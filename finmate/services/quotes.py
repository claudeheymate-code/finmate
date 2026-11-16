"""Cotizaciones y perfil de empresa desde Finnhub, con un cache corto en memoria.

El panel pide los mismos precios varias veces seguidas (resumen, inversiones,
recargas), así que se guardan 60 segundos para no gastar el límite gratuito
de Finnhub. Reutiliza la función de cotización que ya usa el bot.
"""
import logging
import threading
import time
from typing import Optional

import httpx

from config.settings import FINNHUB_API_KEY

logger = logging.getLogger(__name__)

_QUOTE_TTL = 60
_PROFILE_TTL = 24 * 3600
_lock = threading.Lock()
_quotes: dict = {}
_profiles: dict = {}


def get_quote(symbol: str) -> Optional[dict]:
    """{"price", "change_pct", "is_closed"} o None si no hay cotización."""
    from finmate.whatsapp.webhook import _get_finnhub_quote

    symbol = symbol.upper()
    # Etapa B: si el flujo en tiempo real tiene un precio reciente, se usa ese.
    try:
        from finmate.realtime.price_stream import get_live_quote

        live = get_live_quote(symbol)
        if live:
            return live
    except Exception:
        pass
    now = time.time()
    with _lock:
        hit = _quotes.get(symbol)
        if hit and now - hit[0] < _QUOTE_TTL:
            return hit[1]
    try:
        with httpx.Client(timeout=10) as client:
            q = _get_finnhub_quote(client, symbol)
    except Exception as e:
        logger.error(f"Error cotizando {symbol}: {e}")
        q = None
    if q and q.get("price") is not None:
        with _lock:
            _quotes[symbol] = (now, q)
    return q


def get_profile(symbol: str) -> dict:
    """Perfil de Finnhub (/stock/profile2): {"name", "finnhubIndustry", ...} o {}."""
    symbol = symbol.upper()
    now = time.time()
    with _lock:
        hit = _profiles.get(symbol)
        if hit and now - hit[0] < _PROFILE_TTL:
            return hit[1]
    data = {}
    try:
        r = httpx.get(
            "https://finnhub.io/api/v1/stock/profile2",
            params={"symbol": symbol, "token": FINNHUB_API_KEY},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:
        logger.warning(f"No pude obtener el perfil de {symbol}: {e}")
    with _lock:
        _profiles[symbol] = (now, data)
    return data


def clear_cache() -> None:
    with _lock:
        _quotes.clear()
        _profiles.clear()
