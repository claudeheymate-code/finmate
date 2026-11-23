"""Ingreso al panel por código de WhatsApp y por link del bot (etapa 4)."""
import re

H = {"X-Finmate": "1"}


def _new_user(phone):
    from finmate.db.repository import get_or_create_user

    return get_or_create_user("whatsapp:" + phone)


def _capture(monkeypatch, ok=True):
    from finmate.whatsapp import messenger

    sent = []
    monkeypatch.setattr(messenger.WhatsAppMessenger, "send_message",
                        lambda self, to, body: sent.append((to, body)) or ok)
    return sent


def test_numero_desconocido_no_recibe_codigo(app, monkeypatch):
    _capture(monkeypatch)
    r = app.test_client().post("/api/auth/request-code", json={"phone": "+56977770001"}, headers=H)
    assert r.status_code == 404


def test_codigo_correcto_abre_sesion(app, monkeypatch):
    _new_user("+56977770002")
    sent = _capture(monkeypatch)
    c = app.test_client()
    assert c.get("/api/me").status_code == 401
    assert c.post("/api/auth/request-code", json={"phone": "+56 9 7777 0002"}, headers=H).status_code == 200
    code = re.search(r"\*(\d{6})\*", sent[0][1]).group(1)
    assert c.post("/api/auth/verify-code", json={"phone": "+56977770002", "code": "000000" if code != "000000" else "111111"},
                  headers=H).status_code == 401
    assert c.post("/api/auth/verify-code", json={"phone": "+56977770002", "code": code}, headers=H).status_code == 200
    assert c.get("/api/me").status_code == 200
    # Un solo uso.
    assert app.test_client().post("/api/auth/verify-code", json={"phone": "+56977770002", "code": code},
                                  headers=H).status_code == 401


def test_no_se_puede_pedir_otro_codigo_al_tiro(app, monkeypatch):
    _new_user("+56977770003")
    _capture(monkeypatch)
    c = app.test_client()
    assert c.post("/api/auth/request-code", json={"phone": "+56977770003"}, headers=H).status_code == 200
    assert c.post("/api/auth/request-code", json={"phone": "+56977770003"}, headers=H).status_code == 429


def test_si_whatsapp_no_entrega_avisa(app, monkeypatch):
    _new_user("+56977770004")
    _capture(monkeypatch, ok=False)
    r = app.test_client().post("/api/auth/request-code", json={"phone": "+56977770004"}, headers=H)
    assert r.status_code == 502 and "24 horas" in r.get_json()["error"]


def test_link_del_bot_abre_sesion_una_vez(app):
    from finmate.agent.setup_tools import tool_get_panel_link

    u = _new_user("+56977770005")
    out = tool_get_panel_link(u.id, {})
    path = re.search(r"(/panel/entrar\?t=[\w\-]+)", out).group(1)
    c = app.test_client()
    r = c.get(path)
    assert r.status_code == 302 and r.headers["Location"].rstrip("/").endswith("/panel")
    assert c.get("/api/me").status_code == 200
    r2 = app.test_client().get(path)
    assert r2.status_code == 200 and "ya se usó o venció" in r2.get_data(as_text=True)
