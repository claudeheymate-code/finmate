"""Perfil de noticias: notas 1-3, aprendizaje gradual, dónde se ve cada nivel,
botones de WhatsApp, resumen de jornada y panel."""
import pytest

H = {"X-Finmate": "1"}


class FakeMessenger:
    def __init__(self):
        self.sent, self.buttons = [], []

    def send_message(self, to, body):
        self.sent.append((to, body))
        return True

    def send_buttons(self, to, body, buttons, fallback=None):
        self.buttons.append((to, body, buttons))
        return True

    def send_template(self, to, name, variables=None):
        self.sent.append((to, f"TEMPLATE {name}"))
        return True


@pytest.fixture(autouse=True)
def _sin_template(monkeypatch):
    monkeypatch.setattr("config.settings.TEMPLATE_MARKET_NOTIFY", "")


_n = {"i": 0}


def _user():
    from finmate.db.repository import get_or_create_user

    _n["i"] += 1
    return get_or_create_user(f"whatsapp:+5697000{_n['i']:04d}")


def _news(headline="Fed signals rate cut in December", symbol="", kind="mercado"):
    from finmate.services.news_profile import make_item

    return make_item(kind, headline, symbol=symbol, source="Reuters")


def test_clasifica_temas():
    from finmate.services.news_profile import classify

    assert classify("Fed signals rate cut as inflation cools") == ["tasas", "inflacion"]
    assert classify("Nvidia beats earnings on AI chip demand")[0] in ("resultados", "ia_tecnologia")
    assert classify("Bitcoin jumps past record") == ["cripto"]
    assert classify("Something unrelated happens") == ["general"]


def test_sin_notas_todo_sigue_por_el_chat():
    from finmate.services import news_profile as np_

    u = _user()
    r = np_.route(u.id, _news())
    assert r["level"] == 3 and r["action"] == "chat" and r["evidence"] == 0


def test_un_uno_no_borra_el_tema_baja_de_a_poco():
    """Las notas 1 bajan el tema de a poco: primero al resumen, después cada vez menos,
    y solo con muchas notas se da por no relevante."""
    from finmate.services import news_profile as np_

    u = _user()
    levels, discarded_at = [], None
    for i in range(30):
        it = _news(f"Bitcoin and crypto rally day {i}")
        np_.remember(u.id, it, "chat")
        np_.record_rating(u.id, it["id"], 1)
        est = np_.estimate(u.id, _news("Bitcoin crypto slump"))
        levels.append(est["level"])
        if est["discarded"] and discarded_at is None:
            discarded_at = i + 1
    assert levels[0] == 3                        # una nota sola no cambia nada todavía
    assert levels.index(2) >= 1                  # después pasa al resumen…
    assert levels.index(1) > levels.index(2)     # …luego a nivel 1 (cada vez menos)…
    assert discarded_at and discarded_at >= 10   # …y solo con muchas notas deja de aparecer
    assert np_.route(u.id, _news("Bitcoin crypto slump"))["action"] == "pedido"
    # Otros temas no se ven afectados
    assert np_.route(u.id, _news("Oil prices surge after OPEC cut"))["level"] == 3


def test_nivel_1_aparece_cada_vez_menos():
    from finmate.services import news_profile as np_

    assert np_._show_probability({"score": 1.55, "discarded": False}) > \
        np_._show_probability({"score": 1.2, "discarded": False}) > 0
    assert np_._show_probability({"score": 1.2, "discarded": True}) == 0


def test_dos_y_tres_suben_y_se_aprende_por_empresa():
    from finmate.services import news_profile as np_

    u = _user()
    for i in range(4):
        it = _news(f"Apple news number {i}", symbol="AAPL", kind="activo")
        np_.remember(u.id, it, "chat")
        np_.record_rating(u.id, it["id"], 2)
    assert np_.estimate(u.id, _news("Apple something", symbol="AAPL", kind="activo"))["level"] == 2
    prof = {p["key"]: p for p in np_.profile(u.id)}
    assert prof["sym:AAPL"]["ratings"] == 4 and prof["sym:AAPL"]["level"] == 2


def test_nivel_fijado_a_mano_manda_y_display_configurable():
    from finmate.services import news_profile as np_

    u = _user()
    np_.set_manual(u.id, "tema:tasas", 1)
    assert np_.route(u.id, _news())["action"] == "pedido"
    np_.set_manual(u.id, "tema:tasas", 2)
    assert np_.route(u.id, _news())["action"] == "resumen"
    np_.set_display(u.id, level2="chat")
    assert np_.route(u.id, _news())["action"] == "chat"
    with pytest.raises(ValueError):
        np_.set_display(u.id, level3="pedido")


def test_fuera_de_jornada_va_al_resumen():
    from finmate.services import news_profile as np_

    u = _user()
    m = FakeMessenger()
    assert np_.deliver(u.id, u.phone, _news(), m, in_workday=False) == "resumen"
    assert not m.buttons
    assert [d["headline"] for d in np_.pop_digest(u.id)] == ["Fed signals rate cut in December"]


