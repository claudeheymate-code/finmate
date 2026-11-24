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
    monkeypatch.setattr(daily_brief, "send_brief", lambda uid, phone, edge, name="": sent.append((uid, edge)) or True)
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
    monkeypatch.setattr(daily_brief, "gather", lambda uid, edge, held=None: captured.setdefault("held", held) and {})
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
    txt = compose({"indices": ["S&P 500: 600.00 (+0.40% vs. cierre anterior)"], "mis_activos": [],
                   "avisos_fuera_de_horario": ["[watchlist] NVDA +8%"]}, "start")
    assert "S&P 500" in txt and "fuera de horario" in txt


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
