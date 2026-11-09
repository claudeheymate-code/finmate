"""
Finmate — Tool para explicar el movimiento de un activo (Plan Fase 2)

Conecta precio actual + variación diaria + noticias recientes de Finnhub
para que el agente pueda explicar "por qué se movió tanto X".
"""
import datetime as dt
import logging

import httpx

from config.settings import FINNHUB_API_KEY

logger = logging.getLogger(__name__)

_BASE = "https://finnhub.io/api/v1"


def _get_quote(symbol: str) -> dict:
    try:
        r = httpx.get(
            f"{_BASE}/quote",
            params={"symbol": symbol, "token": FINNHUB_API_KEY},
            timeout=5,
        )
        r.raise_for_status()
        d = r.json()
        return {
            "price": d.get("c"),
            "change_pct": d.get("dp"),
            "open": d.get("o"),
            "prev_close": d.get("pc"),
        }
    except Exception as e:
        logger.error(f"Error cotizando {symbol}: {e}")
        return {}


_COMPANY_SUFFIXES = (" inc", " corp", " corporation", " ltd", " plc", " co", " sa", " holdings", " group")


def _get_company_name(symbol: str) -> str:
    """Nombre corto de la empresa (ej. 'NVIDIA'), o '' si no se encuentra."""
    try:
        r = httpx.get(
            f"{_BASE}/stock/profile2",
            params={"symbol": symbol, "token": FINNHUB_API_KEY},
            timeout=5,
        )
        r.raise_for_status()
        name = (r.json() or {}).get("name", "").strip().rstrip(".")
        low = name.lower()
        for suf in _COMPANY_SUFFIXES:
            if low.endswith(suf):
                name = name[: -len(suf)].strip().rstrip(",")
                break
        return name
    except Exception as e:
        logger.warning(f"No pude obtener el nombre de {symbol}: {e}")
        return ""


def _get_news(symbol: str, limit: int = 3) -> list:
    """Devuelve las últimas N noticias de Finnhub para el símbolo (últimos 7 días)."""
    try:
        today = dt.date.today().isoformat()
        week_ago = (dt.date.today() - dt.timedelta(days=7)).isoformat()
        r = httpx.get(
            f"{_BASE}/company-news",
            params={"symbol": symbol, "from": week_ago, "to": today, "token": FINNHUB_API_KEY},
            timeout=5,
        )
        r.raise_for_status()
        items = r.json() or []
        # Finnhub devuelve también notas genéricas que solo "mencionan" el
        # ticker (ej. listados de Yahoo). Priorizamos las que nombran al
        # símbolo o a la empresa en el titular o el resumen.
        keys = {symbol.lower()}
        name = _get_company_name(symbol)
        if name:
            keys.add(name.lower())
        relevant = [
            it for it in items
            if any(k in f"{it.get('headline', '')} {it.get('summary', '')}".lower() for k in keys)
        ]
        return relevant[:limit]
    except Exception as e:
        logger.error(f"Error obteniendo noticias de {symbol}: {e}")
        return []


def tool_explain_movement(tool_input: dict) -> str:
    """Explica el movimiento de un activo: precio + variación + noticias recientes."""
    symbol = tool_input.get("symbol", "").upper().strip()
    if not symbol:
        return "❌ Necesito el símbolo del activo (ej: AAPL, NVDA, SPY)."

    quote = _get_quote(symbol)
    if not quote or quote.get("price") is None:
        return f"❌ No pude obtener datos de *{symbol}* ahora. ¿Es un ticker válido?"

    price = quote["price"]
    change_pct = quote.get("change_pct") or 0.0
    emoji = "🟢" if change_pct >= 0 else "🔴"
    sign = "+" if change_pct >= 0 else ""

    lines = [
        f"*{symbol}* {emoji}",
        f"Precio: ${price:,.2f}",
        f"Variación hoy: {sign}{change_pct:.2f}%",
    ]
    if quote.get("open") and quote.get("prev_close"):
        lines.append(
            f"Apertura: ${quote['open']:,.2f} | Cierre anterior: ${quote['prev_close']:,.2f}"
        )
    lines.append("")

    news = _get_news(symbol)
    if news:
        lines.append("*Noticias recientes:*")
        for item in news:
            headline = item.get("headline", "").strip()
            source = item.get("source", "")
            if headline:
                truncated = headline[:120] + ("..." if len(headline) > 120 else "")
                lines.append(f"• {truncated} _{source}_")
    else:
        lines.append("_No encontré noticias recientes que hablen directamente de este activo._")

    return "\n".join(lines)
