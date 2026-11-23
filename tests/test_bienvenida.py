"""Bienvenida por chat: el bot se presenta y guía la configuración."""
import itertools

_ids = itertools.count(1)


def _user(phone=None):
    from finmate.db.repository import get_or_create_user

    return get_or_create_user(phone or f"whatsapp:+5690000{next(_ids):04d}")


def test_usuario_nuevo_queda_en_bienvenida():
    from finmate.agent.setup_tools import onboarding_status, start_onboarding_if_new

    u = _user()
    assert start_onboarding_if_new(u.id, has_history=False) == "en_curso"
    assert onboarding_status(u.id) == "en_curso"


def test_usuario_antiguo_no_repite_bienvenida():
    from finmate.agent.setup_tools import start_onboarding_if_new

    u = _user()
    assert start_onboarding_if_new(u.id, has_history=True) == "listo"


def test_terminar_y_reiniciar_bienvenida():
    from finmate.agent.setup_tools import onboarding_status, tool_onboarding

    u = _user()
    tool_onboarding(u.id, {"action": "complete"})
    assert onboarding_status(u.id) == "listo"
    tool_onboarding(u.id, {"action": "restart"})
    assert onboarding_status(u.id) == "en_curso"


def test_contexto_muestra_configuracion():
    from finmate.agent.setup_tools import start_onboarding_if_new, user_context
    from finmate.db.repository import add_to_watchlist

    u = _user()
    start_onboarding_if_new(u.id, has_history=False)
    add_to_watchlist(u.id, "TSLA")
    ctx = user_context(u.id, "Joaco")
    assert "Joaco" in ctx and "en_curso" in ctx and "TSLA" in ctx
    assert "noticias por día" in ctx


def test_ajustes_de_frecuencia_por_chat():
    from finmate.agent.setup_tools import tool_set_notification_settings
    from finmate.db.settings_repo import get_notification_settings

    u = _user()
    out = tool_set_notification_settings(u.id, {"watchlist_threshold_pct": 7, "news_max_per_day": 2})
    assert "guardado" in out
    s = get_notification_settings(u.id)
    assert s["watchlist_threshold_pct"] == 7 and s["news_max_per_day"] == 2
    assert "No pude" in tool_set_notification_settings(u.id, {"news_max_per_day": 50})


def test_prompt_incluye_contexto_y_bienvenida():
    from finmate.agent.orchestrator import _build_system_prompt

    blocks = _build_system_prompt({}, "- Bienvenida: en_curso")
    text = " ".join(b["text"] for b in blocks)
    assert "BIENVENIDA" in text and "en_curso" in text and "Watchlist" in text


def test_nombre_de_perfil_llega_desde_meta():
    from finmate.whatsapp.meta_cloud import parse_incoming

    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "56911111111", "profile": {"name": "Joaco"}}],
        "messages": [{"from": "56911111111", "id": "w1", "type": "text", "text": {"body": "Hola"}}],
    }}]}]}
    assert parse_incoming(payload)[0]["name"] == "Joaco"


def test_nombre_se_guarda_una_vez():
    from finmate.db.models import User, get_session
    from finmate.db.repository import set_user_name_if_empty

    u = _user()
    set_user_name_if_empty(u.id, "Joaco")
    set_user_name_if_empty(u.id, "Otro")
    s = get_session()
    try:
        assert s.get(User, u.id).name == "Joaco"
    finally:
        s.close()
