"""Etapa A de fuentes: FRED, Banco Central, Marketaux y alertas de noticias.
Todas las respuestas HTTP están simuladas (no se llama a ninguna API real)."""
import datetime as dt

import pytest

NOW = dt.datetime(2026, 11, 16, 17, 0, tzinfo=dt.timezone.utc)


class FakeResp:
    encoding = "utf-8"

    def __init__(self, data):
        self._data = data

    @property
    def content(self):
        import json
        return json.dumps(self._data).encode("utf-8")

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class FakeClient:
    def __init__(self, router):
        self.router = router

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, params=None):
        return FakeResp(self.router(url, params or {}))


class FakeMessenger:
    def __init__(self):
        self.sent = []

    def send_message(self, to, body):
        self.sent.append((to, body))
        return True

    def send_template(self, to, sid, variables=None):
        self.sent.append((to, f"TEMPLATE {sid} {variables}"))
        return True


# ── FRED ────────────────────────────────────────────────────────────────

def test_fred_snapshot_salta_puntos_y_formatea(monkeypatch):
    from finmate.data_sources import fred
    from finmate.agent import macro_tools

    monkeypatch.setattr(fred, "FRED_API_KEY", "k")

    def router(url, params):
        assert params["api_key"] == "k" and params["file_type"] == "json"
        if params["series_id"] == "DFEDTARU":
            return {"observations": [{"date": "2026-11-15", "value": "."},
                                     {"date": "2026-11-14", "value": "4.00"}]}
        return {"observations": [{"date": "2026-10-01", "value": "2.9"}]}

    monkeypatch.setattr(fred.httpx, "Client", lambda timeout=10: FakeClient(router))
    data = fred.get_snapshot()
    fed = next(d for d in data if d["code"] == "FED_RATE")
    assert fed["value"] == 4.0 and fed["date"] == "2026-11-14"
    out = macro_tools.tool_get_us_macro()
    assert "Tasa Fed" in out and "4,00%" in out and "14 nov" in out


def test_fred_sin_clave_no_rompe(monkeypatch):
    from finmate.data_sources import fred
    from finmate.agent import macro_tools

    monkeypatch.setattr(fred, "FRED_API_KEY", "")
    assert fred.get_snapshot() == [] and fred.get_upcoming_releases() == []
    assert "no está configurada" in macro_tools.tool_get_us_macro()


def test_fred_calendario_filtra_ventana(monkeypatch):
    from finmate.data_sources import fred

    monkeypatch.setattr(fred, "FRED_API_KEY", "k")

    def router(url, params):
        if params["release_id"] == 10:
            return {"release_dates": [{"date": "2026-11-17"}, {"date": "2026-12-20"}]}
        return {"release_dates": []}

    monkeypatch.setattr(fred.httpx, "Client", lambda timeout=10: FakeClient(router))
    rel = fred.get_upcoming_releases(days_ahead=7, today=dt.date(2026, 11, 16))
    assert rel == [{"release_id": 10, "name": fred.RELEASES[10], "date": "2026-11-17"}]


# ── Banco Central ───────────────────────────────────────────────────────

def test_bcch_toma_ultimo_dato_ok(monkeypatch):
    from finmate.data_sources import bcch
    from finmate.agent import macro_tools

    monkeypatch.setattr(bcch, "BCCH_API_TOKEN", "t")

    def router(url, params):
        assert params["token"] == "t" and params["function"] == "GetSeries"
        return {"Codigo": 0, "Series": {"Obs": [
            {"indexDateString": "13-11-2026", "value": "945.12", "statusCode": "OK"},
            {"indexDateString": "14-11-2026", "value": "NaN", "statusCode": "ND"},
        ]}}

    monkeypatch.setattr(bcch.httpx, "Client", lambda timeout=10: FakeClient(router))
    data = bcch.get_snapshot()
    usd = next(d for d in data if d["code"] == "USD_CLP")
    assert usd["value"] == 945.12 and usd["date"] == "2026-11-13"
    out = macro_tools.tool_get_chile_indicators()
    assert "Dólar observado" in out and "$945,12" in out


def test_bcch_error_de_api(monkeypatch):
    from finmate.data_sources import bcch

    monkeypatch.setattr(bcch, "BCCH_API_TOKEN", "t")
    monkeypatch.setattr(bcch.httpx, "Client",
                        lambda timeout=10: FakeClient(lambda u, p: {"Codigo": -5, "Descripcion": "Invalid token"}))
    assert bcch.get_snapshot() == []


# ── Marketaux ───────────────────────────────────────────────────────────

def test_marketaux_normaliza_y_respeta_intervalo(monkeypatch):
    from finmate.data_sources import marketaux

    monkeypatch.setattr(marketaux, "MARKETAUX_API_KEY", "m")
    monkeypatch.setattr(marketaux, "_last_call", {"ts": 0.0})
    calls = []

    def fake_get(url, params=None, timeout=10):
        calls.append(params)
        return FakeResp({"data": [{"title": "Apple sube", "url": "u", "published_at": "2026-11-16T16:50:00Z",
                                   "entities": [{"symbol": "AAPL", "sentiment_score": 0.6},
                                                {"symbol": "ZZZ", "sentiment_score": 0}]}]})

    monkeypatch.setattr(marketaux.httpx, "get", fake_get)
    out = marketaux.get_news(["aapl", "msft"])
    assert [o["symbol"] for o in out] == ["AAPL"] and out[0]["sentiment"] == 0.6
    assert calls[0]["symbols"] == "AAPL,MSFT"
    assert marketaux.get_news(["aapl"]) == []  # segunda llamada inmediata: bloqueada por el intervalo
    assert len(calls) == 1


