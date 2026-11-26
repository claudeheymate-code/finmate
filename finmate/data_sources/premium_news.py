"""Titulares de los grandes medios económicos (RSS públicos y gratuitos).

WSJ, MarketWatch, Bloomberg, Financial Times, The Economist, Reuters (vía la
búsqueda de Google News, porque Reuters ya no publica RSS), CNBC y el Diario
Financiero. Cada RSS trae titular, un resumen corto y el link: el texto completo
está detrás del muro de pago y no se lee ni se republica. El bot cuenta de qué
trata con sus palabras y deja el link.

- `latest(hours)`: todas las noticias recientes, sin repetidas, de la más nueva a la más antigua.
- `top_stories(hours, limit)`: los temas que más medios están cubriendo (para los resúmenes).
- `search(query, hours)`: noticias que hablan de algo (para el bot).
- `items_for_symbols(symbols, names, now)`: noticias de los activos de los usuarios (para los avisos).
"""
from __future__ import annotations

import datetime as dt
import email.utils
import html
import logging
import re
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import httpx

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Finmate/1.0; +https://web-production-3626a.up.railway.app)"}
TIMEOUT = 12
CACHE_SECONDS = 600            # se vuelve a leer cada medio cada 10 minutos como máximo
MAX_PER_FEED = 40

_GN = "https://news.google.com/rss/search?q=when:24h+site:{site}&ceid=US:en&hl=en-US&gl=US"

# source: nombre que ve el usuario · lang: idioma de los titulares
FEEDS = [
    {"id": "wsj_markets", "source": "WSJ", "section": "Mercados", "lang": "en",
     "url": "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain"},
    {"id": "wsj_economy", "source": "WSJ", "section": "Economía", "lang": "en",
     "url": "https://feeds.content.dowjones.io/public/rss/socialeconomyfeed"},
    {"id": "wsj_business", "source": "WSJ", "section": "Empresas", "lang": "en",
     "url": "https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness"},
    {"id": "marketwatch", "source": "MarketWatch", "section": "Portada", "lang": "en",
     "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories"},
    {"id": "bloomberg_markets", "source": "Bloomberg", "section": "Mercados", "lang": "en",
     "url": "https://www.bloomberg.com/feeds/markets/news.rss"},
    {"id": "bloomberg_economics", "source": "Bloomberg", "section": "Economía", "lang": "en",
     "url": "https://www.bloomberg.com/feeds/economics/news.rss"},
    {"id": "ft_markets", "source": "Financial Times", "section": "Mercados", "lang": "en",
     "url": "https://www.ft.com/markets?format=rss"},
    {"id": "ft_economy", "source": "Financial Times", "section": "Economía global", "lang": "en",
     "url": "https://www.ft.com/global-economy?format=rss"},
    {"id": "economist_finance", "source": "The Economist", "section": "Finanzas y economía", "lang": "en",
     "url": "https://www.economist.com/finance-and-economics/rss.xml"},
    {"id": "economist_business", "source": "The Economist", "section": "Empresas", "lang": "en",
     "url": "https://www.economist.com/business/rss.xml"},
    {"id": "economist_leaders", "source": "The Economist", "section": "Editoriales", "lang": "en",
     "url": "https://www.economist.com/leaders/rss.xml"},
    {"id": "reuters_business", "source": "Reuters", "section": "Negocios", "lang": "en",
     "url": _GN.format(site="reuters.com/business")},
    {"id": "reuters_markets", "source": "Reuters", "section": "Mercados", "lang": "en",
     "url": _GN.format(site="reuters.com/markets")},
    {"id": "cnbc_top", "source": "CNBC", "section": "Portada", "lang": "en",
     "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html"},
    {"id": "df", "source": "Diario Financiero", "section": "Portada", "lang": "es",
     "url": "https://www.df.cl/noticias/site/list/port/rss.xml"},
]
SOURCES = sorted({f["source"] for f in FEEDS})

_cache: dict = {}            # feed id -> (timestamp, items)
_lock = threading.Lock()

_STOP = set("""a an the of to in on for and or with at by from as is are was be its it this that after
over into new more says said say amid about vs than up down his her their our your will can could may
de la el los las en y o con por para del al un una que se su sus es son más tras ante""".split())


