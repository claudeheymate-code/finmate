"""Resumen de inicio y de cierre de jornada.

Formato del mensaje:
  1. Encabezado con la fecha.
  2. Un párrafo (Claude Haiku) que explica en conceptos qué pasó en el
     mercado y por qué: las noticias y movimientos de mayor impacto. No es una
     lista de cifras.
  3. Viñetas con los números, armadas por código con datos reales (nunca por
     Claude): índices, Chile, tickers del usuario, portafolio y, al inicio,
     la agenda del día y los avisos guardados fuera de horario. Las secciones
     sin datos no se muestran.

Si Claude falla, el párrafo se arma con los titulares más importantes.
"""

import datetime as dt
import json
import logging
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

# Finnhub gratis no da el nivel de los índices: se usan sus ETF (el precio es el del ETF, por eso va el ticker).
INDICES = (("SPY", "S&P 500 (SPY)"), ("QQQ", "Nasdaq 100 (QQQ)"), ("DIA", "Dow Jones (DIA)"), ("ECH", "Bolsa Chile (ECH)"))
MAX_SYMBOLS = 12
MAX_HELD_LINES = 5
HEADERS = {"start": "☀️ *Inicio de jornada*", "end": "🌙 *Cierre de jornada*"}
_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
_HELD_LABELS = {"watchlist": "Watchlist", "noticias": "Noticia", "macro": "Dato macro", "podcast": "Podcast",
                "earnings": "Resultados", "semanal": "Resumen semanal"}


# ---------------------------------------------------------------- formato

def _num(value: float, decimals: int = 2) -> str:
    s = f"{value:,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(pct) -> str:
    if pct is None:
        return ""
    p = float(pct)
    if abs(p) < 0.05:
        return "▪️ 0,0%"
    return f"{'🟢 ▲' if p > 0 else '🔴 ▼'} {_num(abs(p), 1)}%"


def _date_label(tz_name: Optional[str] = None, now: Optional[dt.datetime] = None) -> str:
    from config.settings import TIMEZONE

    try:
        tz = ZoneInfo(tz_name or TIMEZONE)
    except Exception:  # noqa: BLE001
        tz = ZoneInfo("America/Santiago")
    d = (now or dt.datetime.now(dt.timezone.utc)).astimezone(tz)
    return f"{_DIAS[d.weekday()]} {d.day} {_MESES[d.month - 1]}"


# ---------------------------------------------------------------- datos

def _cached_json(key: str, ttl: int, compute):
    """La cache de Redis guarda texto: las listas van como JSON."""
    from finmate.db.cache import cached

    try:
        return json.loads(cached(key, ttl, lambda: json.dumps(compute() or [])) or "[]")
    except Exception:  # noqa: BLE001
        return compute() or []


def _user_symbols(user_id: int) -> tuple:
    """(símbolos en orden, set de los que están en el portafolio)."""
    from finmate.db.repository import get_portfolio, get_watchlist

    syms, held = [], set()
    try:
        for s, _q, _c in get_portfolio(user_id):
            syms.append(s)
            held.add((s or "").upper())
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
    return out[:MAX_SYMBOLS], held


def _quotes(symbols) -> list:
    """[{symbol, label, price, change_pct, is_closed}] solo de los que cotizan."""
    from finmate.services.quotes import get_quote

    out = []
    for sym, label in symbols:
        try:
            q = get_quote(sym)
        except Exception:  # noqa: BLE001
            q = None
        if q and q.get("price") is not None:
            out.append({"symbol": sym, "label": label, "price": float(q["price"]),
                        "change_pct": q.get("change_pct"), "is_closed": bool(q.get("is_closed"))})
    return out


def _general_news(limit: int = 8) -> list:
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


def _chile() -> list:
    """[{label, value, fmt}] del Banco Central (dólar, UF, TPM), con cache 30 min."""
    try:
        from finmate.data_sources import bcch

        if not bcch.is_configured():
            return []
        data = _cached_json("finmate:cl_snapshot", 1800, bcch.get_snapshot)
        return [d for d in data if d.get("code") in ("USD_CLP", "UF", "TPM")]
    except Exception:  # noqa: BLE001
        return []


