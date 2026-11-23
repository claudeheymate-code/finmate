"""WhatsApp Cloud API de Meta: verificación del webhook, firma, mensajes entrantes y envío."""
import hashlib
import hmac
import json

import pytest

from finmate.whatsapp import meta_cloud, webhook


def _payload(text="hola", msg_id="wamid.1", frm="56912345678", mtype="text"):
    m = {"from": frm, "id": msg_id, "timestamp": "1", "type": mtype}
    if mtype == "text":
        m["text"] = {"body": text}
    return {"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"phone_number_id": "123"},
        "contacts": [{"wa_id": frm, "profile": {"name": "Joaco"}}], "messages": [m]}}]}]}


@pytest.fixture
def anon(app):
    return app.test_client()


@pytest.fixture
def captured(monkeypatch):
    sent = {"posts": [], "handled": []}
    monkeypatch.setattr(meta_cloud, "META_WHATSAPP_TOKEN", "tok")
    monkeypatch.setattr(meta_cloud, "META_PHONE_NUMBER_ID", "123")
    monkeypatch.setattr(meta_cloud, "META_APP_SECRET", "")

    class R:
        status_code = 200
        text = "{}"
        def json(self):
            return {"messages": [{"id": "wamid.out"}]}

    monkeypatch.setattr(meta_cloud.httpx, "post", lambda url, json=None, timeout=None, headers=None: sent["posts"].append((url, json, headers)) or R())
    import finmate.agent.orchestrator as orch
    monkeypatch.setattr(orch, "handle_message", lambda phone, text, **kw: sent["handled"].append((phone, text)) or "respuesta del bot")
    import finmate.whatsapp.messenger as msgr
    monkeypatch.setattr(msgr, "WHATSAPP_PROVIDER", "meta")
    monkeypatch.setattr(webhook, "RUN_IN_BACKGROUND", False)
    webhook._SEEN.clear()
    return sent


def test_verificacion_del_webhook(anon, monkeypatch):
    monkeypatch.setattr(webhook, "META_VERIFY_TOKEN", "secreto-finmate")
    ok = anon.get("/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=secreto-finmate&hub.challenge=12345")
    assert ok.status_code == 200 and ok.get_data(as_text=True) == "12345"
    assert anon.get("/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=otro&hub.challenge=1").status_code == 403


def test_mensaje_entrante_responde_por_meta(anon, captured):
    r = anon.post("/whatsapp/webhook", json=_payload("¿cómo va el dólar?"))
    assert r.status_code == 200
    # Mismo formato de teléfono que con Twilio: el usuario y su memoria se mantienen
    assert captured["handled"] == [("whatsapp:+56912345678", "¿cómo va el dólar?")]
    texts = [p[1] for p in captured["posts"] if p[1].get("type") == "text"]
    assert texts and texts[0]["to"] == "56912345678" and texts[0]["text"]["body"] == "respuesta del bot"
    assert captured["posts"][0][2]["Authorization"] == "Bearer tok"
    assert "/v25.0/123/messages" in captured["posts"][0][0]


def test_reintento_de_meta_no_duplica_respuesta(anon, captured):
    anon.post("/whatsapp/webhook", json=_payload(msg_id="wamid.X"))
    anon.post("/whatsapp/webhook", json=_payload(msg_id="wamid.X"))
    assert len(captured["handled"]) == 1


def test_mensaje_no_texto(anon, captured):
    anon.post("/whatsapp/webhook", json=_payload(mtype="image", msg_id="wamid.img"))
    assert captured["handled"] == []
    body = [p[1] for p in captured["posts"] if p[1].get("type") == "text"][0]["text"]["body"]
    assert "texto" in body


def test_avisos_de_estado_se_ignoran(anon, captured):
    st = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"statuses": [{"id": "x", "status": "read"}]}}]}]}
    assert anon.post("/whatsapp/webhook", json=st).status_code == 200
    assert captured["handled"] == [] and captured["posts"] == []


