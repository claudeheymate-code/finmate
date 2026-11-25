"""Formato de WhatsApp (sin asteriscos dobles a la vista) y nivel de emojis por usuario."""

H = {"X-Finmate": "1"}


def test_negrita_markdown_pasa_a_whatsapp():
    from finmate.utils.text import whatsapp_markup

    txt = ("Lo más destacado:\n\n• **Google** empezó a conectar su IA\n• **Meta** metió su agente\n"
           "## Resumen\nVer [la nota](https://x.com/a) y __esto__ y ~~aquello~~\n---\n**Ojo**: *ya bien*")
    out = whatsapp_markup(txt)
    assert "**" not in out and "##" not in out and "---" not in out
    assert "• *Google* empezó" in out and "• *Meta* metió" in out
    assert "*Resumen*" in out and "la nota: https://x.com/a" in out
    assert "_esto_" in out and "~aquello~" in out and "*Ojo*: *ya bien*" in out
    assert whatsapp_markup("* punto de lista\n* otro") == "* punto de lista\n* otro"   # listas intactas


def test_quitar_emojis_deja_flechas_y_vinetas():
    from finmate.utils.text import strip_emojis

    out = strip_emojis("📊 *Índices*\n• S&P 500  $598,40  🔴 ▼ 0,3%\n☀️ *Inicio* · 🇨🇱 Chile ✅")
    assert out == "*Índices*\n• S&P 500 $598,40 ▼ 0,3%\n*Inicio* · Chile"


def test_mensajes_salen_con_formato_y_emojis_del_usuario(monkeypatch):
    from finmate.db.personality_repo import set_personality
    from finmate.db.repository import get_or_create_user
    from finmate.utils import text
    from finmate.whatsapp import meta_cloud
    from finmate.whatsapp.messenger import WhatsAppMessenger

    sent = []
    monkeypatch.setattr(meta_cloud, "send_text", lambda to, body: sent.append(body) or True)
    u = get_or_create_user("whatsapp:+56972220001")
    text.forget_emoji_level()
    WhatsAppMessenger().send_message(u.phone, "📈 **NVDA** subió 3%")
    assert sent[-1] == "📈 *NVDA* subió 3%"                 # por defecto (4) los emojis quedan
    set_personality(u.id, emojis=1)
    WhatsAppMessenger().send_message(u.phone, "📈 **NVDA** subió 3%")
    assert sent[-1] == "*NVDA* subió 3%"                    # sin emojis


def test_ajuste_de_emojis_en_panel_y_prompt(client):
    from finmate.agent.orchestrator import _build_system_prompt

    assert client.get("/api/personalidad", headers=H).get_json()["emojis"] == 4
    assert client.put("/api/personalidad", json={"emojis": 9}, headers=H).get_json()["emojis"] == 9
    assert client.put("/api/personalidad", json={"emojis": 0}, headers=H).status_code == 400
    sin = "".join(b["text"] for b in _build_system_prompt({"emojis": 1}))
    con = "".join(b["text"] for b in _build_system_prompt({"emojis": 9}))
    assert "NINGÚN emoji" in sin and "muchos emojis" in con and "nunca dos" in sin


def test_tool_del_bot_cambia_emojis():
    from finmate.agent.tools import run_tool
    from finmate.db.personality_repo import get_personality
    from finmate.db.repository import get_or_create_user

    u = get_or_create_user("whatsapp:+56972220002")
    run_tool("set_personality", {"emojis": 2}, user_id=u.id)
    assert get_personality(u.id)["emojis"] == 2
    assert "Emojis: 2/10" in run_tool("get_personality", {}, user_id=u.id)
