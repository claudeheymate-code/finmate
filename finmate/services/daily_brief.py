"""Resumen de inicio y de cierre de jornada: un párrafo con lo relevante.

Junta datos (índices de EE.UU., los activos del usuario, noticias de esos
activos y del mercado, publicaciones macro del día, dólar y UF en Chile y los
avisos guardados fuera de horario) y le pide a Claude Haiku un solo párrafo
corto. Si Claude falla, se arma un párrafo simple con los números.
"""

import datetime as dt
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

INDICES = (("SPY", "S&P 500"), ("QQQ", "Nasdaq 100"), ("DIA", "Dow Jones"))
MAX_SYMBOLS = 12
HEADERS = {"start": "☀️ *Inicio de jornada*", "end": "🌙 *Cierre de jornada*"}


def _user_symbols(user_id: int) -> list:
    from finmate.db.repository import get_portfolio, get_watchlist

    syms = []
    try:
        syms += [s for s, _q, _c in get_portfolio(user_id)]
    except Exception:  # noqa: BLE001
        pass
    try:
        for w in get_watchlist(user_id) or []:
            syms.append(w if isinstance(w, str) else (w[0] if isinstance(w, (list, tuple)) else getattr(w, "symbol", "")))
    except Exception:  # noqa: BLE001
        pass
    seen, out = set(), []
    for s in syms:
        s = (s or "").upper()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out[:MAX_SYMBOLS]


def _quotes(symbols) -> list:
    from finmate.services.quotes import get_quote

    out = []
    for sym, label in symbols:
        try:
            q = get_quote(sym)
        except Exception:  # noqa: BLE001
            q = None
        if q and q.get("price") is not None:
            out.append(f"{label}: {q['price']:.2f} ({(q.get('change_pct') or 0):+.2f}% vs. cierre anterior"
                       f"{', mercado cerrado' if q.get('is_closed') else ''})")
    return out


def _general_news(limit: int = 6) -> list:
    from config.settings import FINNHUB_API_KEY

    if not FINNHUB_API_KEY:
        return []
    try:
        r = httpx.get("https://finnhub.io/api/v1/news", params={"category": "general", "token": FINNHUB_API_KEY}, timeout=10)
        r.raise_for_status()
        cutoff = dt.datetime.now(dt.timezone.utc).timestamp() - 20 * 3600
        return [f"{it.get('headline')} ({it.get('source')})" for it in (r.json() or [])
                if (it.get("datetime") or 0) >= cutoff][:limit]
    except Exception as e:  # noqa: BLE001
        logger.info(f"Resumen de jornada: sin noticias generales ({type(e).__name__})")
        return []


def _symbol_news(symbols: list, limit: int = 6) -> list:
    if not symbols:
        return []
    try:
        from finmate.alerts.news_alerts import fetch_finnhub_news

        items = fetch_finnhub_news(symbols[:6], dt.datetime.now(dt.timezone.utc))
        items.sort(key=lambda x: x.get("datetime") or 0, reverse=True)
        return [f"{it['symbol']}: {it['headline']} ({it['source']})" for it in items[:limit]]
    except Exception as e:  # noqa: BLE001
        logger.info(f"Resumen de jornada: sin noticias de activos ({type(e).__name__})")
        return []


def _cached_tool(key: str, fn_name: str) -> str:
    try:
        from finmate.agent import macro_tools
        from finmate.db.cache import cached

        return cached(key, 1800, getattr(macro_tools, fn_name)) or ""
    except Exception:  # noqa: BLE001
        return ""


def _portfolio_line(user_id: int) -> str:
    try:
        from finmate.services.portfolio import compute_portfolio

        t = (compute_portfolio(user_id) or {}).get("totals") or {}
        if t.get("value"):
            day = t.get("day_change")
            base = (t["value"] - day) if day is not None else None
            extra = f", hoy {day:+,.0f} USD ({day / base * 100:+.2f}%)" if day is not None and base else ""
            return f"Valor del portafolio: {t['value']:,.0f} USD{extra}"
    except Exception:  # noqa: BLE001
        pass
    return ""


