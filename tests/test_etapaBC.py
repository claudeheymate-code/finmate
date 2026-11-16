"""Etapa B (precios en tiempo real) y Etapa C (resumen de podcasts).
Sin red: WebSocket, Finnhub, OpenAI, Claude y Twilio están simulados."""
import datetime as dt
import json

import pytest


class FakeMessenger:
    def __init__(self):
        self.sent = []

    def send_message(self, to, body):
        self.sent.append((to, body))
        return True

    def send_template(self, to, sid, variables=None):
        self.sent.append((to, f"TEMPLATE {variables}"))
        return True


# ── Etapa B ─────────────────────────────────────────────────────────────

def _stream(now=1_000_000.0, symbols=("NVDA", "AAPL")):
    from finmate.realtime.price_stream import PriceStream

    clock = {"t": now}
    s = PriceStream(api_key="k", symbols_fn=lambda: list(symbols),
                    prev_close_fn=lambda sym: {"NVDA": 100.0, "AAPL": 200.0}.get(sym),
                    clock=lambda: clock["t"])
    return s, clock


def test_trades_actualizan_precio_y_calculan_variacion():
    s, clock = _stream()
    s.refresh_subscriptions(send=lambda m: None)
    s.handle_message(json.dumps({"type": "trade", "data": [
        {"s": "NVDA", "p": 105.5, "t": int(clock["t"] * 1000)},
        {"s": "NVDA", "p": 104.0, "t": int((clock["t"] - 5) * 1000)},  # más vieja: se ignora
    ]}))
    q = s.get_quote("NVDA")
    assert q["price"] == 105.5 and round(q["change_pct"], 2) == 5.5 and q["is_closed"] is False
    assert s.get_quote("AAPL") is None            # sin operaciones todavía
    s.handle_message(json.dumps({"type": "ping"}))  # mensajes de control no rompen
    s.handle_message("no-json")
    clock["t"] += 600                              # precio viejo: no se usa
    assert s.get_quote("NVDA") is None


def test_suscripciones_altas_bajas_y_filtro():
    from finmate.realtime.price_stream import PriceStream

    syms = {"v": ["nvda", "BTC-USD", "aapl"]}
    s = PriceStream(api_key="k", symbols_fn=lambda: syms["v"], prev_close_fn=lambda x: 1.0, max_symbols=50)
    sent = []
    s.refresh_subscriptions(send=sent.append)
    assert [json.loads(m) for m in sent] == [{"type": "subscribe", "symbol": "AAPL"},
                                            {"type": "subscribe", "symbol": "NVDA"}]
    sent.clear()
    syms["v"] = ["NVDA", "MSFT"]
    s.refresh_subscriptions(send=sent.append)
    assert {"type": "subscribe", "symbol": "MSFT"} in [json.loads(m) for m in sent]
    assert {"type": "unsubscribe", "symbol": "AAPL"} in [json.loads(m) for m in sent]