def test_firma_invalida_se_rechaza(anon, captured, monkeypatch):
    monkeypatch.setattr(meta_cloud, "META_APP_SECRET", "clave")
    body = json.dumps(_payload(msg_id="wamid.f")).encode()
    bad = anon.post("/whatsapp/webhook", data=body, content_type="application/json", headers={"X-Hub-Signature-256": "sha256=000"})
    assert bad.status_code == 403 and captured["handled"] == []
    sig = "sha256=" + hmac.new(b"clave", body, hashlib.sha256).hexdigest()
    good = anon.post("/whatsapp/webhook", data=body, content_type="application/json", headers={"X-Hub-Signature-256": sig})
    assert good.status_code == 200 and len(captured["handled"]) == 1


def test_plantilla_por_nombre_con_variables(captured):
    from finmate.whatsapp.messenger import WhatsAppMessenger
    assert WhatsAppMessenger().send_template("whatsapp:+56911112222", "finmate_watchlist_alert", {"2": "+5,2%", "1": "NVDA", "3": "$186,64"})
    t = captured["posts"][-1][1]
    assert t["to"] == "56911112222" and t["template"]["name"] == "finmate_watchlist_alert"
    assert [p["text"] for p in t["template"]["components"][0]["parameters"]] == ["NVDA", "+5,2%", "$186,64"]


def test_twilio_sigue_funcionando(anon, monkeypatch):
    import finmate.agent.orchestrator as orch
    monkeypatch.setattr(orch, "handle_message", lambda phone, text, **kw: "hola desde twilio")
    r = anon.post("/whatsapp/webhook", data={"Body": "hola", "From": "whatsapp:+56900000000"})
    assert r.status_code == 200 and "hola desde twilio" in r.get_data(as_text=True)


def test_estado_fallido_queda_en_el_log(anon, captured, caplog):
    st = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"statuses": [
        {"id": "x", "status": "failed", "recipient_id": "56954161465",
         "errors": [{"code": 131030, "title": "Recipient phone number not in allowed list"}]}]}}]}]}
    with caplog.at_level("WARNING"):
        assert anon.post("/whatsapp/webhook", json=st).status_code == 200
    assert "131030" in caplog.text and "FALLÓ" in caplog.text


def test_revision_al_arrancar(monkeypatch, caplog):
    monkeypatch.setattr(meta_cloud, "META_WHATSAPP_TOKEN", "tok")
    monkeypatch.setattr(meta_cloud, "META_PHONE_NUMBER_ID", "123")
    monkeypatch.setattr(meta_cloud, "META_WABA_ID", "999")
    monkeypatch.setattr(meta_cloud, "META_TEST_RECIPIENT", "")
    monkeypatch.setattr(meta_cloud, "META_REGISTER_PIN", "123456")
    calls = []

    class R:
        def __init__(self, data):
            self.status_code, self.text, self._d = 200, "{}", data
        def json(self):
            return self._d

    monkeypatch.setattr(meta_cloud.httpx, "get", lambda url, **k: calls.append(("GET", url)) or R({"display_phone_number": "+1 555", "verified_name": "Finmate"}))
    monkeypatch.setattr(meta_cloud.httpx, "post", lambda url, **k: calls.append(("POST", url)) or R({"success": True}))
    with caplog.at_level("INFO"):
        meta_cloud.startup_check()
    assert ("POST", "https://graph.facebook.com/v25.0/999/subscribed_apps") in calls
    assert ("POST", "https://graph.facebook.com/v25.0/123/register") in calls
    assert "token OK" in caplog.text and "suscrita" in caplog.text


def test_mensaje_de_prueba_al_arrancar(monkeypatch, captured):
    monkeypatch.setattr(meta_cloud, "META_TEST_RECIPIENT", "+56 9 5416 1465")
    monkeypatch.setattr(meta_cloud, "META_WABA_ID", "")
    monkeypatch.setattr(meta_cloud, "META_REGISTER_PIN", "")

    class G:
        status_code, text = 200, "{}"
        def json(self):
            return {}
    monkeypatch.setattr(meta_cloud.httpx, "get", lambda url, **k: G())
    meta_cloud.startup_check()
    t = captured["posts"][-1][1]
    assert t["to"] == "56954161465" and t["template"]["name"] == "hello_world" and t["template"]["language"]["code"] == "en_US"
