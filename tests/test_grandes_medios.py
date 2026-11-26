"""Grandes medios (RSS): lectura de cada formato, temas más cubiertos, búsqueda,
noticias de los activos, tool del bot, resúmenes de jornada y Admin → Fuentes."""
import datetime as dt
import os

import pytest

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "rss")
NOW = dt.datetime(2026, 11, 26, 1, 0, tzinfo=dt.timezone.utc)
FEED_FOR = {"wsj": "wsj_markets", "bloomberg": "bloomberg_markets", "ft": "ft_economy",
            "economist": "economist_finance", "reuters": "reuters_business", "df": "df", "cnbc": "cnbc_top"}


def _feed(fid):
    from finmate.data_sources import premium_news

    return next(f for f in premium_news.FEEDS if f["id"] == fid)


def _all_fixture_items():
    from finmate.data_sources import premium_news

    out = []
    for name, fid in FEED_FOR.items():
        out += premium_news.parse_feed(open(os.path.join(FIX, name + ".xml"), "rb").read(), _feed(fid))
    return out


@pytest.fixture
def media(monkeypatch):
    from finmate.data_sources import premium_news

    items = _all_fixture_items()
    monkeypatch.setattr(premium_news, "_all_items", lambda feeds=None: items)
    return premium_news


def test_lee_cada_formato():
    from finmate.data_sources import premium_news

    for name, fid in FEED_FOR.items():
        items = premium_news.parse_feed(open(os.path.join(FIX, name + ".xml"), "rb").read(), _feed(fid))
        assert items, name
        it = items[0]
        assert it["title"] and it["url"].startswith("http") and it["published"].tzinfo, name
        assert "<" not in it["title"] and "<" not in it["summary"], name
    reuters = premium_news.parse_feed(open(os.path.join(FIX, "reuters.xml"), "rb").read(), _feed("reuters_business"))
    assert all(not r["title"].endswith("- Reuters") and r["summary"] == "" for r in reuters)
    eco = premium_news.parse_feed(open(os.path.join(FIX, "economist.xml"), "rb").read(), _feed("economist_finance"))
    assert eco[0]["title"] == eco[0]["title"].strip() and eco[0]["summary"]


def test_temas_que_mas_medios_cubren(media):
    top = media.top_stories(hours=14, limit=5, now=NOW)
    assert top and top[0]["coverage"] >= 2
    spacex = next(t for t in top if "SpaceX" in t["title"])
    assert set(spacex["sources"]) == {"CNBC", "Reuters"}
    assert top[0]["coverage"] >= top[-1]["coverage"]


def test_busqueda_por_tema_y_medio(media):
    hits = media.search("gold", hours=24, now=NOW)
    assert hits and all("gold" in (h["title"] + h["summary"]).lower() for h in hits)
    only_cnbc = media.search("spacex", hours=24, source="cnbc", now=NOW)
    assert only_cnbc and {h["source"] for h in only_cnbc} == {"CNBC"}
    assert len(media.search("spacex", hours=24, now=NOW)) == 2
    assert media.search("palabra que no existe xyz", hours=24, now=NOW) == []


def test_noticias_de_activos_por_nombre_de_empresa(media):
    items = media.items_for_symbols(["NVDA", "M"], {"NVDA": "nvidia", "M": "macy"}, NOW, hours=24)
    syms = {i["symbol"] for i in items}
    assert syms == {"NVDA", "M"}
    assert any(i["source"] == "Reuters" and "Nvidia" in i["headline"] for i in items)
    assert all(i["headline"] and i["source"] for i in items)
    # una empresa sin nombre ni ticker reconocible no trae nada
    assert media.items_for_symbols(["X"], {}, NOW) == []


def test_tool_del_bot(media, monkeypatch):
    from finmate.agent import tools

    monkeypatch.setattr(media, "latest", lambda hours=24, now=None, feeds=None:
                        media._dedupe(sorted([i for i in _all_fixture_items() if i["published"]],
                                             key=lambda x: x["published"], reverse=True)))
    out = tools.run_tool("get_premium_news", {"query": "gold"})
    assert "[WSJ]" in out or "[Bloomberg]" in out
    assert "http" in out and "artículo completo es de pago" in out
    general = tools.run_tool("get_premium_news", {})
    assert "también en" in general
    none = tools.run_tool("get_premium_news", {"query": "zzzz inexistente"})
    assert "No encontré" in none


def test_resumen_de_jornada_incluye_grandes_medios(monkeypatch):
    from finmate.services import daily_brief

    facts = {"grandes_medios": [
        {"title": "Gold Edges Lower Amid Rate Hike Bets", "summary": "", "source": "WSJ",
         "sources": ["Bloomberg", "WSJ"], "lang": "en", "url": ""},
        {"title": "Chile tendrá Sala Cuna Universal", "summary": "", "source": "Diario Financiero",
         "sources": ["Diario Financiero"], "lang": "es", "url": ""},
    ]}
    monkeypatch.setattr(daily_brief, "_spanish_titles",
                        lambda st: ["El oro baja por apuestas de alza de tasas" if s["lang"] == "en" else s["title"] for s in st])
    text = daily_brief.bullets(facts, "end")
    assert "🌎 *En los grandes medios*" in text
    assert "El oro baja por apuestas de alza de tasas (Bloomberg, WSJ)" in text
    assert "Chile tendrá Sala Cuna Universal (Diario Financiero)" in text
    assert "grandes medios" in daily_brief._facts_for_prompt(facts)


def test_traduccion_sin_claude_deja_el_original(monkeypatch):
    from finmate.agent import orchestrator
    from finmate.services import daily_brief

    monkeypatch.setattr(orchestrator, "_client", None)
    st = [{"title": "Gold Edges Lower", "lang": "en"}, {"title": "Dólar sube", "lang": "es"}]
    assert daily_brief._spanish_titles(st) == ["Gold Edges Lower", "Dólar sube"]


def test_avisos_usan_grandes_medios(monkeypatch):
    from finmate.alerts import news_alerts
    from finmate.db.state_store import save_json

    save_json(news_alerts.STATE_FILE, {"seen": {}, "daily": {}})
    delivered = []
    from finmate.services import news_profile

    monkeypatch.setattr(news_profile, "deliver", lambda uid, phone, item, m, **k: delivered.append(item) or "chat")
    fresh = (NOW - dt.timedelta(minutes=10)).isoformat()
    premium = lambda symbols, now: [{"symbol": "KNTK", "headline": "Targa in talks to buy Kinetik", "summary": "",
                                     "url": "https://bloomberg.com/x", "source": "Bloomberg", "datetime": fresh,
                                     "sentiment": None}]
    sent = news_alerts.check_news_alerts(messenger=object(), tracked=[(1, "+56911111111", "KNTK")],
                                         finnhub_fetch=lambda s, n: [], marketaux_fetch=lambda s, published_after=None: [],
                                         now=NOW, premium_fetch=premium)
    assert sent == 1 and delivered and "Bloomberg" in (delivered[0].get("text") or str(delivered[0]))


def test_fuente_en_el_admin(monkeypatch):
    from finmate.admin import sources
    from finmate.data_sources import premium_news

    assert "premium" in [s["id"] for s in sources.catalog()]
    monkeypatch.setattr(premium_news, "health", lambda: {"a": {"ok": True, "items": 20}, "b": {"ok": False, "error": "x"}})
    ok, detail = sources._t_premium()
    assert ok and "1/2 feeds" in detail and "fallan: b" in detail
