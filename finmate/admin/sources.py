"""Catálogo de fuentes de información de Finmate (panel admin → Fuentes).

Cada fuente dice qué entrega, para qué la usa el bot, su plan/límite, si está
configurada en Railway y tiene una prueba rápida en vivo (sin gastar más de
una llamada). Las notas e ideas del administrador se guardan en kv_state.
"""
import os
import time

import httpx

from config import settings
from finmate.db.state_store import load_json, save_json

NOTES_KEY = "admin:source_notes"
TIMEOUT = 6


def _env(name: str) -> bool:
    return bool(getattr(settings, name, "") or os.getenv(name, ""))


def _t_finnhub():
    r = httpx.get("https://finnhub.io/api/v1/quote", params={"symbol": "AAPL", "token": settings.FINNHUB_API_KEY}, timeout=TIMEOUT)
    j = r.json() if r.status_code == 200 else {}
    return r.status_code == 200 and bool(j.get("c")), f"AAPL ${j.get('c')}" if j.get("c") else f"HTTP {r.status_code}"


def _t_fred():
    r = httpx.get("https://api.stlouisfed.org/fred/series/observations", timeout=TIMEOUT, params={
        "series_id": "FEDFUNDS", "api_key": settings.FRED_API_KEY, "file_type": "json", "sort_order": "desc", "limit": 1})
    obs = (r.json().get("observations") or [{}])[0] if r.status_code == 200 else {}
    return r.status_code == 200 and bool(obs), f"Tasa Fed {obs.get('value')}% ({obs.get('date')})" if obs else f"HTTP {r.status_code}"


def _t_bcch():
    from finmate.data_sources import bcch

    snap = bcch.get_snapshot()
    return bool(snap), (f"{snap[0].get('name')}: {snap[0].get('value')}" if snap else "sin datos")


def _t_marketaux():
    r = httpx.get("https://api.marketaux.com/v1/news/all", timeout=TIMEOUT, params={
        "symbols": "AAPL", "limit": 1, "api_token": settings.MARKETAUX_API_KEY})
    return r.status_code == 200, "ok (gasta 1 de 100 llamadas diarias)" if r.status_code == 200 else f"HTTP {r.status_code}"


def _t_alpha():
    r = httpx.get("https://www.alphavantage.co/query", timeout=TIMEOUT, params={
        "function": "GLOBAL_QUOTE", "symbol": "IBM", "apikey": settings.ALPHA_VANTAGE_API_KEY})
    j = r.json() if r.status_code == 200 else {}
    ok = bool(j.get("Global Quote"))
    return ok, "ok" if ok else (j.get("Note") or j.get("Information") or f"HTTP {r.status_code}")[:120]


def _t_bing():
    from finmate.data_sources.news_content import bing_news

    items = bing_news("mercados financieros", "es", 3)
    return bool(items), f"{len(items)} noticias · ej: {items[0]['title'][:60]}" if items else "sin resultados"


def _t_guardian():
    from finmate.data_sources.news_content import guardian_search

    items = guardian_search("stock market", 1)
    return bool(items), (items[0]["title"][:70] if items else "sin resultados")


def _t_sec():
    from finmate.data_sources.news_content import sec_latest_filings

    f = sec_latest_filings("AAPL", limit=1)
    return bool(f), (f"{f[0]['form']} del {f[0]['date']}" if f else "sin resultados")


def _t_article():
    from finmate.data_sources.news_content import bing_news, extract_article

    items = bing_news("economía Chile", "es", 3)
    for it in items:
        text = extract_article(it["url"], max_chars=2000)
        if text:
            return True, f"leyó {len(text)} caracteres de {it.get('source') or 'un medio'}"
    return False, "no pudo leer los artículos de prueba"


def _t_podcast():
    from finmate.podcasts.catalog import PODCASTS

    r = httpx.get(PODCASTS["primer_click"]["rss"], timeout=TIMEOUT, follow_redirects=True)
    return r.status_code == 200 and "<item>" in r.text, "feed ok" if r.status_code == 200 else f"HTTP {r.status_code}"