# ---------------------------------------------------------------- lectura
def _clean(text: str, limit: int = 400) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= limit else t[: limit - 1].rsplit(" ", 1)[0] + "…"


def _date(text: str):
    if not text:
        return None
    try:
        d = email.utils.parsedate_to_datetime(text.strip())
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def parse_feed(xml_text: str | bytes, feed: dict) -> list[dict]:
    """Lee un RSS 2.0 (o Atom) y devuelve noticias normalizadas."""
    root = ET.fromstring(xml_text)
    nodes = root.findall(".//item")
    atom = False
    if not nodes:
        nodes = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        atom = True
    out = []
    for n in nodes:
        def get(tag):
            el = n.find(tag) if not atom else n.find("{http://www.w3.org/2005/Atom}" + tag)
            return (el.text or "") if el is not None else ""

        title = _clean(get("title"), 240)
        if not title:
            continue
        if atom:
            link_el = n.find("{http://www.w3.org/2005/Atom}link")
            link = link_el.get("href", "") if link_el is not None else ""
            published = _date(get("updated") or get("published"))
            summary = _clean(get("summary"))
        else:
            link = get("link").strip()
            published = _date(get("pubDate"))
            summary = _clean(get("description"))
        if feed["source"] == "Reuters":
            # Google News: "Titular - Reuters" y la descripción es solo un link
            title = re.sub(r"\s+-\s+Reuters\s*$", "", title)
            summary = ""
        if summary and _norm(summary) == _norm(title):
            summary = ""
        out.append({"title": title, "summary": summary, "url": link, "published": published,
                    "source": feed["source"], "section": feed["section"], "lang": feed["lang"],
                    "feed": feed["id"]})
    out.sort(key=lambda x: x["published"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
    return out[:MAX_PER_FEED]


def fetch_feed(feed: dict, client: httpx.Client | None = None) -> list[dict]:
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True)
    try:
        r = client.get(feed["url"])
        r.raise_for_status()
        return parse_feed(r.content, feed)
    finally:
        if own:
            client.close()


def _feed_items(feed: dict, client: httpx.Client) -> list[dict]:
    now = time.time()
    hit = _cache.get(feed["id"])
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        items = fetch_feed(feed, client)
    except Exception as e:  # noqa: BLE001
        logger.info(f"Grandes medios: no pude leer {feed['id']} ({type(e).__name__})")
        return hit[1] if hit else []      # si falla, se usa lo último que se leyó
    _cache[feed["id"]] = (now, items)
    return items


def _all_items(feeds=None) -> list[dict]:
    feeds = feeds or FEEDS
    with _lock, httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        with ThreadPoolExecutor(max_workers=6) as pool:
            chunks = list(pool.map(lambda f: _feed_items(f, client), feeds))
    return [it for chunk in chunks for it in chunk]


# ---------------------------------------------------------------- utilidades
def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def _tokens(text: str) -> set:
    return {w for w in _norm(text).split() if len(w) > 2 and w not in _STOP}


def _same_story(a: set, b: set) -> bool:
    if not a or not b:
        return False
    inter = len(a & b)
    return inter >= 3 and inter / min(len(a), len(b)) >= 0.5


def _dedupe(items: list[dict]) -> list[dict]:
    """Una noticia por titular (los medios repiten la misma en varias secciones)."""
    seen, out = set(), []
    for it in items:
        k = _norm(it["title"])[:90]
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def latest(hours: float = 24, now: dt.datetime | None = None, feeds=None) -> list[dict]:
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=hours)
    items = [it for it in _all_items(feeds) if it["published"] and it["published"] >= cutoff]
    items.sort(key=lambda x: x["published"], reverse=True)
    return _dedupe(items)


