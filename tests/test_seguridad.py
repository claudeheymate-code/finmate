"""Capas de seguridad: filtro de tráfico, registro de eventos, chequeos y panel admin."""
import logging

import pytest

H = {"X-Finmate": "1"}


@pytest.fixture
def admin(app, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "ADMIN_DEV_LOGIN", True)
    c = app.test_client()
    assert c.post("/admin/api/dev-login", json={"email": "claude.heymate@gmail.com"}, headers=H).status_code == 200
    return c


@pytest.fixture(autouse=True)
def sin_whatsapp(monkeypatch):
    from finmate.whatsapp import messenger

    monkeypatch.setattr(messenger.WhatsAppMessenger, "send_message", lambda self, to, body: True)


def _events(kind=None):
    from finmate.security.monitor import list_events

    return [e for e in list_events() if kind is None or e["kind"] == kind]


def test_encabezados_de_seguridad(app):
    r = app.test_client().get("/panel/acceso")
    for h in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Content-Security-Policy",
              "Permissions-Policy"):
        assert h in r.headers, h
    assert "script-src 'self'" in r.headers["Content-Security-Policy"]


def test_escaneo_se_detecta_y_bloquea(app):
    c = app.test_client()
    for p in ("/wp-admin/setup.php", "/.env", "/phpmyadmin/"):
        assert c.get(p).status_code == 404
    assert c.get("/panel/acceso").status_code == 403       # IP bloqueada 1 hora
    assert _events("scanner")


def test_limite_de_intentos_de_ingreso(app):
    c = app.test_client()
    codes = [c.post("/api/auth/verify-code", json={"phone": "+56911119999", "code": "123456"}, headers=H).status_code
             for _ in range(25)]
    assert 403 in codes or 429 in codes


def test_fuerza_bruta_de_codigos_bloquea_la_ip(app):
    from finmate.db.repository import get_or_create_user

    get_or_create_user("whatsapp:+56911118888")
    c = app.test_client()
    for _ in range(5):
        c.post("/api/auth/verify-code", json={"phone": "+56911118888", "code": "000000"}, headers=H)
    assert c.post("/api/auth/verify-code", json={"phone": "+56911118888", "code": "000000"},
                  headers=H).status_code == 403
    assert _events("login_bruteforce")


def test_escritura_sin_encabezado_csrf_se_rechaza(client):
    r = client.post("/api/watchlist", json={"symbol": "AAPL"})
    assert r.status_code == 403
    assert _events("csrf_missing")


def test_formulario_falso_al_webhook_queda_registrado(app):
    r = app.test_client().post("/whatsapp/webhook", data={"Body": "hola", "From": "whatsapp:+56900000000"})
    assert r.status_code == 403
    assert _events("webhook_forged")


def test_claves_ocultas_en_los_logs(caplog):
    from finmate.security.logfilter import RedactSecretsFilter, redact

    assert "abc123secret" not in redact("GET https://finnhub.io/api/v1/quote?symbol=NVDA&token=abc123secret")
    assert "XYZ" not in redact("https://api.marketaux.com/v1/news?api_token=XYZXYZXYZ&symbols=NVDA")
    assert "sk-ant-" not in redact("clave sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAA")
    rec = logging.LogRecord("httpx", logging.INFO, __file__, 1, "GET %s", ("https://x.io/?token=SECRETO1",), None)
    RedactSecretsFilter().filter(rec)
    assert "SECRETO1" not in rec.getMessage()


def test_spam_de_mensajes_no_gasta_claude(monkeypatch):
    from finmate.agent import orchestrator

    llamadas = []
    monkeypatch.setattr(orchestrator, "_run_agent", lambda *a, **k: llamadas.append(1) or "ok", raising=False)
    from finmate.security import guard

    for _ in range(guard.MESSAGE_LIMIT[0]):
        guard.note_message("whatsapp:+56977776666")
    r = orchestrator.handle_message("whatsapp:+56977776666", "hola")
    assert "muchos mensajes" in r and not llamadas
    assert _events("message_flood")


def test_sesion_de_usuario_sin_acceso_deja_de_servir(client):
    from finmate.db.repository import set_access_status

    uid = client.get("/api/me").get_json()["id"]
    set_access_status(uid, "denied")
    assert client.get("/api/me").status_code == 401


