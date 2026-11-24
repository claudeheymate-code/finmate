"""Panel de administrador: acceso, aprobación de números nuevos, costos, inbox y fuentes."""
import pytest

H = {"X-Finmate": "1"}
ADMIN = "claude.heymate@gmail.com"


@pytest.fixture
def admin(app, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "ADMIN_DEV_LOGIN", True)
    c = app.test_client()
    r = c.post("/admin/api/dev-login", json={"email": ADMIN}, headers=H)
    assert r.status_code == 200, r.get_json()
    return c


def test_sin_sesion_redirige_y_api_401(app):
    c = app.test_client()
    r = c.get("/admin/")
    assert r.status_code == 302 and "/admin/login" in r.headers["Location"]
    assert c.get("/admin/api/resumen", headers=H).status_code == 401
    assert c.get("/admin/login").status_code == 200


def test_otro_correo_no_entra(app, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "ADMIN_DEV_LOGIN", True)
    r = app.test_client().post("/admin/api/dev-login", json={"email": "otro@gmail.com"}, headers=H)
    assert r.status_code == 403


def test_dev_login_apagado_por_defecto(app, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "ADMIN_DEV_LOGIN", False)
    r = app.test_client().post("/admin/api/dev-login", json={"email": ADMIN}, headers=H)
    assert r.status_code == 404


def test_api_exige_encabezado_csrf(admin):
    r = admin.post("/admin/api/suscripciones", json={"name": "X", "cost": 1})
    assert r.status_code == 403


def test_sesion_de_usuario_no_abre_admin(client):
    assert client.get("/admin/api/resumen", headers=H).status_code == 401


def test_paginas_cargan(admin):
    for p in ("/admin/", "/admin/usuarios", "/admin/inbox", "/admin/fuentes"):
        r = admin.get(p)
        assert r.status_code == 200, p
        assert b"admin.js" in r.data


def test_resumen_y_suscripciones(admin):
    d = admin.get("/admin/api/resumen", headers=H).get_json()
    names = [s["name"] for s in d["subscriptions"]]
    assert any("Railway" in n for n in names) and any("Claude" in n for n in names)
    r = admin.post("/admin/api/suscripciones", headers=H,
                   json={"name": "Dominio", "cost": 12, "currency": "USD", "cycle": "anual"})
    assert r.status_code == 200
    subs = r.get_json()["subscriptions"]
    dom = next(s for s in subs if s["name"] == "Dominio")
    r = admin.delete("/admin/api/suscripciones/" + dom["id"], headers=H)
    assert all(s["name"] != "Dominio" for s in r.get_json()["subscriptions"])
    assert admin.post("/admin/api/suscripciones", headers=H, json={"name": "", "cost": 1}).status_code == 400


def test_consumo_se_registra_y_tiene_costo(admin):
    from types import SimpleNamespace
    from finmate.services import usage

    usage.record_claude("claude-haiku-5-5", SimpleNamespace(input_tokens=1_000_000, output_tokens=0,
                                                           cache_read_input_tokens=0, cache_creation_input_tokens=0))
    usage.record_whatsapp("template", True)
    u = admin.get("/admin/api/resumen", headers=H).get_json()["usage"]
    haiku = next(m for m in u["claude"] if m["model"] == "claude-haiku-5-5")
    assert haiku["calls"] >= 1 and haiku["cost_usd"] >= 0.10
    assert u["whatsapp"]["template"] >= 1
    r = admin.put("/admin/api/precios", headers=H, json={"model": "claude-haiku-5-5", "in": 1, "out": 5})
    assert r.status_code == 200


def _fake_whatsapp(monkeypatch):
    from finmate.whatsapp import messenger

    sent = []
    monkeypatch.setattr(messenger.WhatsAppMessenger, "send_message",
                        lambda self, to, body: sent.append((to, body)) or True)
    return sent