def top_stories(hours: float = 14, limit: int = 6, now: dt.datetime | None = None,
                items: list[dict] | None = None) -> list[dict]:
    """Los temas que más medios distintos están cubriendo. Cada tema trae su mejor titular,
    la lista de medios y cuántos son."""
    items = items if items is not None else latest(hours, now)
    clusters: list[dict] = []
    for it in items:
        toks = _tokens(it["title"] + " " + it.get("summary", "")[:120])
        for c in clusters:
            if _same_story(toks, c["tokens"]):
                c["items"].append(it)
                c["sources"].add(it["source"])
                break
        else:
            clusters.append({"tokens": toks, "items": [it], "sources": {it["source"]}})
    now = now or dt.datetime.now(dt.timezone.utc)

    def score(c):
        newest = max(i["published"] for i in c["items"])
        hours_old = (now - newest).total_seconds() / 3600
        markets = any(i["section"] in ("Mercados", "Economía", "Economía global", "Finanzas y economía") for i in c["items"])
        return len(c["sources"]) * 3 + (1 if markets else 0) - hours_old * 0.15

    clusters.sort(key=score, reverse=True)
    out = []
    for c in clusters[:limit]:
        # titular principal: el de una fuente "de mercado" con resumen, si hay
        main = sorted(c["items"], key=lambda i: (not i["summary"], i["source"] == "Reuters"))[0]
        out.append({**main, "sources": sorted(c["sources"]), "coverage": len(c["sources"])})
    return out


def search(query: str, hours: float = 72, source: str | None = None, limit: int = 10,
           now: dt.datetime | None = None) -> list[dict]:
    """Noticias de los grandes medios que mencionan el tema (todas las palabras importantes)."""
    words = [w for w in _tokens(query)] if query else []
    src = _norm(source) if source else ""
    out = []
    for it in latest(hours, now):
        if src and src not in _norm(it["source"]):
            continue
        hay = _norm(it["title"] + " " + it["summary"])
        if words and not all(re.search(rf"\b{re.escape(w)}", hay) for w in words):
            continue
        out.append(it)
        if len(out) >= limit:
            break
    return out


def items_for_symbols(symbols, names: dict, now: dt.datetime, hours: float = 3) -> list[dict]:
    """Noticias que nombran a una empresa seguida por algún usuario, en el formato de news_alerts.

    names: {símbolo: nombre corto de la empresa en minúsculas} (ej. {"AAPL": "apple"}).
    Se busca el nombre como palabra completa, o el ticker escrito en mayúsculas (si tiene 3+ letras).
    """
    out = []
    recent = latest(hours, now)
    for sym in symbols:
        sym = sym.upper()
        name = (names.get(sym) or "").lower()
        pats = []
        if name and len(name) > 2:
            pats.append(re.compile(rf"\b{re.escape(name)}\b", re.I))
        if len(sym) >= 3 and sym.isalpha():
            pats.append(re.compile(rf"\b{re.escape(sym)}\b"))
        if not pats:
            continue
        for it in recent:
            text = f"{it['title']} {it['summary']}"
            if any(p.search(text) for p in pats):
                out.append({"symbol": sym, "headline": it["title"], "summary": it["summary"],
                            "url": it["url"], "source": it["source"],
                            "datetime": it["published"].isoformat() if it["published"] else None,
                            "sentiment": None})
    return out


def ago(published: dt.datetime | None, now: dt.datetime | None = None) -> str:
    if not published:
        return ""
    now = now or dt.datetime.now(dt.timezone.utc)
    mins = int((now - published).total_seconds() // 60)
    if mins < 60:
        return f"hace {max(mins, 1)} min"
    if mins < 48 * 60:
        return f"hace {mins // 60} h"
    return f"hace {mins // 1440} días"


def health() -> dict:
    """Prueba de cada medio (Admin → Fuentes): cuántas noticias trae y la más nueva."""
    res = {}
    with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        def one(f):
            try:
                items = fetch_feed(f, client)
                _cache[f["id"]] = (time.time(), items)
                return f["id"], {"ok": bool(items), "items": len(items),
                                 "newest": items[0]["published"].isoformat() if items and items[0]["published"] else None}
            except Exception as e:  # noqa: BLE001
                return f["id"], {"ok": False, "error": f"{type(e).__name__}: {str(e)[:80]}"}

        with ThreadPoolExecutor(max_workers=6) as pool:
            for k, v in pool.map(one, FEEDS):
                res[k] = v
    return res