def test_tope_de_50_simbolos():
    from finmate.realtime.price_stream import PriceStream

    many = [f"S{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(60)]
    s = PriceStream(api_key="k", symbols_fn=lambda: many, prev_close_fn=lambda x: 1.0, max_symbols=50)
    assert len(s.wanted_symbols()) == 50


def test_alerta_en_tiempo_real_usa_mismo_estado_que_el_chequeo(tmp_path, monkeypatch):
    from finmate.alerts import watchlist_alerts as wa

    monkeypatch.setattr(wa, "STATE_FILE", str(tmp_path / "wl.json"))
    monkeypatch.setattr(wa, "TWILIO_TEMPLATE_WATCHLIST_ALERT_SID", "")
    monkeypatch.setattr(wa, "get_all_watchlist_entries", lambda: [(99999, "whatsapp:+7", "NVDA"),
                                                                  (99999, "whatsapp:+7", "AAPL")])
    s, clock = _stream()
    s.refresh_subscriptions(send=lambda m: None)
    s.handle_message(json.dumps({"type": "trade", "data": [{"s": "NVDA", "p": 94.0, "t": int(clock["t"] * 1000)}]}))
    m = FakeMessenger()
    sent = wa.check_watchlist_alerts(m, quote_fn=s.get_quote)
    assert sent == 1 and "NVDA" in m.sent[0][1]   # AAPL sin dato en vivo: se salta
    # El chequeo periódico (u otra evaluación) no repite la alerta del día.
    assert wa.check_watchlist_alerts(m, quote_fn=lambda sym: {"price": 94.0, "change_pct": -6.0, "is_closed": False} if sym == "NVDA" else None) == 0


def test_evaluate_sin_datos_no_llama():
    s, _ = _stream()
    calls = []
    s.evaluate_fn = lambda quote_fn: calls.append(1) or 0
    assert s.evaluate() == 0 and calls == []


def test_quotes_prefiere_precio_en_vivo(monkeypatch):
    """El servicio de cotizaciones (panel y portafolio) usa el precio en vivo si existe."""
    import importlib
    import sys
    from finmate.realtime import price_stream

    monkeypatch.setattr(price_stream, "get_live_quote", lambda s: {"price": 1.23, "change_pct": 0.5, "is_closed": False})
    # conftest reemplaza quotes.get_quote; recargamos una copia limpia del módulo.
    spec = importlib.util.find_spec("finmate.services.quotes")
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    assert fresh.get_quote("nvda")["price"] == 1.23


# ── Etapa C ─────────────────────────────────────────────────────────────

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel><title>Primer Click</title>
<item><title>Especial (video): Nvidia y Anthropic</title><guid>g-video</guid>
<pubDate>Mon, 16 Nov 2026 10:20:00 GMT</pubDate><description>&lt;p&gt;Video&lt;/p&gt;</description>
<enclosure url="https://x/v.mp3" length="34000000" type="audio/mpeg"/></item>
<item><title>Noviembre 16: IA, tasas y China</title><guid>g-1</guid>
<pubDate>Mon, 16 Nov 2026 10:13:43 GMT</pubDate><link>https://podcasters.spotify.com/ep1</link>
<description>&lt;p&gt;Las dudas sobre Nvidia &amp;amp; el dólar.&lt;/p&gt;</description>
<enclosure url="https://x/a.mp3" length="14521108" type="audio/mpeg"/><itunes:duration>00:14:57</itunes:duration></item>
<item><title>Noviembre 13: viejo</title><guid>g-0</guid><pubDate>Fri, 13 Nov 2026 10:00:00 GMT</pubDate>
<description>x</description></item>
</channel></rss>"""
NOW = dt.datetime(2026, 11, 16, 11, 0, tzinfo=dt.timezone.utc)


def test_parse_feed_y_elige_episodio():
    from finmate.podcasts.digest import parse_feed, pick_new_episode

    eps = parse_feed(RSS)
    assert eps[0]["guid"] == "g-video" and eps[1]["description"] == "Las dudas sobre Nvidia & el dólar."
    ep = pick_new_episode(eps, [], ["Especial (video)"], NOW)
    assert ep["guid"] == "g-1" and ep["duration"] == "00:14:57" and ep["audio_bytes"] == 14521108
    assert pick_new_episode(eps, ["g-1"], ["Especial (video)"], NOW) is None
    assert pick_new_episode(eps, [], [], NOW + dt.timedelta(days=3)) is None


@pytest.fixture
def pod_state(tmp_path, monkeypatch):
    from finmate.podcasts import digest

    monkeypatch.setattr(digest, "STATE_FILE", str(tmp_path / "pod.json"))
    monkeypatch.setattr(digest, "TWILIO_TEMPLATE_MARKET_NOTIFY_SID", "")
    return digest


def test_resumen_se_envia_una_vez(pod_state):
    d = pod_state
    m = FakeMessenger()
    calls = {"t": 0, "s": 0}

    def fake_transcribe(ep):
        calls["t"] += 1
        return "transcripción de prueba"

    def fake_summary(name, ep, transcript):
        calls["s"] += 1
        assert transcript == "transcripción de prueba"
        return "• Punto uno\n• Punto dos"

    kw = dict(now=NOW, feed_fn=lambda url: d.parse_feed(RSS), transcribe_fn=fake_transcribe,
              summarize_fn=fake_summary, recipients_fn=lambda pid: ["whatsapp:+1", "whatsapp:+2"])
    assert d.check_podcast_digests(m, **kw) == 2
    body = m.sent[0][1]
    assert "Primer Click" in body and "Noviembre 16" in body and "• Punto uno" in body
    assert "https://podcasters.spotify.com/ep1" in body and "descripción del episodio" not in body
    assert d.check_podcast_digests(m, **kw) == 0 and calls == {"t": 1, "s": 1}
    assert "Punto dos" in d.get_last_digest("primer_click")


def test_sin_transcripcion_usa_descripcion_y_lo_avisa(pod_state):
    d = pod_state
    m = FakeMessenger()
    d.check_podcast_digests(m, now=NOW, feed_fn=lambda url: d.parse_feed(RSS),
                            transcribe_fn=lambda ep: None,
                            summarize_fn=lambda n, ep, t: "• Resumen corto",
                            recipients_fn=lambda pid: ["whatsapp:+1"])
    assert "descripción del episodio" in m.sent[0][1]


def test_summarize_con_claude_simulado():
    from finmate.podcasts.digest import summarize

    class Block:
        text = "• A\n• B"

    class Client:
        class messages:
            @staticmethod
            def create(**kw):
                assert "Primer Click" in kw["messages"][0]["content"]
                return type("R", (), {"content": [Block()]})

    ep = {"title": "T", "description": "D"}
    assert summarize("Primer Click", ep, "texto", client=Client) == "• A\n• B"


def test_transcribe_sin_clave_o_audio_grande(monkeypatch):
    from finmate.podcasts import digest

    monkeypatch.setattr(digest, "OPENAI_API_KEY", "")
    assert digest.transcribe({"audio_url": "u", "audio_bytes": 1}) is None
    monkeypatch.setattr(digest, "OPENAI_API_KEY", "sk")
    assert digest.transcribe({"title": "x", "audio_url": "u", "audio_bytes": 30_000_000}) is None


def test_tools_de_podcast(client):
    from finmate.agent.tools import TOOLS, run_tool
    from finmate.db import repository as repo
    from finmate.db.news_repo import get_topic_followers

    assert {"follow_podcast", "unfollow_podcast", "get_podcast_summary"} <= {t["name"] for t in TOOLS}
    u = repo.get_or_create_user("whatsapp:+56933334444")
    assert "Listo" in run_tool("follow_podcast", {"podcast": "primer click del DF"}, user_id=u.id)
    assert "Ya recibes" in run_tool("follow_podcast", {"podcast": "Primer Click"}, user_id=u.id)
    assert (u.id, "whatsapp:+56933334444") in get_topic_followers("podcast", "primer_click")
    assert "no sé" in run_tool("follow_podcast", {"podcast": "Otro"}, user_id=u.id).lower()
    assert "ya no" in run_tool("unfollow_podcast", {"podcast": "Primer Click"}, user_id=u.id)