def _t_cmf_fondos():
    """Estado de los fondos guardados; si no hay datos recientes, baja el último día publicado."""
    import datetime as dt

    from finmate.data_sources import cmf_fondos
    from finmate.services import funds

    today = funds._today()

    def history_text(st):
        if st.get("backfill"):
            m = st.get("history_months", 0)
            return (f"historia: {m} meses guardados" + ("" if m >= 12 else
                    " (para completarla, importa los Excel de la CMF abajo)"))
        pr = st.get("progress") or {}
        started = funds.start_backfill_thread()
        if pr.get("error") and not st.get("busy"):
            return f"historia: error al bajar ({pr['error'][:120]}); se reintenta"
        if pr.get("total"):
            return f"cargando historia: {pr.get('done', 0)}/{pr['total']} meses"
        return "cargando historia de 13 meses en segundo plano" if started or st.get("busy") else "historia pendiente"

    st = funds.status()
    if st["latest"] and dt.date.fromisoformat(st["latest"]) >= today - dt.timedelta(days=5):
        latest = dt.date.fromisoformat(st["latest"])
        return True, (f"{st['dates']} fechas guardadas (última {latest.strftime('%d-%m')})"
                      f"{' · actualizando ahora' if st['busy'] else ''} · {history_text(st)}")
    for back in range(1, 6):
        day = today - dt.timedelta(days=back)
        content = cmf_fondos.download_day(day)
        if content is None:
            continue
        rows = cmf_fondos.parse_xls(content)
        funds.store_day(day, rows)
        n_admin = len({r["admin"] for r in rows})
        return True, (f"{len(rows):,} series de {n_admin} administradoras ({day.strftime('%d-%m')})".replace(",", ".")
                      + " · " + history_text(funds.status()))
    return False, "la CMF respondió, pero sin datos en los últimos 5 días"

def _t_claude():
    from config.settings import ANTHROPIC_MODEL_DEFAULT

    return bool(settings.ANTHROPIC_API_KEY), f"modelo por defecto: {ANTHROPIC_MODEL_DEFAULT}"