def _releases_today() -> list:
    try:
        from finmate.data_sources import fred

        if not fred.is_configured():
            return []
        rel = _cached_json("finmate:us_releases_7d", 1800, lambda: fred.get_upcoming_releases(days_ahead=7))
        today = dt.date.today().isoformat()
        return [r["name"] for r in rel if r.get("date") == today]
    except Exception:  # noqa: BLE001
        return []


def _portfolio(user_id: int) -> dict:
    """{"value", "day_change", "day_pct"} o {}."""
    try:
        from finmate.services.portfolio import compute_portfolio

        t = (compute_portfolio(user_id) or {}).get("totals") or {}
        if t.get("value"):
            day = t.get("day_change")
            base = (t["value"] - day) if day is not None else None
            return {"value": t["value"], "day_change": day,
                    "day_pct": (day / base * 100) if day is not None and base else None}
    except Exception:  # noqa: BLE001
        pass
    return {}


def gather(user_id: int, edge: str, held: Optional[list] = None, digest: Optional[list] = None) -> dict:
    syms, in_portfolio = _user_symbols(user_id)
    facts = {
        "indices": _quotes(INDICES),
        "mis_activos": _quotes([(s, s) for s in syms]),
        "en_portafolio": sorted(in_portfolio),
        "noticias_de_mis_activos": _symbol_news(syms),
        "noticias_del_mercado": _general_news(),
        "portafolio": _portfolio(user_id),
        "chile": _chile(),
        "noticias_para_ti": list(digest or []),
    }
    if edge == "start":
        facts["agenda_hoy"] = _releases_today()
        facts["avisos_fuera_de_horario"] = list(held or [])[:15]
    return facts


# ---------------------------------------------------------------- párrafo

_PROMPT = {
    "start": ("Escribe el párrafo de INICIO de jornada. Explica qué dejó la sesión anterior y qué pasó durante la "
              "noche y la mañana: cuál es el tema que mueve al mercado, por qué se movieron los índices o los "
              "activos del usuario que más cambiaron, y qué es lo importante a mirar hoy (datos que se publican, "
              "resultados de empresas)."),
    "end": ("Escribe el párrafo de CIERRE de jornada. Explica qué pasó hoy en el mercado y por qué: el tema "
            "principal del día, las noticias de mayor impacto y cómo se conectan con los movimientos de los "
            "índices y de los activos del usuario que más se movieron."),
}

_SYSTEM = ("Eres Finmate, asistente financiero por WhatsApp. Español de Chile, tuteo, sin voseo. Respondes con UN "
           "solo párrafo de 80 a 140 palabras, en texto plano (sin asteriscos ni negritas), sin títulos, sin listas, sin emojis, sin saludo y sin recomendar "
           "comprar ni vender. El párrafo es conceptual: cuenta la historia del día (qué pasó, por qué y qué "
           "significa), conectando noticias con movimientos. Las cifras van aparte en una lista, así que no las "
           "repitas: menciona como máximo dos o tres números cuando sean clave para entender. Prioriza lo de "
           "mayor impacto y deja fuera lo menor. Usa solo los datos entregados; si algo no está, no lo inventes "
           "ni especules con causas que los datos no muestran.")


def _facts_for_prompt(facts: dict) -> str:
    def q(x):
        return f"{x['label']} {x['change_pct']:+.2f}%" if x.get("change_pct") is not None else x["label"]

    lines = []
    if facts.get("indices"):
        lines.append("Índices (vía ETF): " + "; ".join(q(x) for x in facts["indices"]))
    if facts.get("mis_activos"):
        movers = sorted(facts["mis_activos"], key=lambda x: -abs(x.get("change_pct") or 0))
        lines.append("Activos del usuario, del que más se movió al que menos: " + "; ".join(q(x) for x in movers))
    for key, label in (("noticias_de_mis_activos", "Noticias de sus activos"),
                       ("noticias_del_mercado", "Noticias generales del mercado")):
        if facts.get(key):
            lines.append(f"{label}:\n  - " + "\n  - ".join(facts[key]))
    mine = [d for d in facts.get("noticias_para_ti") or [] if (d.get("level") or 2) >= 2]
    if mine:
        lines.append("Noticias guardadas para su resumen (le importan; van en lista aparte):\n  - " +
                     "\n  - ".join(f"{d['symbol'] + ': ' if d.get('symbol') else ''}{d['headline']}" for d in mine[:8]))
    p = facts.get("portafolio") or {}
    if p.get("day_pct") is not None:
        lines.append(f"Su portafolio hoy: {p['day_pct']:+.2f}%")
    if facts.get("agenda_hoy"):
        lines.append("Se publica hoy en EE.UU.: " + ", ".join(facts["agenda_hoy"]))
    if facts.get("avisos_fuera_de_horario"):
        lines.append(f"Avisos guardados de fuera de horario (van en lista aparte): {len(facts['avisos_fuera_de_horario'])}")
    return "\n".join(lines)


