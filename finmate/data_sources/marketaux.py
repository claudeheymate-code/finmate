"""
Finmate - Cliente de Marketaux (noticias por empresa con sentimiento).

Plan gratis: 100 consultas al día y pocas noticias por consulta, por eso se
llama en lote (varios símbolos por request) y con un intervalo mínimo entre
llamadas (MARKETAUX_MIN_INTERVAL_MINUTES). Sin MARKETAUX_API_KEY, devuelve
vacío.
"""
import logging
import time
from typing import Iterable, Optional

import httpx

from config.settings import MARKETAUX_API_KEY, MARKETAUX_MIN_INTERVAL_MINUTES

logger = logging.getLogger(__name__)

BASE_URL = "https://api.marketaux.com/v1/news/all"

_last_call = {"ts": 0.0}


def is_configured() -> bool:
    return bool(MARKETAUX_API_KEY)


def can_call_now(now: Optional[float] = None) -> bool:
    now = now if now is not None else time.time()
    return now - _last_call["ts"] >= MARKETAUX_MIN_INTERVAL_MINUTES * 60


def get_news(symbols: Iterable[str], published_after: Optional[str] = None,
             force: bool = False) -> list:
    """Noticias recientes de los `symbols` (lote). `published_after` en
    formato YYYY-MM-DDTHH:MM (UTC). Devuelve una lista normalizada:
    [{"symbol","headline","summary","url","source","datetime","sentiment"}]."""
    symbols = sorted({s.upper() for s in symbols if s})
    if not MARKETAUX_API_KEY or not symbols:
        return []
    if not force and not can_call_now():
        return []
    params = {
        "api_token": MARKETAUX_API_KEY,
        "symbols": ",".join(symbols[:50]),
        "filter_entities": "true",
        "language": "en,es",
    }
    if published_after:
        params["published_after"] = published_after
    _last_call["ts"] = time.time()
    try:
        r = httpx.get(BASE_URL, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.error(f"Error consultando Marketaux: {e}")
        return []
    out = []
    for art in data.get("data", []):
        for ent in art.get("entities", []) or []:
            sym = (ent.get("symbol") or "").upper()
            if sym not in symbols:
                continue
            out.append({
                "symbol": sym,
                "headline": art.get("title") or "",
                "summary": art.get("description") or art.get("snippet") or "",
                "url": art.get("url") or "",
                "source": art.get("source") or "Marketaux",
                "datetime": art.get("published_at") or "",
                "sentiment": ent.get("sentiment_score"),
            })
    return out
