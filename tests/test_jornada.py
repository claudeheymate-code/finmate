"""Jornada: avisos solo dentro del horario, resúmenes de inicio y cierre, y lo de
fuera de horario guardado para el resumen siguiente."""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.jornada_real
SCL = ZoneInfo("America/Santiago")
H = {"X-Finmate": "1"}


def _at(y, m, d, hh, mm):
    return dt.datetime(y, m, d, hh, mm, tzinfo=SCL)


def _user(phone, **settings):
    from finmate.db.repository import get_or_create_user
    from finmate.db.settings_repo import set_notification_settings

    u = get_or_create_user(phone)
    if settings:
        set_notification_settings(u.id, **settings)
    return u


def test_dentro_y_fuera_de_la_jornada():
    from finmate.services.workday import in_workday

    u = _user("whatsapp:+56944440001")                      # por defecto 08:30–18:30, lunes a viernes
    assert in_workday(u.id, now=_at(2026, 11, 24, 10, 0))    # martes 10:00
    assert not in_workday(u.id, now=_at(2026, 11, 24, 7, 0))
    assert not in_workday(u.id, now=_at(2026, 11, 24, 19, 0))
    assert not in_workday(u.id, now=_at(2026, 11, 28, 12, 0))   # sábado


def test_jornada_que_cruza_medianoche_y_fines_de_semana():
    from finmate.services.workday import in_workday

    u = _user("whatsapp:+56944440002", workday_start="22:00", workday_end="06:00", workday_weekends=True)
    assert in_workday(u.id, now=_at(2026, 11, 28, 23, 30))
    assert in_workday(u.id, now=_at(2026, 11, 29, 2, 0))
    assert not in_workday(u.id, now=_at(2026, 11, 29, 12, 0))


def test_jornada_apagada_deja_pasar_todo():
    from finmate.services.workday import in_workday

    u = _user("whatsapp:+56944440003", workday_enabled=False)
    assert in_workday(u.id, now=_at(2026, 11, 29, 3, 0))


def test_horas_se_validan_y_normalizan():
    from finmate.db.settings_repo import get_notification_settings, set_notification_settings

    u = _user("whatsapp:+56944440004")
    set_notification_settings(u.id, workday_start="9", workday_end="1730")
    s = get_notification_settings(u.id)
    assert (s["workday_start"], s["workday_end"]) == ("09:00", "17:30")
    with pytest.raises(ValueError):
        set_notification_settings(u.id, workday_start="25:00")
    with pytest.raises(ValueError):
        set_notification_settings(u.id, workday_start="17:30")   # igual al término


def test_fuera_de_horario_se_guarda_para_el_resumen(monkeypatch):
    from finmate.services import workday

    u = _user("whatsapp:+56944440005")
    monkeypatch.setattr(workday, "in_workday", lambda *a, **k: False)
    assert workday.allow("whatsapp:+56944440005", "NVDA se movió +8%", "watchlist") is False
    held = workday.pop_held(u.id)
    assert held and held[0]["kind"] == "watchlist" and "NVDA" in held[0]["text"]
    assert workday.pop_held(u.id) == []


def test_resumenes_de_inicio_y_cierre_se_mandan_una_vez(monkeypatch):
    from finmate.services import daily_brief, workday

    u = _user("whatsapp:+56944440006", workday_start="09:00", workday_end="18:00")
    sent = []
    monkeypatch.setattr(daily_brief, "send_brief", lambda uid, phone, edge, name="", tz_name=None: sent.append((uid, edge)) or True)
    monkeypatch.setattr(workday, "_approved_users", lambda: [(u.id, u.phone, "America/Santiago", "Ana")])
    assert workday.run_workday_tick(_at(2026, 11, 24, 8, 55)) == 0
    assert workday.run_workday_tick(_at(2026, 11, 24, 9, 5)) == 1
    assert workday.run_workday_tick(_at(2026, 11, 24, 9, 10)) == 0          # no se repite
    assert workday.run_workday_tick(_at(2026, 11, 24, 18, 3)) == 1
    assert workday.run_workday_tick(_at(2026, 11, 28, 9, 5)) == 0           # sábado
    assert sent == [(u.id, "start"), (u.id, "end")]


def test_resumen_incluye_avisos_guardados_y_queda_en_el_historial(monkeypatch):
    from finmate.db.repository import get_recent_history
    from finmate.services import daily_brief, workday
    from finmate.whatsapp import messenger

    u = _user("whatsapp:+56944440007")
    workday.hold(u.id, "Resultados de DLTR hoy", "Resultados corporativos")
    captured = {}
    monkeypatch.setattr(daily_brief, "gather", lambda uid, edge, held=None, digest=None: captured.setdefault("held", held) and {})
    monkeypatch.setattr(daily_brief, "compose", lambda facts, edge, name="": "El S&P cerró +0,4% y DLTR presentó resultados.")
    out = []
    monkeypatch.setattr(messenger.WhatsAppMessenger, "send_message", lambda self, to, body: out.append(body) or True)
    assert daily_brief.send_brief(u.id, u.phone, "start")
    assert "DLTR" in captured["held"][0]["text"]
    assert out[0].startswith("☀️ *Inicio de jornada*")
    assert any("Inicio de jornada" in txt for role, txt in get_recent_history(u.id) if role == "assistant")