def _fallback_paragraph(facts: dict, edge: str) -> str:
    news = (facts.get("noticias_de_mis_activos") or [])[:2] + (facts.get("noticias_del_mercado") or [])[:2]
    if news:
        intro = "Lo más relevante desde ayer" if edge == "start" else "Lo más relevante de hoy"
        return f"{intro}: " + "; ".join(n.rsplit(" (", 1)[0] for n in news) + "."
    if facts.get("indices") or facts.get("mis_activos"):
        return "No encontré noticias destacadas; abajo tienes cómo se movieron los mercados y tus activos."
    return "Sin datos de mercado disponibles en este momento."


def _plain(text: str) -> str:
    """El párrafo va sin asteriscos ni guiones bajos (sin negritas ni cursivas sueltas)."""
    import re

    text = re.sub(r"[*_`#]+", "", text or "")
    return " ".join(text.split()).strip()


def paragraph(facts: dict, edge: str, name: str = "") -> str:
    """El párrafo conceptual con Claude Haiku; si no se puede, uno con los titulares."""
    try:
        from finmate.agent.orchestrator import ANTHROPIC_MODEL_DEFAULT, _client, _record_usage

        data = _facts_for_prompt(facts)
        if _client is not None and data:
            r = _client.messages.create(
                model=ANTHROPIC_MODEL_DEFAULT, max_tokens=500, system=_SYSTEM,
                messages=[{"role": "user", "content": f"{_PROMPT[edge]}\nNombre del usuario: {name or '—'}\n"
                                                       f"Datos:\n{data}"}])
            _record_usage(ANTHROPIC_MODEL_DEFAULT, r)
            text = _plain("".join(b.text for b in r.content if b.type == "text"))
            if text:
                return text
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Resumen de jornada: Claude no respondió ({type(e).__name__}); uso el resumen simple.")
    return _fallback_paragraph(facts, edge)


# ---------------------------------------------------------------- viñetas

def _quote_line(x: dict, star: bool = False) -> str:
    tag = " 💼" if star else ""
    closed = " (cerrado)" if x.get("is_closed") and x.get("change_pct") in (None, 0) else ""
    return f"• {x['label']}{tag}  ${_num(x['price'])}  {_pct(x.get('change_pct'))}{closed}".rstrip()


