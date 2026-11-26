"""Tools del agente para leer noticias completas (ver data_sources/news_content.py)."""
import logging

from finmate.data_sources import news_content as nc

logger = logging.getLogger(__name__)

TEXT_PER_ARTICLE = 1800


def _finnhub_items(symbol: str) -> list:
    try:
        from finmate.agent.market_tools import _get_news

        return [{"title": n.get("headline", ""), "url": n.get("url", ""),
                 "source": n.get("source", ""), "summary": n.get("summary", ""),
                 "date": n.get("datetime", "")} for n in (_get_news(symbol) or [])]
    except Exception as e:  # noqa: BLE001
        logger.info(f"Finnhub news falló para {symbol}: {e}")
        return []


def tool_get_news_detail(tool_input: dict) -> str:
    """Noticias recientes con el contenido de los artículos, para resumir."""
    query = (tool_input.get("query") or "").strip()
    symbol = (tool_input.get("symbol") or "").strip().upper()
    if not query and not symbol:
        return "Necesito un tema o un símbolo para buscar noticias."

    items = []
    if symbol:
        items += _finnhub_items(symbol)
    q = query or symbol
    try:  # titulares de los grandes medios primero (solo titular y resumen)
        from finmate.data_sources import premium_news as pn

        items += [{"title": f"{it['title']} ({it['source']})", "url": it["url"], "source": it["source"],
                   "summary": it["summary"], "date": it["published"].isoformat() if it["published"] else ""}
                  for it in pn.search(q, hours=72, limit=4)]
    except Exception as e:  # noqa: BLE001
        logger.info(f"Grandes medios no disponibles: {e}")
    items += nc.guardian_search(q)
    items += nc.bing_news(q, "es")
    items += nc.bing_news(q, "en")

    seen, picked = set(), []
    for it in items:
        key = (it.get("title") or "").lower()[:70]
        if not it.get("url") or key in seen:
            continue
        seen.add(key)
        picked.append(it)
    if not picked:
        return f"No encontré noticias recientes sobre {q}."

    out, with_text = [], 0
    for it in picked[:8]:
        text = it.get("text") or ""
        if not text and with_text < 3:
            text = nc.extract_article(it["url"])
        if text:
            with_text += 1
        body = (text[:TEXT_PER_ARTICLE] + "…") if len(text) > TEXT_PER_ARTICLE else text
        out.append(
            f"### {it.get('title')}\nFuente: {it.get('source') or '?'} · {it.get('date') or ''}\n"
            f"Link: {it['url']}\n"
            + (f"Contenido:\n{body}" if body else f"Resumen: {it.get('summary') or '(sin resumen)'}")
        )
        if len(out) >= 6:
            break
    return ("Noticias encontradas (resume con tus palabras para el usuario; no copies "
            "párrafos completos; menciona la fuente y comparte el link si lo pide):\n\n"
            + "\n\n".join(out))


def tool_read_article(tool_input: dict) -> str:
    url = (tool_input.get("url") or "").strip()
    text = nc.extract_article(url, max_chars=8000)
    if not text:
        return "No pude leer ese artículo (puede tener muro de pago o bloquear lectores)."
    return ("Contenido del artículo (resúmelo con tus palabras; no lo copies entero):\n\n" + text)


def tool_get_company_filings(tool_input: dict) -> str:
    symbol = (tool_input.get("symbol") or "").strip().upper()
    if not symbol:
        return "Necesito el símbolo de la empresa (ej: AAPL)."
    filings = nc.sec_latest_filings(symbol)
    if not filings:
        return f"No encontré reportes en la SEC para {symbol} (solo empresas que reportan en EE.UU.)."
    lines = [f"Últimos reportes oficiales de {symbol} en la SEC:"]
    for f in filings:
        lines.append(f"- {f['form']} del {f['date']}" + (f" (ítems {f['items']})" if f.get("items") else "")
                     + f": {f['url']}")
    if filings[0].get("text"):
        lines.append(f"\nExtracto del más reciente ({filings[0]['form']}):\n{filings[0]['text']}")
    return "\n".join(lines)


def tool_get_premium_news(tool_input: dict) -> str:
    """Titulares y resúmenes de WSJ, Bloomberg, FT, The Economist, Reuters, CNBC, MarketWatch y DF."""
    from finmate.data_sources import premium_news as pn

    query = (tool_input.get("query") or "").strip()
    source = (tool_input.get("fuente") or "").strip() or None
    try:
        hours = float(tool_input.get("horas") or (72 if query else 24))
    except (TypeError, ValueError):
        hours = 24
    hours = max(1, min(hours, 168))
    try:
        if query or source:
            items = pn.search(query, hours=hours, source=source, limit=10)
        else:
            items = [dict(s) for s in pn.top_stories(hours=min(hours, 24), limit=8)]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"get_premium_news falló: {e}")
        return "No pude revisar los grandes medios en este momento."
    if not items:
        what = f"sobre «{query}»" if query else "recientes"
        return (f"No encontré noticias {what} en WSJ, Bloomberg, FT, The Economist, Reuters, CNBC, MarketWatch ni DF "
                f"en las últimas {int(hours)} horas. Puedes probar get_news_detail para una búsqueda más amplia.")
    lines = ["Titulares de los grandes medios (solo titular y resumen: el artículo completo es de pago; "
             "cuéntalo con tus palabras, en español, y deja el link):"]
    for it in items:
        cov = f" · también en {', '.join(s for s in it['sources'] if s != it['source'])}" if it.get("coverage", 1) > 1 else ""
        lines.append(f"• [{it['source']}] {it['title']} ({pn.ago(it.get('published'))}){cov}")
        if it.get("summary"):
            lines.append(f"  {it['summary']}")
        if it.get("url"):
            lines.append(f"  {it['url']}")
    return "\n".join(lines)
