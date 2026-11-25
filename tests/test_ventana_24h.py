"""Ventana de 24 h de WhatsApp: lo que el bot manda por su cuenta a quien no le escribe hace
más de un día no se pierde (Meta lo rechazaba con el error 131047), se guarda y llega
cuando el usuario vuelve a escribir."""
import datetime as dt

H = {"X-Finmate": "1"}


class FakeMessenger:
    def __init__(self):
        self.sent = []

    def send_message(self, to, body):
        self.sent.append((to, body))
        return True

    def send_buttons(self, to, body, buttons, fallback=None):
        self.sent.append((to, body))
        return True

    def send_template(self, to, name, variables=None):
        self.sent.append((to, f"TEMPLATE {name}"))
        return True


_n = {"i": 0}


def _user():
    from finmate.db.repository import get_or_create_user, set_access_status

    _n["i"] += 1
    u = get_or_create_user(f"whatsapp:+5697100{_n['i']:04d}")
    set_access_status(u.id, "approved")
    return u


def test_ventana_real_segun_ultimo_mensaje(monkeypatch):
    import importlib

    from finmate.db.models import ConversationTurn, get_session
    from finmate.services import workday

    real = importlib.reload(workday).window_open      # sin el reemplazo del conftest
    u = _user()
    assert real(u.id) is False                         # nunca escribió
    s = get_session()
    s.add(ConversationTurn(user_id=u.id, role="user", content="hola",
                           timestamp=dt.datetime.utcnow() - dt.timedelta(hours=30)))
    s.commit(); s.close()
    assert real(u.id) is False                         # hace 30 h
    s = get_session()
    s.add(ConversationTurn(user_id=u.id, role="user", content="hola",
                           timestamp=dt.datetime.utcnow() - dt.timedelta(hours=2)))
    s.commit(); s.close()
    assert real(u.id) is True


def test_resumen_queda_pendiente_y_llega_al_escribir(window_closed, monkeypatch):
    from finmate.agent import orchestrator
    from finmate.services import daily_brief, news_profile, workday

    monkeypatch.setattr("config.settings.TEMPLATE_MARKET_NOTIFY", "")
    monkeypatch.setattr(orchestrator, "_client", None)
    u = _user()
    workday.hold(u.id, "NVDA se movió +6%", "watchlist")
    news_profile.push_digest(u.id, news_profile.make_item("mercado", "Fed holds rates"), 2)
    m = FakeMessenger()
    monkeypatch.setattr("finmate.whatsapp.messenger.WhatsAppMessenger", lambda: m)

    assert daily_brief.send_brief(u.id, u.phone, "start") is False
    assert daily_brief.send_brief(u.id, u.phone, "end") is False
    assert m.sent == []                                   # nada se manda (se perdería)
    assert daily_brief.has_pending_brief(u.id)

    # Cuando escribe: un solo resumen, con todo lo guardado y la explicación
    assert daily_brief.deliver_pending_brief(u.phone, messenger=m) is True
    to, body = m.sent[-1]
    assert to == u.phone and body.startswith("🗞️ *Lo que te perdiste*")
    assert "NVDA se movió +6%" in body and "Fed holds rates" in body
    assert "Junta lo de 2 resúmenes" in body
    assert daily_brief.deliver_pending_brief(u.phone, messenger=m) is False   # una sola vez


def test_avisos_se_guardan_con_la_ventana_cerrada(window_closed, monkeypatch):
    from finmate.services import workday

    monkeypatch.setattr("config.settings.TEMPLATE_MARKET_NOTIFY", "")
    monkeypatch.setattr(workday, "in_workday", lambda *a, **k: True)
    u = _user()
    assert workday.allow(u.phone, "AAPL +7%", "watchlist") is False
    assert any("AAPL +7%" in h["text"] for h in workday.pop_held(u.id))


def test_con_plantilla_si_se_puede_avisar(window_closed, monkeypatch):
    from finmate.services import workday

    monkeypatch.setattr("config.settings.TEMPLATE_MARKET_NOTIFY", "finmate_market_notify")
    monkeypatch.setattr(workday, "in_workday", lambda *a, **k: True)
    u = _user()
    assert workday.allow(u.phone, "AAPL +7%", "watchlist") is True


def test_noticia_va_al_resumen_con_la_ventana_cerrada(window_closed, monkeypatch):
    from finmate.services import news_profile

    monkeypatch.setattr("config.settings.TEMPLATE_MARKET_NOTIFY", "")
    u = _user()
    m = FakeMessenger()
    assert news_profile.deliver(u.id, u.phone, news_profile.make_item("mercado", "Oil jumps"), m) == "resumen"
    assert m.sent == []
    assert [d["headline"] for d in news_profile.pop_digest(u.id)] == ["Oil jumps"]


def test_admin_muestra_la_ventana(app, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "ADMIN_DEV_LOGIN", True)
    c = app.test_client()
    c.post("/admin/api/dev-login", json={"email": "claude.heymate@gmail.com"}, headers=H)
    users = c.get("/admin/api/usuarios", headers=H).get_json()["users"]
    assert users and all("window_open" in u for u in users)