def bullets(facts: dict, edge: str) -> str:
    sections = []
    if facts.get("indices"):
        title = "📊 *Índices (cierre anterior)*" if edge == "start" else "📊 *Índices*"
        sections.append(title + "\n" + "\n".join(_quote_line(x) for x in facts["indices"]))

    cl = facts.get("chile") or []
    if cl:
        rows = []
        for it in cl:
            val = f"${_num(it['value'])}" if it.get("fmt") == "clp" else f"{_num(it['value'])}%"
            label = {"USD_CLP": "Dólar", "TPM": "TPM"}.get(it.get("code"), it.get("label", ""))
            rows.append(f"• {label}  {val}")
        sections.append("🇨🇱 *Chile*\n" + "\n".join(rows))

    mine = facts.get("mis_activos") or []
    if mine:
        held = set(facts.get("en_portafolio") or [])
        mine = sorted(mine, key=lambda x: -(x.get("change_pct") or 0))
        sections.append("⭐ *Tus tickers*\n" + "\n".join(_quote_line(x, x["symbol"] in held) for x in mine))

    p = facts.get("portafolio") or {}
    if p.get("value"):
        line = f"💼 *Tu portafolio*\n• US${_num(p['value'], 0)}"
        if p.get("day_change") is not None:
            sign = "+" if p["day_change"] >= 0 else "−"
            line += f"  {_pct(p.get('day_pct'))} ({sign}US${_num(abs(p['day_change']), 0)})"
        sections.append(line)

    news = facts.get("noticias_para_ti") or []
    if news:
        rows = []
        for d in news:
            who = f"{d['symbol']}: " if d.get("symbol") else ""
            head = d["headline"] if len(d["headline"]) <= 140 else d["headline"][:139] + "…"
            rows.append(f"{d.get('code', '•')}) {who}{head}" if d.get("code") else f"• {who}{head}")
        rows.append("")
        rows.append("Califícalas con la letra y un número del 1 al 3, por ejemplo: a3 b1")
        sections.append("📰 *Noticias para ti*\n" + "\n".join(rows))

    if edge == "start" and facts.get("agenda_hoy"):
        sections.append("🗓️ *Hoy se publica*\n" + "\n".join(f"• {n}" for n in facts["agenda_hoy"]))

    held_items = facts.get("avisos_fuera_de_horario") or []
    if edge == "start" and held_items:
        rows = []
        for h in held_items[:MAX_HELD_LINES]:
            if isinstance(h, dict):
                k = h.get("kind") or ""
                kind = _HELD_LABELS.get(k) or (k[:1].upper() + k[1:] if k else "Aviso")
                txt = " ".join((h.get("text") or "").replace("*", "").replace("_", "").split())
            else:
                kind, txt = "Aviso", " ".join(str(h).split())
            rows.append(f"• {kind}: {txt[:110] + '…' if len(txt) > 110 else txt}")
        extra = len(held_items) - MAX_HELD_LINES
        if extra > 0:
            rows.append(f"• …y {extra} más")
        sections.append("📬 *Mientras no estabas*\n" + "\n".join(rows))

    return "\n\n".join(sections)


def compose(facts: dict, edge: str, name: str = "") -> str:
    """Párrafo conceptual + viñetas con los números."""
    body = paragraph(facts, edge, name)
    tail = bullets(facts, edge)
    return f"{body}\n\n{tail}" if tail else body


def send_brief(user_id: int, phone: str, edge: str, name: str = "", tz_name: Optional[str] = None) -> bool:
    """Arma y manda el resumen. Lo deja en el historial, así el bot sabe qué dijo
    si el usuario le responde."""
    from config.settings import TEMPLATE_MARKET_NOTIFY
    from finmate.services.workday import window_open

    if not TEMPLATE_MARKET_NOTIFY and not window_open(user_id):
        # WhatsApp no deja escribirle (no escribe hace más de 24 h; Meta lo rechazaba con el
        # error 131047 y se perdía). No se toca nada de lo guardado: el resumen se arma con
        # todo lo acumulado apenas vuelva a escribir.
        if edge == "start" and _send_morning_template(user_id, phone, name, tz_name):
            _mark_brief_pending(user_id, edge, via="template")
            logger.info(f"Jornada: aviso diario (plantilla) enviado al usuario {user_id}; "
                        "el resumen sale cuando responda")
            return True
        _mark_brief_pending(user_id, edge)
        logger.info(f"Jornada: resumen de {'inicio' if edge == 'start' else 'cierre'} para el usuario {user_id} "
                    "pendiente: no escribe hace más de 24 h (se lo mando cuando vuelva a escribir)")
        return False
    return _build_and_send(user_id, phone, edge, name, tz_name)


def _build_and_send(user_id: int, phone: str, edge: str, name: str = "", tz_name: Optional[str] = None,
                    header: Optional[str] = None, note: str = "", messenger=None, free_text: bool = False) -> bool:
    from config.settings import TEMPLATE_MARKET_NOTIFY
    from finmate.services.workday import pop_held

    held = pop_held(user_id) if edge == "start" else []
    digest = []
    try:
        from finmate.services import news_profile

        digest = news_profile.assign_brief_codes(user_id, news_profile.pop_digest(user_id))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Jornada: no pude leer las noticias guardadas de {user_id}: {e}")
    text = f"{header or HEADERS[edge]} · {_date_label(tz_name)}\n\n{compose(gather(user_id, edge, held, digest), edge, name)}"
    if note:
        text += f"\n\n{note}"
    if messenger is None:
        from finmate.whatsapp.messenger import WhatsAppMessenger
        messenger = WhatsAppMessenger()
    if TEMPLATE_MARKET_NOTIFY and not note and not free_text:
        from finmate.alerts.pending import queue_pending

        queue_pending(phone, text)
        ok = messenger.send_template(phone, TEMPLATE_MARKET_NOTIFY,
                                     {"1": "Resumen de inicio de jornada" if edge == "start" else "Resumen de cierre de jornada"})
    else:
        ok = messenger.send_message(phone, text)
    try:
        from finmate.db.repository import save_turn

        save_turn(user_id, "assistant", text)
    except Exception:  # noqa: BLE001
        pass
    logger.info(f"Jornada: resumen de {'inicio' if edge == 'start' else 'cierre'} para el usuario {user_id} "
                f"{'enviado' if ok else 'NO enviado'}")
    return bool(ok)