SOURCES = [
    {"id": "finnhub", "name": "Finnhub", "kind": "Precios y noticias", "env": "FINNHUB_API_KEY", "test": _t_finnhub,
     "gives": "Cotizaciones de acciones EE.UU., precios en tiempo real (WebSocket), noticias por empresa con resumen, perfil y sector.",
     "used_for": "Precios del portafolio y watchlist, alertas en tiempo real, «por qué se movió», noticias de tus activos.",
     "plan": "Gratis: 60 llamadas/min, WebSocket hasta 50 símbolos.", "url": "https://finnhub.io/docs/api"},
    {"id": "marketaux", "name": "Marketaux", "kind": "Noticias", "env": "MARKETAUX_API_KEY", "test": _t_marketaux,
     "gives": "Noticias por empresa con puntaje de sentimiento.", "used_for": "Avisos de noticias de tus activos (complementa a Finnhub).",
     "plan": "Gratis: 100 llamadas/día (el bot espera 20 min entre consultas).", "url": "https://www.marketaux.com/documentation"},
    {"id": "bing", "name": "Bing News (RSS)", "kind": "Noticias", "env": None, "test": _t_bing,
     "gives": "Búsqueda de noticias por tema en español e inglés, con link directo al medio.",
     "used_for": "Responder «qué pasó con…» sobre cualquier tema, no solo empresas.", "plan": "Sin clave.",
     "url": "https://www.bing.com/news"},
    {"id": "articles", "name": "Lectura de artículos (trafilatura)", "kind": "Contenido", "env": None, "test": _t_article,
     "gives": "El texto completo de una noticia a partir de su link.", "used_for": "Que el bot lea el contenido y no se quede en el titular.",
     "plan": "Sin clave. No funciona con medios con muro de pago.", "url": "https://trafilatura.readthedocs.io"},
    {"id": "guardian", "name": "The Guardian", "kind": "Contenido", "env": "GUARDIAN_API_KEY", "test": _t_guardian,
     "gives": "Artículos completos de economía, tecnología y mundo.", "used_for": "Contexto internacional con texto completo.",
     "plan": "Gratis (uso no comercial): 500 llamadas/día.", "url": "https://open-platform.theguardian.com/access/"},
    {"id": "sec", "name": "SEC EDGAR", "kind": "Reportes oficiales", "env": None, "test": _t_sec,
     "gives": "Reportes oficiales de empresas de EE.UU. (8-K, 10-Q, 10-K) y sus comunicados de resultados.",
     "used_for": "Resultados trimestrales y anuncios oficiales con la fuente primaria.", "plan": "Sin clave (máx. 10 consultas/seg).",
     "url": "https://www.sec.gov/edgar/sec-api-documentation"},
    {"id": "fred", "name": "FRED (Fed de St. Louis)", "kind": "Macro EE.UU.", "env": "FRED_API_KEY", "test": _t_fred,
     "gives": "Datos macro de EE.UU. (tasas, inflación, empleo, PIB) y calendario oficial de publicaciones.",
     "used_for": "Indicadores macro y recordatorios de publicaciones (IPC, NFP, FOMC).", "plan": "Gratis.",
     "url": "https://fred.stlouisfed.org/docs/api/fred/"},
    {"id": "bcch", "name": "Banco Central de Chile", "kind": "Macro Chile", "env": "BCCH_API_TOKEN", "test": _t_bcch,
     "gives": "Dólar observado, UF, TPM e IPC.", "used_for": "Indicadores chilenos.", "plan": "Gratis con registro.",
     "url": "https://si3.bcentral.cl/estadisticas/Principal1/Web_Services/index_EN.htm"},
    {"id": "cmf_fondos", "name": "CMF — Fondos mutuos", "kind": "Fondos Chile", "env": None, "test": _t_cmf_fondos,
     "gives": "Valor cuota, patrimonio y partícipes de todas las series de todos los fondos mutuos de Chile (~2.900 series, ~22 administradoras).",
     "used_for": "Buscar y comparar fondos de cualquier banco, rentabilidad 1 día / 1 mes / año / 12 meses, ranking y «mis fondos».",
     "plan": "Público, sin clave. Publica con 1 día de retraso; el bot baja 1 archivo al día (~700 KB).",
     "url": "https://www.cmfchile.cl/institucional/estadisticas/fm.bpr_menu.php"},
    {"id": "alpha", "name": "Alpha Vantage", "kind": "Precios y calendario", "env": "ALPHA_VANTAGE_API_KEY", "test": _t_alpha,
     "gives": "Cotizaciones, calendario de resultados, noticias con sentimiento.", "used_for": "Respaldo del motor de alertas generales.",
     "plan": "Gratis: 25 llamadas/día.", "url": "https://www.alphavantage.co/documentation/"},
    {"id": "podcast", "name": "Primer Click (DF) — RSS", "kind": "Podcast", "env": None, "test": _t_podcast,
     "gives": "Episodios diarios del podcast del Diario Financiero.", "used_for": "Resumen diario del podcast para quienes lo siguen.",
     "plan": "Sin clave. Transcripción opcional con OpenAI.", "url": "https://anchor.fm/s/713eaf3c/podcast/rss"},
    {"id": "claude", "name": "Claude (Anthropic)", "kind": "Inteligencia", "env": "ANTHROPIC_API_KEY", "test": _t_claude,
     "gives": "El modelo que entiende los mensajes, usa las fuentes y redacta.", "used_for": "Todo el chat del bot.",
     "plan": "Pago por uso (créditos prepagados).", "url": "https://platform.claude.com"},
]


def catalog() -> list:
    notes = load_json(NOTES_KEY, {}) or {}
    out = []
    for s in SOURCES:
        configured = True if s["env"] is None else _env(s["env"])
        out.append({k: v for k, v in s.items() if k != "test"} | {
            "configured": configured, "needs_key": s["env"] is not None, "note": notes.get(s["id"], ""),
        })
    return out


def test_source(source_id: str) -> dict:
    src = next((s for s in SOURCES if s["id"] == source_id), None)
    if src is None:
        return {"ok": False, "detail": "Fuente desconocida"}
    if src["env"] and not _env(src["env"]):
        return {"ok": False, "detail": f"Falta la variable {src['env']} en Railway"}
    t0 = time.time()
    try:
        ok, detail = src["test"]()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"error: {str(e)[:140]}"
    return {"ok": bool(ok), "detail": detail, "ms": int((time.time() - t0) * 1000)}


def save_note(source_id: str, note: str) -> None:
    if source_id != "_ideas" and not any(s["id"] == source_id for s in SOURCES):
        raise ValueError("Fuente desconocida")
    notes = load_json(NOTES_KEY, {}) or {}
    notes[source_id] = (note or "").strip()[:2000]
    save_json(NOTES_KEY, notes)


def get_ideas() -> str:
    return (load_json(NOTES_KEY, {}) or {}).get("_ideas", "")