# ── Alertas de noticias ─────────────────────────────────────────────────

@pytest.fixture
def news_state(tmp_path, monkeypatch):
    from finmate.alerts import news_alerts

    monkeypatch.setattr(news_alerts, "STATE_FILE", str(tmp_path / "news.json"))
    monkeypatch.setattr(news_alerts, "TWILIO_TEMPLATE_MARKET_NOTIFY_SID", "")
    return news_alerts


def _item(sym, headline, minutes_ago, source="fh"):
    ts = (NOW - dt.timedelta(minutes=minutes_ago)).timestamp()
    return {"symbol": sym, "headline": headline, "summary": "", "url": f"https://{source}/{headline}",
            "source": source, "datetime": ts, "sentiment": None}


def test_noticias_calentamiento_luego_avisa_y_deduplica(news_state):
    na = news_state
    tracked = [(1, "whatsapp:+1", "AAPL"), (2, "whatsapp:+2", "AAPL"), (2, "whatsapp:+2", "NVDA")]
    m = FakeMessenger()

    # 1) Primera corrida: solo marca como visto.
    old = [_item("AAPL", "Old news", 10)]
    assert na.check_news_alerts(m, tracked, lambda s, n: old, lambda s, **k: [], now=NOW) == 0

    # 2) Noticia nueva, repetida por Marketaux con otra URL, más una vieja.
    fresh = [_item("AAPL", "Apple unveils new chip", 5), _item("NVDA", "Nvidia beats", 200)]
    dup = [{**_item("AAPL", "Apple unveils new chip!", 4, "mx"), "sentiment": 0.5}]
    n = na.check_news_alerts(m, tracked, lambda s, n: fresh, lambda s, **k: dup, now=NOW)
    assert n == 2  # usuarios 1 y 2, un mensaje cada uno
    bodies = {to: body for to, body in m.sent}
    assert "Apple unveils new chip" in bodies["whatsapp:+1"]
    assert bodies["whatsapp:+2"].count("AAPL") >= 1 and "Nvidia" not in bodies["whatsapp:+2"]

    # 3) Misma noticia otra vez: nada.
    assert na.check_news_alerts(m, tracked, lambda s, n: fresh, lambda s, **k: dup, now=NOW) == 0


def test_noticias_tope_diario(news_state, monkeypatch):
    na = news_state
    monkeypatch.setattr(na, "NEWS_ALERTS_MAX_PER_USER_PER_DAY", 1)
    tracked = [(1, "whatsapp:+1", "AAPL")]
    m = FakeMessenger()
    na.check_news_alerts(m, tracked, lambda s, n: [], lambda s, **k: [], now=NOW)  # calentamiento
    assert na.check_news_alerts(m, tracked, lambda s, n: [_item("AAPL", "a", 1)], lambda s, **k: [], now=NOW) == 1
    assert na.check_news_alerts(m, tracked, lambda s, n: [_item("AAPL", "b", 1)], lambda s, **k: [], now=NOW) == 0


def test_noticias_con_template_encola(news_state, monkeypatch, tmp_path):
    na = news_state
    from finmate.alerts import pending

    monkeypatch.setattr(na, "TWILIO_TEMPLATE_MARKET_NOTIFY_SID", "HXtest")
    if hasattr(pending, "STATE_FILE"):
        monkeypatch.setattr(pending, "STATE_FILE", str(tmp_path / "pending.json"))
    tracked = [(1, "whatsapp:+1", "AAPL")]
    m = FakeMessenger()
    na.check_news_alerts(m, tracked, lambda s, n: [], lambda s, **k: [], now=NOW)
    na.check_news_alerts(m, tracked, lambda s, n: [_item("AAPL", "x", 1)], lambda s, **k: [], now=NOW)
    assert m.sent[-1][1].startswith("TEMPLATE HXtest")
    assert "x" in (pending.pop_pending("whatsapp:+1") or "")


# ── Recordatorios macro ─────────────────────────────────────────────────

def test_recordatorio_macro_solo_a_seguidores():
    from finmate.alerts.macro_alerts import check_macro_reminders

    m = FakeMessenger()
    rel = [{"release_id": 10, "name": "Inflación EE.UU. (IPC)", "date": "2026-11-17"}]
    followers = {"CPI_US": [(1, "whatsapp:+1")], "NFP": [(2, "whatsapp:+2")]}
    n = check_macro_reminders(m, today=dt.date(2026, 11, 16), releases=rel, followers=followers)
    assert n == 1 and m.sent[0][0] == "whatsapp:+1" and "mañana" in m.sent[0][1]


# ── Integración con la DB y el agente ───────────────────────────────────

def test_simbolos_seguidos_unen_portafolio_y_watchlist():
    from finmate.db import repository as repo

    u = repo.get_or_create_user("whatsapp:+56911112222")
    repo.add_or_update_holding(u.id, "aapl", 1, 100)
    repo.add_to_watchlist(u.id, "AAPL")
    repo.add_to_watchlist(u.id, "nvda")
    mine = [(s) for uid, _p, s in repo.get_all_tracked_symbols() if uid == u.id]
    assert mine == ["AAPL", "NVDA"]


def test_tools_registradas():
    from finmate.agent.tools import TOOLS, run_tool

    names = {t["name"] for t in TOOLS}
    assert {"get_us_macro", "get_chile_indicators", "get_us_release_calendar"} <= names
    assert isinstance(run_tool("get_us_macro", {}), str)