# ── Resúmenes que no se pudieron mandar (ventana de 24 h cerrada) ──────────

def _brief_key(user_id: int) -> str:
    return f"brief:pending:{user_id}"


def _mark_brief_pending(user_id: int, edge: str, via: str = "") -> None:
    from finmate.db.state_store import load_json, save_json

    prev = load_json(_brief_key(user_id), None) or {}
    save_json(_brief_key(user_id), {"since": prev.get("since") or dt.datetime.utcnow().isoformat(timespec="minutes"),
                                    "missed": int(prev.get("missed") or 0) + 1, "edge": edge,
                                    "via": via or prev.get("via", "")})


def has_pending_brief(user_id: int) -> bool:
    from finmate.db.state_store import load_json

    return bool(load_json(_brief_key(user_id), None))


def deliver_pending_brief(phone: str, messenger=None) -> bool:
    """Si quedaron resúmenes sin mandar (ventana cerrada), le manda uno solo, armado ahora con
    todo lo acumulado desde entonces. Se llama apenas el usuario escribe."""
    try:
        from finmate.db.repository import find_user_by_phone
        from finmate.db.state_store import load_json, save_json

        user = find_user_by_phone(phone)
        if user is None or (getattr(user, "access_status", None) or "approved") != "approved":
            return False
        item = load_json(_brief_key(user.id), None)
        if not item:
            return False
        save_json(_brief_key(user.id), None)
        missed = int(item.get("missed") or 1)
        if item.get("via") == "template" and missed == 1:
            # Respondió al aviso diario de hoy: es el resumen de inicio normal.
            ok = _build_and_send(user.id, phone, "start", name=user.name or "",
                                 tz_name=getattr(user, "timezone", None), messenger=messenger, free_text=True)
        else:
            note = ("Te lo guardé porque llevabas más de un día sin escribirme y WhatsApp no me deja mandarte "
                    "mensajes antes de que me hables." + (f" Junta lo de {missed} resúmenes." if missed > 1 else ""))
            ok = _build_and_send(user.id, phone, "start", name=user.name or "",
                                 tz_name=getattr(user, "timezone", None),
                                 header="🗞️ *Lo que te perdiste*", note=note, messenger=messenger)
        logger.info(f"Jornada: resumen pendiente entregado al usuario {user.id} ({'ok' if ok else 'falló'})")
        return ok
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Jornada: no pude entregar el resumen pendiente a {phone}: {e}")
        return False


# ── Aviso diario por plantilla (lunes a viernes) ──────────────────────────
# Para quien no escribe hace más de 24 h: una plantilla aprobada por Meta
# (META_TEMPLATE_MORNING_BRIEF) avisa que el resumen está listo, con el
# destacado del día. Al tocar "Sí, mándamelo" (o escribir cualquier cosa) se
# abre la ventana de 24 h, llega el resumen y el resto del día todo llega normal.

MORNING_YES = ("sí, mándamelo", "si, mandamelo", "sí, mandamelo", "si, mándamelo")
MORNING_NO = ("hoy no",)
_HIGHLIGHT_FALLBACK = "cómo cerró Wall Street y cómo vienen tus activos"