def test_chequeo_de_configuracion(monkeypatch):
    from config import settings
    from finmate.security import checks

    monkeypatch.setattr(settings, "PANEL_DEV_LOGIN", True)
    monkeypatch.setattr(settings, "META_APP_SECRET", "")
    sev = {i["severity"] for i in checks.check_config()}
    assert "critical" in sev and "high" in sev


def test_integridad_detecta_archivo_modificado(tmp_path, monkeypatch):
    from finmate.security import checks

    (tmp_path / "app.py").write_text("print('hola')\n")
    monkeypatch.setattr(checks, "ROOT", tmp_path)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    checks.snapshot_baseline()
    assert checks.check_integrity() == []
    (tmp_path / "app.py").write_text("import os; os.system('malo')\n")
    (tmp_path / "puerta_trasera.py").write_text("x = 1\n")
    issues = checks.check_integrity()
    assert issues and issues[0]["severity"] == "critical"
    assert "app.py" in issues[0]["detail"] and "puerta_trasera.py" in issues[0]["detail"]


def test_integridad_compara_con_github(tmp_path, monkeypatch):
    from finmate.security import checks

    (tmp_path / "app.py").write_text("print('hola')\n")
    monkeypatch.setattr(checks, "ROOT", tmp_path)
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc1234")
    checks.snapshot_baseline()

    class R:
        status_code = 200

        @staticmethod
        def json():
            return {"tree": [{"path": "app.py", "type": "blob", "sha": "0" * 40}]}

    monkeypatch.setattr(checks.httpx, "get", lambda *a, **k: R())
    issues = checks.check_integrity()
    assert issues and "GitHub" in issues[0]["detail"]


def test_vulnerabilidades_de_librerias(monkeypatch):
    from finmate.security import checks

    monkeypatch.setattr(checks, "_installed", lambda: [("flask", "0.1"), ("httpx", "0.28.1")])

    class R:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"results": [{"vulns": [{"id": "GHSA-xxxx"}]}, {}]}

    monkeypatch.setattr(checks.httpx, "post", lambda *a, **k: R())
    issues = checks.check_dependencies()
    assert issues and "flask 0.1" in issues[0]["detail"] and "httpx" not in issues[0]["detail"]


def test_revision_mensual_deja_recordatorio(monkeypatch):
    from finmate.security import checks

    for fn in ("check_config", "check_integrity", "check_dependencies", "check_spend"):
        monkeypatch.setattr(checks, fn, lambda: [])
    rep = checks.run_monthly_review()
    assert rep["ok"] is True
    ev = _events("monthly_review")
    assert ev and "limpieza" in ev[0]["detail"]


def test_eventos_repetidos_se_agrupan():
    from finmate.security.monitor import record_event

    for _ in range(4):
        record_event("scanner", "medium", "prueba de agrupación", ip="9.9.9.9", path="/x")
    ev = [e for e in _events("scanner") if e["ip"] == "9.9.9.9"]
    assert len(ev) == 1 and ev[0]["count"] >= 4


def test_panel_admin_seguridad(admin):
    from finmate.security.monitor import record_event

    record_event("config", "high", "prueba de panel", ip=None, path=None)
    d = admin.get("/admin/api/seguridad", headers=H).get_json()
    ev = next(e for e in d["events"] if e["detail"] == "prueba de panel")
    assert d["counts"]["urgent"] >= 1
    assert admin.put(f"/admin/api/seguridad/{ev['id']}", json={"status": "revisado"}, headers=H).status_code == 200
    assert admin.post("/admin/api/seguridad/revisar-todo", headers=H).get_json()["ok"]
    assert admin.get("/admin/api/resumen", headers=H).get_json()["security"]["open"] == 0
    assert admin.get("/admin/inbox").status_code == 200


def test_ingreso_admin_rechazado_queda_registrado(app, monkeypatch):
    from config import settings
    from finmate.web import admin as admin_mod

    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "x")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "y")

    class R:
        def __init__(self, data):
            self._d = data

        def json(self):
            return self._d

    monkeypatch.setattr(admin_mod.httpx, "post", lambda *a, **k: R({"access_token": "t"}))
    monkeypatch.setattr(admin_mod.httpx, "get", lambda *a, **k: R({"email": "intruso@gmail.com", "email_verified": True}))
    c = app.test_client()
    with c.session_transaction() as s:
        s["admin_oauth_state"] = "abc"
    r = c.get("/admin/oauth/callback?state=abc&code=zzz")
    assert r.status_code == 302 and "login" in r.headers["Location"]
    assert any("intruso@gmail.com" in e["detail"] for e in _events("admin_denied"))
