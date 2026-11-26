"""
Contenido completo de noticias (no solo titulares).

- extract_article(url): baja la página y saca el texto principal con
  trafilatura. Sirve para los links de Finnhub, Marketaux, Bing, etc. Si el
  medio tiene muro de pago o bloquea, devuelve "" y el bot usa el resumen.
- bing_news(query): búsqueda de noticias por tema (RSS de Bing News, sin
  clave), con el link directo al medio.
- guardian_search(query): The Guardian Open Platform (texto completo gratis,
  500 llamadas/día). Requiere GUARDIAN_API_KEY; sin clave se salta.
- sec_latest_filings(symbol): últimos 8-K/10-Q/10-K en SEC EDGAR, con el
  texto del comunicado (EX-99.1 si existe). Gratis, sin clave.

Todo con timeouts cortos y cache en Redis: si algo falla, se devuelve vacío
y el resto del bot sigue igual. El contenido es para que el bot resuma al
usuario, no para reenviar artículos completos.
"""
import html
import json
import logging
import os
import re
from typing import List, Optional
from urllib.parse import parse_qs, urlparse

import httpx

logger = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
SEC_UA = os.getenv("SEC_USER_AGENT", "Finmate bot contacto claude.heymate@gmail.com")
GUARDIAN_API_KEY = os.getenv("GUARDIAN_API_KEY", "")
MAX_HTML_BYTES = 3_000_000
TIMEOUT = 10


def _cached(key: str, ttl: int, fn):
    """Cache en Redis (guarda JSON, porque el cache solo acepta texto)."""
    try:
        from finmate.db.cache import cached

        raw = cached(key, ttl, lambda: json.dumps(fn(), ensure_ascii=False))
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return fn()


# ── Texto de un artículo ────────────────────────────────────────────────

def _fetch_html(url: str) -> str:
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": UA, "Accept-Language": "es-CL,es;q=0.9,en;q=0.8"}) as c:
        r = c.get(url)
        if r.status_code != 200 or len(r.content) > MAX_HTML_BYTES:
            return ""
        ctype = r.headers.get("content-type", "")
        if "html" not in ctype and "xml" not in ctype:
            return ""
        return r.text


_PAYWALL_RE = re.compile(r'"isAccessibleForFree"\s*:\s*"?(false|False|FALSE)"?')


def is_paywalled(raw_html: str) -> bool:
    """True si la página se declara de pago (schema.org isAccessibleForFree=false).

    Algunos medios (ej. el DF) mandan el texto completo escondido en la página aunque
    sea de suscriptores: se respeta la marca y esos artículos se tratan como solo titular.
    """
    return bool(_PAYWALL_RE.search(raw_html or ""))


def extract_article(url: str, max_chars: int = 6000) -> str:
    """Texto principal de la página (o "" si no se pudo)."""
    if not url or not url.startswith(("http://", "https://")):
        return ""

    def _do():
        try:
            import trafilatura

            raw = _fetch_html(url)
            if not raw or is_paywalled(raw):
                return ""
            text = trafilatura.extract(raw, include_comments=False, include_tables=False,
                                       favor_precision=True) or ""
            return re.sub(r"\n{3,}", "\n\n", text).strip()
        except Exception as e:  # noqa: BLE001
            logger.info(f"No pude leer el artículo {url[:80]}: {e}")
            return ""

    text = _cached(f"finmate:article2:{url}", 6 * 3600, _do) or ""
    return text[:max_chars]


# ── Bing News (RSS) ─────────────────────────────────────────────────────

def _unwrap_bing(link: str) -> str:
    link = html.unescape(link)
    if "bing.com/news/apiclick" in link:
        u = parse_qs(urlparse(link).query).get("url", [""])[0]
        return u or link
    return link


def _tag(block: str, name: str) -> str:
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, re.S)
    if not m:
        return ""
    val = re.sub(r"^<!\[CDATA\[|\]\]>$", "", m.group(1).strip())
    return html.unescape(re.sub(r"<[^>]+>", "", val)).strip()


