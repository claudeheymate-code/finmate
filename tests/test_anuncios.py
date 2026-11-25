"""Pestaña Anuncios del panel admin: mensajes a todos los usuarios."""
import datetime as dt

import pytest

H = {"X-Finmate": "1"}
ADMIN = "claude.heymate@gmail.com"


class FakeMessenger:
    def __init__(self):
        self.sent, self.templates = [], []

    def send_message(self, to, body):
        self.sent.append((to, body))
        return True

    def send_template(self, to, name, variables=None):
        self.templates.append((to, name, variables))
        return True


@pytest.fixture
def admin(app, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "ADMIN_DEV_LOGIN", True)
    c = app.test_client()
    assert c.post("/admin/api/dev-login", json={"email": ADMIN}, headers=H).status_code == 200
    return c


@pytest.fixture
def fake(monkeypatch):
    m = FakeMessenger()
    monkeypatch.setattr("finmate.whatsapp.messenger.WhatsAppMessenger", lambda: m)
    monkeypatch.setattr("config.settings.TEMPLATE_MARKET_NOTIFY", "")
    return m


def _user(phone, wrote_hours_ago=None, status="approved"):
    from finmate.db.models import ConversationTurn, get_session
    from finmate.db.repository import get_or_create_user, set_access_status

    u = get_or_create_user(phone)
    set_access_status(u.id, status)
    if wrote_hours_ago is not None:
        s = get_session()
        try:
            s.add(ConversationTurn(user_id=u.id, role="user", content="hola",
                                   timestamp=dt.datetime.utcnow() - dt.timedelta(hours=wrote_hours_ago)))
            s.commit()
        finally:
            s.close()
    return u


def test_pagina_y_permiso(admin, app):
    assert admin.get("/admin/anuncios").status_code == 200
    assert b"Anuncios" in admin.get("/admin/anuncios").data
    assert app.test_client().get("/admin/api/anuncios", headers=H).status_code == 401


def test_envio_a_todos_respeta_la_ventana_de_24h(admin, fake):
    from finmate.admin.announcements import deliver_pending
    from finmate.db.repository import get_recent_history

    reciente = _user("whatsapp:+56955550001", wrote_hours_ago=2)
    antiguo = _user("whatsapp:+56955550002", wrote_hours_ago=40)
    pendiente = _user("whatsapp:+56955550003", wrote_hours_ago=1, status="pending")

    reach = admin.get("/admin/api/anuncios", headers=H).get_json()["reach"]
    assert reach["total"] >= 2 and reach["now"] >= 1

    r = admin.post("/admin/api/anuncios", json={"title": "Novedad", "body": "Ahora puedes calificar noticias.",
                                                "audience": "all"}, headers=H)
    assert r.status_code == 200, r.get_json()
    a = r.get_json()["announcement"]
    phones = [to for to, _b in fake.sent]
    assert reciente.phone in phones and antiguo.phone not in phones and pendiente.phone not in phones
    assert fake.sent[0][1].startswith("📣 *Novedad*\n\nAhora puedes")
    assert a["counts"]["sent"] >= 1 and a["counts"]["pending"] >= 1
    assert any("📣" in txt for role, txt in get_recent_history(reciente.id) if role == "assistant")

    # El que no estaba en la ventana lo recibe cuando vuelve a escribir (una sola vez)
    assert deliver_pending(antiguo.phone, messenger=fake) == 1
    assert fake.sent[-1] == (antiguo.phone, "📣 *Novedad*\n\nAhora puedes calificar noticias.")
    assert deliver_pending(antiguo.phone, messenger=fake) == 0
    hist = admin.get("/admin/api/anuncios", headers=H).get_json()["history"]
    assert hist[0]["counts"]["later"] >= 1


def test_con_plantilla_avisa_y_encola(admin, fake, monkeypatch):
    from finmate.alerts import pending

    monkeypatch.setattr("config.settings.TEMPLATE_MARKET_NOTIFY", "finmate_market_notify")
    u = _user("whatsapp:+56955550010", wrote_hours_ago=72)
    admin.post("/admin/api/anuncios", json={"body": "Cambio importante en los avisos.", "audience": "all"}, headers=H)
    assert (u.phone, "finmate_market_notify", {"1": "Anuncio de Finmate"}) in fake.templates
    assert "Cambio importante" in (pending.pop_pending(u.phone) or "")


def test_prueba_solo_a_los_admins(admin, fake, monkeypatch):
    monkeypatch.setattr("config.settings.WHATSAPP_RECIPIENTS", ["whatsapp:+56900009999"])
    _user("whatsapp:+56955550020", wrote_hours_ago=1)
    r = admin.post("/admin/api/anuncios", json={"body": "Probando el anuncio.", "audience": "test"}, headers=H)
    assert r.status_code == 200
    assert [to for to, _b in fake.sent] == ["whatsapp:+56900009999"]


def test_validaciones_y_cancelar(admin, fake):
    assert admin.post("/admin/api/anuncios", json={"body": "", "audience": "all"}, headers=H).status_code == 400
    assert admin.post("/admin/api/anuncios", json={"body": "Hola a todos", "audience": "x"}, headers=H).status_code == 400
    assert admin.post("/admin/api/anuncios", json={"body": "Hola", "title": "x" * 200}, headers=H).status_code == 400
    u = _user("whatsapp:+56955550030", wrote_hours_ago=50)
    a = admin.post("/admin/api/anuncios", json={"body": "Algo que cancelaré.", "audience": "all"}, headers=H).get_json()["announcement"]
    r = admin.post(f"/admin/api/anuncios/{a['id']}/cancelar", headers=H).get_json()
    assert r["announcement"]["counts"]["pending"] == 0
    from finmate.admin.announcements import deliver_pending

    assert deliver_pending(u.phone, messenger=fake) == 0


def test_redactar_con_ia(admin, monkeypatch):
    from finmate.agent import orchestrator

    class _R:
        content = [type("B", (), {"type": "text", "text": '{"title": "Noticias a tu medida", "body": "Desde hoy puedes calificar."}'})()]

    class _C:
        class messages:
            @staticmethod
            def create(**kw):
                return _R()

    monkeypatch.setattr(orchestrator, "_client", _C())
    monkeypatch.setattr(orchestrator, "_record_usage", lambda *a, **k: None)
    d = admin.post("/admin/api/anuncios/redactar", json={"notes": "notas 1-3 en noticias, perfil gradual"}, headers=H).get_json()
    assert d == {"title": "Noticias a tu medida", "body": "Desde hoy puedes calificar."}
    assert admin.post("/admin/api/anuncios/redactar", json={"notes": "x"}, headers=H).status_code == 400