def test_resumen_simple_si_claude_no_esta(monkeypatch):
    from finmate.agent import orchestrator
    from finmate.services.daily_brief import compose

    monkeypatch.setattr(orchestrator, "_client", None)
    txt = compose({"indices": [{"symbol": "SPY", "label": "S&P 500", "price": 600.0, "change_pct": 0.4, "is_closed": False}],
                   "mis_activos": [], "noticias_del_mercado": ["La Fed mantiene la tasa (Reuters)"],
                   "avisos_fuera_de_horario": [{"kind": "watchlist", "text": "NVDA +8%"}]}, "start")
    assert "La Fed mantiene la tasa" in txt            # párrafo con los titulares
    assert "• S&P 500" in txt and "*S&P 500*" not in txt and "▲ 0,4%" in txt       # viñeta con la cifra
    assert "Mientras no estabas" in txt and "NVDA +8%" in txt


def test_formato_parrafo_y_vinetas(monkeypatch):
    """El párrafo lo escribe Claude; las cifras las pone el código, ordenadas y con formato chileno."""
    from finmate.agent import orchestrator
    from finmate.services import daily_brief

    seen = {}

    class _Resp:
        content = [type("B", (), {"type": "text", "text": "Día marcado por la Fed y la caída de los chips."})()]

    class _Client:
        class messages:
            @staticmethod
            def create(**kw):
                seen.update(kw)
                return _Resp()

    monkeypatch.setattr(orchestrator, "_client", _Client())
    monkeypatch.setattr(orchestrator, "_record_usage", lambda *a, **k: None)
    facts = {
        "indices": [{"symbol": "QQQ", "label": "Nasdaq 100", "price": 512.3, "change_pct": -0.84, "is_closed": False}],
        "mis_activos": [{"symbol": "AAPL", "label": "AAPL", "price": 229.8, "change_pct": 0.4, "is_closed": False},
                        {"symbol": "NVDA", "label": "NVDA", "price": 1142.3, "change_pct": -3.1, "is_closed": False}],
        "en_portafolio": ["NVDA"],
        "chile": [{"code": "USD_CLP", "label": "Dólar observado", "value": 938.12, "fmt": "clp"}],
        "portafolio": {"value": 12500.0, "day_change": -120.0, "day_pct": -0.95},
        "noticias_del_mercado": ["Powell enfría recortes (Reuters)"],
    }
    txt = daily_brief.compose(facts, "end")
    para, rest = txt.split("\n\n", 1)
    assert para == "Día marcado por la Fed y la caída de los chips."
    assert "Powell enfría recortes" in seen["messages"][0]["content"]
    assert "• Nasdaq 100  $512,30  🔴 ▼ 0,8%" in rest
    assert "• Dólar  $938,12" in rest
    assert rest.index("AAPL") < rest.index("NVDA")      # tickers de mayor a menor variación
    assert "• NVDA 💼  $1.142,30" in rest                # marca los que están en el portafolio
    assert "US$12.500" in rest and "−US$120" in rest
    assert "Hoy se publica" not in rest and "Mientras no estabas" not in rest   # solo al inicio
    # Negrita solo en los títulos de sección, nunca en las viñetas
    assert all("*" not in line for line in rest.splitlines() if line.startswith("•"))


def test_secciones_vacias_no_aparecen(monkeypatch):
    from finmate.agent import orchestrator
    from finmate.services.daily_brief import bullets

    monkeypatch.setattr(orchestrator, "_client", None)
    assert bullets({"indices": [], "mis_activos": [], "chile": [], "portafolio": {}}, "start") == ""


def test_alerta_de_watchlist_fuera_de_horario_no_se_manda(monkeypatch):
    from finmate.alerts import watchlist_alerts
    from finmate.db.repository import add_to_watchlist
    from finmate.services import workday

    u = _user("whatsapp:+56944440008")
    add_to_watchlist(u.id, "NVDA")
    monkeypatch.setattr(workday, "in_workday", lambda *a, **k: False)
    sent = []

    class M:
        def send_message(self, to, body):
            sent.append(to)
            return True

    watchlist_alerts.check_watchlist_alerts(messenger=M(), quote_fn=lambda s: {"price": 200.0, "change_pct": 9.0,
                                                                                "is_closed": False})
    assert "whatsapp:+56944440008" not in sent
    assert any("NVDA" in h["text"] for h in workday.pop_held(u.id))


def test_panel_guarda_la_jornada(client):
    r = client.put("/api/avisos", json={"workday_start": "07:45", "workday_end": "17:15", "workday_weekends": True}, headers=H)
    d = r.get_json()
    assert (d["workday_start"], d["workday_end"], d["workday_weekends"]) == ("07:45", "17:15", True)
    assert client.put("/api/avisos", json={"workday_start": "99:00"}, headers=H).status_code == 400
    assert client.put("/api/avisos", json={"workday_enabled": "si"}, headers=H).status_code == 400