def test_numero_nuevo_queda_pendiente_y_se_aprueba(admin, monkeypatch):
    from config import settings
    from finmate.agent import orchestrator

    monkeypatch.setattr(settings, "ACCESS_APPROVAL_REQUIRED", True)
    monkeypatch.setattr(settings, "WHATSAPP_RECIPIENTS", ["whatsapp:+56911110000"])
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test", raising=False)
    monkeypatch.setattr(orchestrator, "ANTHROPIC_API_KEY", "test", raising=False)
    sent = _fake_whatsapp(monkeypatch)

    def boom(*a, **k):
        raise AssertionError("no debe llamar a Claude sin acceso")

    monkeypatch.setattr(orchestrator, "_run_agent", boom, raising=False)
    monkeypatch.setattr("finmate.services.feedback.send_email", lambda *a, **k: True)
    reply = orchestrator.handle_message("whatsapp:+56988880001", "hola", name="Pedro Pérez")
    assert "Pedro" in reply and "correo" in reply.lower()
    assert not sent  # todavía no hay datos: no se avisa al admin
    reply = orchestrator.handle_message("whatsapp:+56988880001", "Pedro Pérez Soto", name="Pedro Pérez")
    assert "correo" in reply.lower()
    reply = orchestrator.handle_message("whatsapp:+56988880001", "pedro@correo.cl", name="Pedro Pérez")
    assert "pendiente" in reply.lower()
    aviso = [b for to, b in sent if to == "whatsapp:+56911110000"]
    assert aviso and "pedro@correo.cl" in aviso[0] and "Pedro Pérez Soto" in aviso[0]
    reply = orchestrator.handle_message("whatsapp:+56988880001", "hola?", name="Pedro Pérez")
    assert "sigue pendiente" in reply.lower()

    inbox = admin.get("/admin/api/inbox", headers=H).get_json()
    req = next(r for r in inbox["requests"] if r["phone"].endswith("56988880001"))
    assert req["status"] == "pending" and req["messages"]
    assert req["email"] == "pedro@correo.cl" and req["name"] == "Pedro Pérez Soto" and req["registered"]
    csv_text = admin.get("/admin/api/usuarios.csv").get_data(as_text=True)
    assert "Correo" in csv_text and "pedro@correo.cl" in csv_text

    # Sin acceso no puede pedir código para el panel.
    assert admin.post("/api/auth/request-code", json={"phone": "+56988880001"}, headers=H).status_code == 403

    r = admin.post(f"/admin/api/usuarios/{req['id']}/acceso", json={"action": "approve"}, headers=H)
    assert r.status_code == 200 and r.get_json()["status"] == "approved"
    users = admin.get("/admin/api/usuarios", headers=H).get_json()["users"]
    assert next(u for u in users if u["id"] == req["id"])["status"] == "approved"

    r = admin.post(f"/admin/api/usuarios/{req['id']}/acceso", json={"action": "deny"}, headers=H)
    assert r.get_json()["status"] == "denied"
    reply = orchestrator.handle_message("whatsapp:+56988880001", "hola?", name="Pedro Pérez")
    assert "pendiente" not in reply.lower()


def test_usuarios_existentes_siguen_con_acceso(admin):
    from finmate.db.repository import get_or_create_user, is_approved

    u = get_or_create_user("whatsapp:+56988880002")  # sin estado = usuario antiguo
    assert is_approved(u)
    assert admin.post(f"/admin/api/usuarios/{u.id}/acceso", json={"action": "xx"}, headers=H).status_code == 400


def test_feedback_en_inbox(admin, client):
    r = client.post("/api/feedback", json={"tipo": "idea", "message": "Agregar fondos mutuos"}, headers=H)
    assert r.status_code in (200, 201), r.get_json()
    fb = admin.get("/admin/api/inbox", headers=H).get_json()["feedback"]
    item = next(f for f in fb if f["message"] == "Agregar fondos mutuos")
    assert item["status"] == "nuevo"
    r = admin.put(f"/admin/api/feedback/{item['id']}", json={"status": "en_curso", "note": "Etapa CMF"}, headers=H)
    assert r.status_code == 200
    item = next(f for f in admin.get("/admin/api/inbox", headers=H).get_json()["feedback"] if f["id"] == item["id"])
    assert item["status"] == "en_curso" and item["note"] == "Etapa CMF"
    assert admin.put(f"/admin/api/feedback/{item['id']}", json={"status": "raro"}, headers=H).status_code == 400