def test_noticia_por_chat_con_botones_y_nota_por_boton():
    from finmate.agent.orchestrator import handle_rating_button
    from finmate.db.repository import set_access_status
    from finmate.services import news_profile as np_

    u = _user()
    set_access_status(u.id, "approved")
    m = FakeMessenger()
    it = _news()
    assert np_.deliver(u.id, u.phone, it, m) == "chat"
    to, body, buttons = m.buttons[-1]
    assert to == u.phone and "Fed signals rate cut" in body
    assert [b[1] for b in buttons] == ["1 · Poco", "2 · Algo", "3 · Mucho"]
    reply = handle_rating_button(u.phone, buttons[0][0], "1 · Poco")
    assert reply.startswith("Anotado: 1")
    assert np_.profile(u.id)[0]["ratings"] == 1


def test_nota_por_texto_solo_si_lo_ultimo_fue_una_noticia():
    from finmate.services import news_profile as np_

    u = _user()
    it = _news()
    np_.remember(u.id, it, "chat")
    # Si lo último que dijo el bot no fue una noticia, "2" es una respuesta normal.
    assert np_.try_handle_rating(u.id, "2", last_assistant="¿Prefieres 1) pocos, 2) normal o 3) todo?") is None
    reply = np_.try_handle_rating(u.id, "3", last_assistant=np_.chat_text(it))
    assert reply and reply.startswith("Anotado: 3")


def test_codigos_del_resumen():
    from finmate.services import news_profile as np_

    u = _user()
    a, b = _news("Fed holds rates"), _news("Oil jumps on OPEC cut")
    np_.push_digest(u.id, a, 2)
    np_.push_digest(u.id, b, 1)
    items = np_.assign_brief_codes(u.id, np_.pop_digest(u.id))
    assert [i["code"] for i in items] == ["a", "b"] and items[0]["headline"] == "Fed holds rates"
    reply = np_.try_handle_rating(u.id, "a3 b1")
    assert reply and "a3" in reply and "b1" in reply
    assert np_.try_handle_rating(u.id, "hola, ¿cómo estás?") is None


def test_resumen_incluye_noticias_para_ti(monkeypatch):
    from finmate.agent import orchestrator
    from finmate.services.daily_brief import compose

    monkeypatch.setattr(orchestrator, "_client", None)
    txt = compose({"noticias_para_ti": [{"code": "a", "symbol": "NVDA", "headline": "Nvidia beats", "level": 2}]}, "end")
    assert "📰 *Noticias para ti*" in txt and "a) NVDA: Nvidia beats" in txt and "a3 b1" in txt


def test_motor_general_usa_el_perfil(monkeypatch):
    from finmate.alerts.engine import AlertEngine

    u = _user()
    eng = AlertEngine.__new__(AlertEngine)
    eng.messenger = FakeMessenger()
    eng._broadcast_or_queue("texto", "Noticia de mercado", [u.phone, "whatsapp:+10000000000"], news=_news())
    assert len(eng.messenger.buttons) == 1 and eng.messenger.buttons[0][0] == u.phone


def test_historial_para_claude_alterna_roles():
    from finmate.agent.orchestrator import _clean_history

    h = [("assistant", "resumen"), ("user", "hola"), ("assistant", "noticia 1"), ("assistant", "noticia 2"),
         ("user", "sin respuesta")]
    out = _clean_history(h)
    assert [m["role"] for m in out] == ["user", "assistant"]
    assert out[1]["content"] == "noticia 1\n\nnoticia 2"


def test_bienvenida_explica_los_niveles():
    from finmate.web.admin import approval_message

    body = approval_message("Camila Rojas")
    assert "Nivel 3" in body and "Nivel 2" in body and "Nivel 1" in body and "No es blanco o negro" in body


def test_panel_perfil_de_noticias(client):
    r = client.get("/api/noticias/perfil", headers=H)
    d = r.get_json()
    assert d["display"] == {"level3": "chat", "level2": "resumen", "level1": "gradual"} and d["profile"] == []
    assert any(t["key"] == "tema:cripto" for t in d["topics"])
    d = client.put("/api/noticias/display", json={"level1": "pedido"}, headers=H).get_json()
    assert d["display"]["level1"] == "pedido"
    assert client.put("/api/noticias/display", json={"level3": "nunca"}, headers=H).status_code == 400
    d = client.put("/api/noticias/perfil", json={"key": "tema:cripto", "level": 1}, headers=H).get_json()
    assert d["profile"][0]["key"] == "tema:cripto" and d["profile"][0]["status"] == "fijado"
    assert client.put("/api/noticias/perfil", json={"key": "tema:cripto", "level": 5}, headers=H).status_code == 400
    d = client.delete("/api/noticias/perfil", json={"key": "tema:cripto"}, headers=H).get_json()
    assert d["profile"] == []


def test_tool_del_bot():
    from finmate.agent.tools import run_tool

    u = _user()
    assert "Todavía no tengo notas" in run_tool("get_news_profile", {}, user_id=u.id)
    assert "nivel 1" in run_tool("set_news_preference", {"topic": "cripto", "level": 1}, user_id=u.id)
    assert "Cripto: nivel 1 (fijado por ti)" in run_tool("get_news_profile", {}, user_id=u.id)