def _clean_param(text: str, limit: int) -> str:
    """Los parámetros de plantilla no aceptan saltos de línea ni muchos espacios seguidos."""
    import re

    text = re.sub(r"[*_~`\n\r\t]+", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    return text[:limit].rstrip(" ,;:") or ""


def morning_highlight(today: Optional[dt.date] = None) -> str:
    """Lo más importante del día en una frase corta (una vez al día para todos)."""
    from finmate.db.state_store import load_json, save_json

    today = today or dt.date.today()
    key = f"morning:highlight:{today.isoformat()}"
    cached = load_json(key, None)
    if cached:
        return cached
    agenda = _releases_today()
    news = _general_news(limit=6)
    text = ""
    try:
        from finmate.agent.orchestrator import ANTHROPIC_MODEL_DEFAULT, _client, _record_usage

        if _client is not None and (agenda or news):
            facts = ("Datos de EE.UU. que se publican hoy: " + ", ".join(agenda) + "\n" if agenda else "") + \
                    ("Titulares de las últimas horas:\n- " + "\n- ".join(news) if news else "")
            r = _client.messages.create(
                model=ANTHROPIC_MODEL_DEFAULT, max_tokens=80,
                system=("Escribe en español de Chile UNA frase de máximo 80 caracteres con lo más importante del "
                        "día para un inversionista, que se lea bien dentro de paréntesis en: 'tu resumen de hoy ya "
                        "está disponible (…)'. Empieza en minúscula, sin punto final, sin emojis, sin comillas, "
                        "sin recomendar comprar o vender. Ej: 'se publica la inflación PCE de EE.UU.' o 'Nvidia "
                        "presenta resultados tras el cierre'. Usa solo los datos entregados."),
                messages=[{"role": "user", "content": facts}])
            _record_usage(ANTHROPIC_MODEL_DEFAULT, r)
            text = "".join(b.text for b in r.content if b.type == "text")
    except Exception as e:  # noqa: BLE001
        logger.info(f"Jornada: sin destacado del día por Claude ({type(e).__name__})")
    if not text and agenda:
        text = "hoy se publica " + ", ".join(agenda[:2])
    text = _clean_param(text, 90).strip("\"'«»") or _HIGHLIGHT_FALLBACK
    save_json(key, text)
    return text


def _send_morning_template(user_id: int, phone: str, name: str = "", tz_name: Optional[str] = None,
                           messenger=None) -> bool:
    """Manda el aviso diario si hay plantilla configurada y es lunes a viernes (hora del usuario)."""
    from config.settings import META_TEMPLATE_MORNING_BRIEF, TIMEZONE

    if not META_TEMPLATE_MORNING_BRIEF:
        return False
    try:
        local = dt.datetime.now(dt.timezone.utc).astimezone(ZoneInfo(tz_name or TIMEZONE))
    except Exception:  # noqa: BLE001
        local = dt.datetime.now(dt.timezone.utc).astimezone(ZoneInfo("America/Santiago"))
    if local.weekday() >= 5:
        return False
    first = _clean_param((name or "").split(" ")[0], 30) or "hola"
    try:
        if messenger is None:
            from finmate.whatsapp.messenger import WhatsAppMessenger
            messenger = WhatsAppMessenger()
        ok = messenger.send_template(phone, META_TEMPLATE_MORNING_BRIEF,
                                     {"1": first, "2": morning_highlight(local.date())})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Jornada: no pude mandar el aviso diario a {user_id}: {e}")
        return False
    return bool(ok)


def handle_morning_reply(phone: str, text: str, messenger=None) -> Optional[str]:
    """Botones del aviso diario. "Sí, mándamelo" → manda el resumen (devuelve "" porque ya
    respondió); "Hoy no" → devuelve una respuesta corta. None si no es uno de esos botones."""
    t = (text or "").strip().lower()
    if t not in MORNING_YES and t not in MORNING_NO:
        return None
    from finmate.db.repository import find_user_by_phone, save_turn
    from finmate.db.state_store import save_json

    user = find_user_by_phone(phone)
    if user is None or (getattr(user, "access_status", None) or "approved") != "approved":
        return None
    try:
        save_turn(user.id, "user", text.strip())
    except Exception:  # noqa: BLE001
        pass
    if t in MORNING_NO:
        save_json(_brief_key(user.id), None)
        reply = "Dale, que tengas buen día 👋 Si más tarde lo quieres, escríbeme \"resumen\" y te lo mando."
        try:
            save_turn(user.id, "assistant", reply)
        except Exception:  # noqa: BLE001
            pass
        return reply
    if not deliver_pending_brief(phone, messenger=messenger):          # sin pendiente: se arma uno nuevo
        _build_and_send(user.id, phone, "start", name=user.name or "", tz_name=getattr(user, "timezone", None),
                        messenger=messenger, free_text=True)
    return ""
