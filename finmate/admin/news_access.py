"""¿Qué puede leer el bot de cada medio? (Admin → Fuentes)

Tres niveles:
- "completo": el bot puede leer el artículo entero (sitio abierto o API con texto).
- "mixto": algunos artículos se leen enteros y otros son de pago (solo titular + resumen).
- "titular": solo titular y resumen corto del RSS/API; el artículo es de pago o el sitio
  bloquea la lectura automática.

`ACCESS` es lo comprobado a mano el 26 nov 2026. `check()` lo vuelve a comprobar en vivo:
abre los últimos artículos de cada medio y mira si responden, si se declaran de pago
(schema.org isAccessibleForFree=false) y cuánto texto se puede extraer.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from concurrent.futures import ThreadPoolExecutor

import httpx

logger = logging.getLogger(__name__)

STATE_KEY = "admin:news_access_check"
MIN_WORDS = 150

LABELS = {"completo": "Texto completo", "mixto": "Mixto", "titular": "Solo titulares"}

# feed: id de premium_news.FEEDS que se usa para la comprobación en vivo
ACCESS = [
    {"id": "cnbc", "name": "CNBC", "access": "completo", "feed": "cnbc_top", "via": "RSS",
     "note": "Noticias abiertas: el bot puede leer el artículo entero. CNBC Pro es de pago."},
    {"id": "sec", "name": "SEC EDGAR", "access": "completo", "feed": None, "via": "API oficial",
     "note": "Reportes oficiales completos de empresas de EE.UU. (8-K, 10-Q, 10-K)."},
    {"id": "guardian", "name": "The Guardian", "access": "completo", "feed": None, "via": "API",
     "note": "La API entrega el texto completo, pero falta cargar GUARDIAN_API_KEY (gratis) en Railway."},
    {"id": "df", "name": "Diario Financiero", "access": "mixto", "feed": "df", "via": "RSS",
     "note": "Opinión y cartas son abiertas; las noticias están marcadas de pago y se usan como titular + resumen."},
    {"id": "wsj", "name": "WSJ", "access": "titular", "feed": "wsj_markets", "via": "RSS",
     "note": "Titular + resumen. El artículo es de pago (responde 401)."},
    {"id": "marketwatch", "name": "MarketWatch", "access": "titular", "feed": "marketwatch", "via": "RSS",
     "note": "Titular + resumen. El artículo responde 401 a lectores automáticos."},
    {"id": "bloomberg", "name": "Bloomberg", "access": "titular", "feed": "bloomberg_markets", "via": "RSS",
     "note": "Titular + resumen. El artículo es de pago (responde 403)."},
    {"id": "ft", "name": "Financial Times", "access": "titular", "feed": "ft_markets", "via": "RSS",
     "note": "Titular + resumen. El artículo es de pago (responde 403)."},
    {"id": "economist", "name": "The Economist", "access": "titular", "feed": "economist_finance", "via": "RSS",
     "note": "Titular + resumen de una línea. El artículo es de pago (responde 403)."},
    {"id": "reuters", "name": "Reuters", "access": "titular", "feed": "reuters_business", "via": "Google News",
     "note": "Solo el titular (Google News no trae resumen). Reuters bloquea la lectura automática (401)."},
    {"id": "finnhub", "name": "Finnhub / Marketaux / Bing News", "access": "mixto", "feed": None, "via": "API / RSS",
     "note": "Titular + resumen de muchos sitios. El bot intenta abrir el link: si el sitio es abierto lee el "
             "artículo; si es de pago, se queda con el resumen."},
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Finmate/1.0; +https://web-production-3626a.up.railway.app)",
           "Accept-Language": "es-CL,es;q=0.9,en;q=0.8"}


def _probe_article(client: httpx.Client, url: str) -> str:
    """'abierto' | 'pago' | 'bloqueado' | 'poco texto' para un artículo."""
    try:
        r = client.get(url)
    except Exception:  # noqa: BLE001
        return "bloqueado"
    if r.status_code in (401, 402, 403, 451) or r.status_code >= 500:
        return "bloqueado"
    if r.status_code != 200:
        return "bloqueado"
    raw = r.text
    from finmate.data_sources.news_content import is_paywalled

    if is_paywalled(raw):
        return "pago"
    try:
        import trafilatura

        text = trafilatura.extract(raw, include_comments=False, include_tables=False) or ""
    except Exception:  # noqa: BLE001
        text = " ".join(re.findall(r"(?is)<p[^>]*>(.*?)</p>", raw))
    return "abierto" if len(text.split()) >= MIN_WORDS else "poco texto"


def _classify(results: list[str]) -> str:
    if not results:
        return "titular"
    open_ = sum(1 for x in results if x == "abierto")
    if open_ == len(results):
        return "completo"
    return "mixto" if open_ else "titular"


def _check_one(entry: dict, articles: int = 3) -> dict:
    from finmate.data_sources import premium_news

    feed = next((f for f in premium_news.FEEDS if f["id"] == entry["feed"]), None)
    if not feed:
        return {"id": entry["id"], "access": entry["access"], "checked": False}
    try:
        with httpx.Client(timeout=12, headers=HEADERS, follow_redirects=True) as client:
            items = premium_news.fetch_feed(feed, client)
            links = [i["url"] for i in items if i.get("url")][:articles]
            results = [_probe_article(client, u) for u in links]
    except Exception as e:  # noqa: BLE001
        return {"id": entry["id"], "access": entry["access"], "checked": False, "error": type(e).__name__}
    return {"id": entry["id"], "access": _classify(results), "checked": True, "articles": results}


def check() -> dict:
    """Comprueba en vivo los medios con RSS y guarda el resultado."""
    with ThreadPoolExecutor(max_workers=5) as pool:
        res = list(pool.map(_check_one, [e for e in ACCESS if e["feed"]]))
    data = {"at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z", "results": {r["id"]: r for r in res}}
    try:
        from finmate.db.state_store import save_json

        save_json(STATE_KEY, data)
    except Exception as e:  # noqa: BLE001
        logger.info(f"No pude guardar la comprobación de acceso: {e}")
    return data


def overview() -> dict:
    """Lista para el admin: lo conocido + la última comprobación en vivo (si hay)."""
    try:
        from finmate.db.state_store import load_json

        last = load_json(STATE_KEY, None) or {}
    except Exception:  # noqa: BLE001
        last = {}
    live = last.get("results", {})
    try:
        from finmate.data_sources.news_content import GUARDIAN_API_KEY

        guardian_ok = bool(GUARDIAN_API_KEY)
    except Exception:  # noqa: BLE001
        guardian_ok = False
    rows = []
    for e in ACCESS:
        if e["id"] == "guardian" and guardian_ok:
            e = {**e, "note": "La API entrega el texto completo de los artículos (clave configurada)."}
        lv = live.get(e["id"]) or {}
        access = lv.get("access") if lv.get("checked") else e["access"]
        label = LABELS[access]
        if e["id"] == "guardian" and not guardian_ok:
            label += " · falta clave"
        rows.append({**e, "access": access, "label": label, "expected": e["access"],
                     "changed": bool(lv.get("checked")) and access != e["access"],
                     "articles": lv.get("articles") or []})
    order = {"completo": 0, "mixto": 1, "titular": 2}
    rows.sort(key=lambda r: (order[r["access"]], r["name"]))
    return {"rows": rows, "checked_at": last.get("at")}