def bing_news(query: str, lang: str = "es", limit: int = 8) -> List[dict]:
    """[{title, url, source, date, summary}] de Bing News."""
    if not query:
        return []

    def _do():
        params = {"q": query, "format": "rss", "setlang": lang,
                  "cc": "CL" if lang == "es" else "US"}
        try:
            r = httpx.get("https://www.bing.com/news/search", params=params,
                          headers={"User-Agent": UA}, timeout=TIMEOUT)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            logger.info(f"Bing News falló para '{query}': {e}")
            return []
        out = []
        for block in re.findall(r"<item>(.*?)</item>", r.text, re.S):
            link = re.search(r"<link>(.*?)</link>", block, re.S)
            out.append({
                "title": _tag(block, "title"),
                "url": _unwrap_bing(link.group(1).strip()) if link else "",
                "source": _tag(block, "News:Source"),
                "date": _tag(block, "pubDate"),
                "summary": _tag(block, "description"),
            })
        return out

    return (_cached(f"finmate:bing:{lang}:{query.lower()}", 900, _do) or [])[:limit]


# ── The Guardian ────────────────────────────────────────────────────────

def guardian_search(query: str, limit: int = 3) -> List[dict]:
    if not GUARDIAN_API_KEY or not query:
        return []

    def _do():
        try:
            r = httpx.get("https://content.guardianapis.com/search", timeout=TIMEOUT, params={
                "q": query, "api-key": GUARDIAN_API_KEY, "order-by": "newest",
                "show-fields": "bodyText,trailText", "page-size": limit,
                "section": "business|technology|world|us-news",
            })
            r.raise_for_status()
            res = (r.json().get("response") or {}).get("results") or []
        except Exception as e:  # noqa: BLE001
            logger.info(f"The Guardian falló para '{query}': {e}")
            return []
        return [{
            "title": x.get("webTitle", ""),
            "url": x.get("webUrl", ""),
            "source": "The Guardian",
            "date": x.get("webPublicationDate", ""),
            "summary": (x.get("fields") or {}).get("trailText", ""),
            "text": (x.get("fields") or {}).get("bodyText", ""),
        } for x in res]

    return _cached(f"finmate:guardian:{query.lower()}", 1800, _do) or []


# ── SEC EDGAR ───────────────────────────────────────────────────────────

def _sec_get(url: str):
    return httpx.get(url, headers={"User-Agent": SEC_UA, "Accept-Encoding": "gzip"},
                     timeout=TIMEOUT, follow_redirects=True)


def _cik(symbol: str) -> Optional[str]:
    def _do():
        r = _sec_get("https://www.sec.gov/files/company_tickers.json")
        r.raise_for_status()
        return {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in r.json().values()}

    try:
        table = _cached("finmate:sec:tickers", 86400, _do) or {}
    except Exception as e:  # noqa: BLE001
        logger.info(f"SEC tickers falló: {e}")
        return None
    return table.get(symbol.upper().replace(".", "-"))


def sec_latest_filings(symbol: str, forms=("8-K", "10-Q", "10-K"), limit: int = 3) -> List[dict]:
    """Últimos reportes oficiales con un extracto del texto."""
    cik = _cik(symbol)
    if not cik:
        return []

    def _do():
        r = _sec_get(f"https://data.sec.gov/submissions/CIK{cik}.json")
        r.raise_for_status()
        recent = (r.json().get("filings") or {}).get("recent") or {}
        out = []
        for i, form in enumerate(recent.get("form", [])):
            if form not in forms:
                continue
            acc = recent["accessionNumber"][i].replace("-", "")
            doc = recent["primaryDocument"][i]
            base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}"
            out.append({"form": form, "date": recent["filingDate"][i],
                        "items": recent.get("items", [""] * (i + 1))[i],
                        "url": f"{base}/{doc}", "base": base})
            if len(out) >= limit:
                break
        return out

    try:
        filings = _cached(f"finmate:sec:filings:{cik}", 3600, _do) or []
    except Exception as e:  # noqa: BLE001
        logger.info(f"SEC filings falló para {symbol}: {e}")
        return []

    for f in filings[:1]:  # texto solo del más reciente (para no demorar)
        text = ""
        if f["form"] == "8-K":
            try:
                idx = _sec_get(f["base"] + "/index.json").json()
                ex = [x["name"] for x in (idx.get("directory") or {}).get("item", [])
                      if re.search(r"ex-?99", x.get("name", ""), re.I) and x["name"].endswith((".htm", ".html"))]
                if ex:
                    text = _sec_text(f["base"] + "/" + ex[0])
            except Exception:  # noqa: BLE001
                pass
        f["text"] = text or _sec_text(f["url"])
    return filings


def _sec_text(url: str, max_chars: int = 5000) -> str:
    def _do():
        try:
            import trafilatura

            r = _sec_get(url)
            if r.status_code != 200:
                return ""
            return (trafilatura.extract(r.text) or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    return (_cached(f"finmate:sec:doc:{url}", 86400, _do) or "")[:max_chars]


def to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