# ── Aviso diario por plantilla (lunes a viernes) ────────────────────────

class TemplateMessenger(FakeMessenger):
    def __init__(self):
        super().__init__()
        self.templates = []

    def send_template(self, to, name, variables=None):
        self.templates.append((to, name, variables))
        return True


def _weekday(monkeypatch, weekday: int):
    """Fija "ahora" en un día de la semana (0 = lunes) a las 08:30 de Chile."""
    import datetime as real_dt

    from finmate.services import daily_brief

    base = real_dt.datetime(2026, 11, 23, 11, 30, tzinfo=real_dt.timezone.utc) + real_dt.timedelta(days=weekday)

    class FakeDT(real_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return base.astimezone(tz) if tz else base.replace(tzinfo=None)

    monkeypatch.setattr(daily_brief.dt, "datetime", FakeDT)


def test_aviso_diario_con_destacado_y_si_mandamelo(window_closed, monkeypatch):
    from finmate.agent import orchestrator
    from finmate.db.repository import set_user_name_if_empty
    from finmate.services import daily_brief

    monkeypatch.setattr("config.settings.TEMPLATE_MARKET_NOTIFY", "")
    monkeypatch.setattr("config.settings.META_TEMPLATE_MORNING_BRIEF", "finmate_buenos_dias")
    monkeypatch.setattr(orchestrator, "_client", None)
    monkeypatch.setattr(daily_brief, "_releases_today", lambda: ["Personal Income and Outlays (PCE)"])
    _weekday(monkeypatch, 2)                                        # miércoles
    u = _user()
    set_user_name_if_empty(u.id, "Camila Rojas")
    m = TemplateMessenger()
    monkeypatch.setattr("finmate.whatsapp.messenger.WhatsAppMessenger", lambda: m)

    assert daily_brief.send_brief(u.id, u.phone, "start", name="Camila Rojas") is True
    to, name, variables = m.templates[-1]
    assert (to, name) == (u.phone, "finmate_buenos_dias")
    assert variables["1"] == "Camila" and "PCE" in variables["2"] and "\n" not in variables["2"]
    assert m.sent == []                                             # el resumen espera la respuesta

    assert daily_brief.handle_morning_reply(u.phone, "Sí, mándamelo", messenger=m) == ""
    assert m.sent[-1][1].startswith("☀️ *Inicio de jornada*")      # resumen normal, sin "te lo guardé"
    assert "Te lo guardé" not in m.sent[-1][1]
    assert not daily_brief.has_pending_brief(u.id)


def test_aviso_diario_hoy_no_y_fin_de_semana(window_closed, monkeypatch):
    from finmate.services import daily_brief

    monkeypatch.setattr("config.settings.TEMPLATE_MARKET_NOTIFY", "")
    monkeypatch.setattr("config.settings.META_TEMPLATE_MORNING_BRIEF", "finmate_buenos_dias")
    monkeypatch.setattr(daily_brief, "morning_highlight", lambda today=None: "algo importante")
    u = _user()
    m = TemplateMessenger()
    monkeypatch.setattr("finmate.whatsapp.messenger.WhatsAppMessenger", lambda: m)

    _weekday(monkeypatch, 5)                                        # sábado: no se manda plantilla
    assert daily_brief.send_brief(u.id, u.phone, "start") is False and m.templates == []
    assert daily_brief.has_pending_brief(u.id)

    _weekday(monkeypatch, 0)                                        # lunes
    assert daily_brief.send_brief(u.id, u.phone, "start") is True and len(m.templates) == 1
    reply = daily_brief.handle_morning_reply(u.phone, "Hoy no", messenger=m)
    assert reply.startswith("Dale, que tengas buen día")
    assert not daily_brief.has_pending_brief(u.id) and m.sent == []
    assert daily_brief.handle_morning_reply(u.phone, "hola, ¿cómo va NVDA?") is None   # mensaje normal


def test_sin_plantilla_configurada_queda_pendiente(window_closed, monkeypatch):
    from finmate.services import daily_brief

    monkeypatch.setattr("config.settings.TEMPLATE_MARKET_NOTIFY", "")
    monkeypatch.setattr("config.settings.META_TEMPLATE_MORNING_BRIEF", "")
    u = _user()
    m = TemplateMessenger()
    monkeypatch.setattr("finmate.whatsapp.messenger.WhatsAppMessenger", lambda: m)
    assert daily_brief.send_brief(u.id, u.phone, "start") is False
    assert m.templates == [] and daily_brief.has_pending_brief(u.id)


def test_parametro_de_plantilla_limpio():
    from finmate.services.daily_brief import _clean_param

    assert _clean_param("*Nvidia*  presenta\nresultados.", 90) == "Nvidia presenta resultados"
    assert len(_clean_param("x" * 200, 90)) == 90