def test_fuentes(admin, monkeypatch):
    from finmate.admin import sources

    d = admin.get("/admin/api/fuentes", headers=H).get_json()
    ids = {s["id"] for s in d["sources"]}
    assert {"finnhub", "fred", "bcch", "podcast"} <= ids
    monkeypatch.setenv("FINNHUB_API_KEY", "test")
    fh = next(x for x in sources.SOURCES if x["id"] == "finnhub")
    monkeypatch.setitem(fh, "test", lambda: (True, "ok de prueba"))
    r = admin.post("/admin/api/fuentes/finnhub/probar", headers=H).get_json()
    assert r["ok"] is True and "ms" in r
    assert admin.put("/admin/api/fuentes/fred/nota", json={"note": "Ver series de empleo"}, headers=H).status_code == 200
    assert admin.put("/admin/api/fuentes/_ideas/nota", json={"note": "Probar Reddit"}, headers=H).status_code == 200
    d = admin.get("/admin/api/fuentes", headers=H).get_json()
    assert next(s for s in d["sources"] if s["id"] == "fred")["note"] == "Ver series de empleo"
    assert d["ideas"] == "Probar Reddit"
    assert admin.post("/admin/api/fuentes/nada/probar", headers=H).status_code == 404


def test_registro_en_un_solo_mensaje(admin, monkeypatch):
    from config import settings
    from finmate.agent import orchestrator

    monkeypatch.setattr(settings, "ACCESS_APPROVAL_REQUIRED", True)
    monkeypatch.setattr(settings, "WHATSAPP_RECIPIENTS", ["whatsapp:+56911110000"])
    monkeypatch.setattr(orchestrator, "ANTHROPIC_API_KEY", "test", raising=False)
    sent = _fake_whatsapp(monkeypatch)
    mails = []
    monkeypatch.setattr("finmate.services.feedback.send_email", lambda subj, body, fields: mails.append(fields) or True)
    orchestrator.handle_message("whatsapp:+56988880003", "Hola, quiero probar", name=None)
    reply = orchestrator.handle_message("whatsapp:+56988880003", "me llamo ana soto y mi correo es Ana@Mail.com")
    assert "Ana" in reply and "pendiente" in reply.lower()
    assert mails and mails[0]["correo"] == "ana@mail.com" and mails[0]["nombre"] == "Ana Soto"


def test_interpretar_nombre_y_correo():
    from finmate.agent.signup import parse_signup

    assert parse_signup("hola") == (None, None)
    assert parse_signup("Joaquín Cornejo, joaco@gmail.com") == ("Joaquín Cornejo", "joaco@gmail.com")
    assert parse_signup("pedro@x.com") == (None, "pedro@x.com")
    assert parse_signup("Mi nombre es ana maría soto") == ("Ana María Soto", None)
    assert parse_signup("¿qué es finmate?") == (None, None)


def test_apps_separadas_con_su_icono(app, admin):
    user_page = app.test_client().get("/panel/acceso").get_data(as_text=True)
    assert "manifest.json" in user_page and "admin-manifest" not in user_page
    for html in (admin.get("/admin/").get_data(as_text=True),
                 app.test_client().get("/admin/login").get_data(as_text=True)):
        assert "admin-manifest.json" in html and "admin-apple-touch-icon.png" in html
        assert "user-scalable=no" in html
    m = app.test_client().get("/panel/static/admin-manifest.json").get_json()
    assert m["scope"] == "/admin/" and m["start_url"] == "/admin/" and m["name"] == "Finmate Admin"
    assert app.test_client().get("/panel/static/admin-icon-512.png").status_code == 200