def gather(user_id: int, edge: str, held: Optional[list] = None) -> dict:
    syms = _user_symbols(user_id)
    facts = {
        "indices": _quotes(INDICES),
        "mis_activos": _quotes([(s, s) for s in syms]),
        "noticias_de_mis_activos": _symbol_news(syms),
        "noticias_del_mercado": _general_news(),
        "portafolio": _portfolio_line(user_id),
        "chile": _cached_tool("finmate:cl_indicators", "tool_get_chile_indicators")[:600],
    }
    if edge == "start":
        facts["publicaciones_macro_hoy"] = _cached_tool("finmate:us_releases", "tool_get_us_release_calendar")[:800]
        facts["avisos_fuera_de_horario"] = [f"[{h.get('kind')}] {h.get('text', '')[:300]}" for h in (held or [])][:15]
    return facts


_PROMPT = {
    "start": ("Escribe el resumen de INICIO de jornada: los hechos relevantes del mercado desde la jornada anterior "
              "(cómo cerró Wall Street, qué pasó con sus activos, noticias de la noche y la mañana, y lo que se publica "
              "hoy). Si hay avisos fuera de horario, inclúyelos en una frase."),
    "end": ("Escribe el resumen de CIERRE de jornada: cómo le fue hoy al mercado y a sus activos (y a su portafolio, "
            "si hay dato), y las noticias que más importaron durante el día."),
}


def compose(facts: dict, edge: str, name: str = "") -> str:
    """Un párrafo con Claude Haiku; si no se puede, uno simple con los números."""
    try:
        from finmate.agent.orchestrator import ANTHROPIC_MODEL_DEFAULT, _client, _record_usage

        if _client is not None:
            lines = [f"- {k}: {v}" for k, v in facts.items() if v]
            r = _client.messages.create(
                model=ANTHROPIC_MODEL_DEFAULT, max_tokens=450,
                system=("Eres Finmate, asistente financiero por WhatsApp. Español de Chile, tuteo, sin voseo. "
                        "Respondes con UN solo párrafo de 70 a 130 palabras, sin títulos, sin listas, sin "
                        "saludos largos y sin recomendar comprar ni vender. Usa solo los datos entregados; si "
                        "un dato falta, no lo inventes. Menciona cifras clave con 1 decimal."),
                messages=[{"role": "user", "content": f"{_PROMPT[edge]}\nNombre del usuario: {name or '—'}\n"
                                                       "Datos:\n" + "\n".join(lines)}])
            _record_usage(ANTHROPIC_MODEL_DEFAULT, r)
            text = "".join(b.text for b in r.content if b.type == "text").strip()
            if text:
                return text
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Resumen de jornada: Claude no respondió ({type(e).__name__}); uso el resumen simple.")
    parts = []
    if facts.get("indices"):
        parts.append("Índices: " + "; ".join(facts["indices"]) + ".")
    if facts.get("mis_activos"):
        parts.append("Tus activos: " + "; ".join(facts["mis_activos"][:6]) + ".")
    if facts.get("noticias_de_mis_activos"):
        parts.append("Noticias: " + "; ".join(facts["noticias_de_mis_activos"][:3]) + ".")
    if facts.get("avisos_fuera_de_horario"):
        parts.append(f"Además quedaron {len(facts['avisos_fuera_de_horario'])} aviso(s) de fuera de horario.")
    return " ".join(parts) or "Sin datos de mercado disponibles en este momento."


def send_brief(user_id: int, phone: str, edge: str, name: str = "") -> bool:
    """Arma y manda el resumen. Lo deja en el historial, así el bot sabe qué dijo
    si el usuario le responde."""
    from config.settings import TEMPLATE_MARKET_NOTIFY
    from finmate.whatsapp.messenger import WhatsAppMessenger
    from finmate.services.workday import pop_held

    held = pop_held(user_id) if edge == "start" else []
    text = f"{HEADERS[edge]}\n{compose(gather(user_id, edge, held), edge, name)}"
    m = WhatsAppMessenger()
    if TEMPLATE_MARKET_NOTIFY:
        from finmate.alerts.pending import queue_pending

        queue_pending(phone, text)
        ok = m.send_template(phone, TEMPLATE_MARKET_NOTIFY,
                             {"1": "Resumen de inicio de jornada" if edge == "start" else "Resumen de cierre de jornada"})
    else:
        ok = m.send_message(phone, text)
    try:
        from finmate.db.repository import save_turn

        save_turn(user_id, "assistant", text)
    except Exception:  # noqa: BLE001
        pass
    logger.info(f"Jornada: resumen de {'inicio' if edge == 'start' else 'cierre'} para el usuario {user_id} "
                f"{'enviado' if ok else 'NO enviado'}")
    return bool(ok)
