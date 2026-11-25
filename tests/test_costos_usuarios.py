"""Costo por usuario en el panel admin: consumo de Claude y WhatsApp anotado a cada número."""
import pytest

H = {"X-Finmate": "1"}


class _U:
    input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens = 1_000_000, 200_000, 0, 0


@pytest.fixture
def admin(app, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "ADMIN_DEV_LOGIN", True)
    c = app.test_client()
    assert c.post("/admin/api/dev-login", json={"email": "claude.heymate@gmail.com"}, headers=H).status_code == 200
    return c


def test_consumo_se_anota_al_usuario():
    from finmate.services import usage

    with usage.for_user("whatsapp:+56973330001"):
        usage.record_claude("claude-haiku-5-5", _U())
    usage.record_claude("claude-haiku-5-5", _U())                 # sin usuario: solo al total
    usage.record_whatsapp("template", True, to="56973330001")
    usage.record_whatsapp("text", True, to="56973330001")
    u = usage.get_user_usage()["56973330001"]
    assert u["claude"]["claude-haiku-5-5"]["input_tokens"] == 1_000_000
    assert u["wa"] == {"template": 1, "text": 1}
    assert usage.tracking_since()


def test_handle_message_anota_a_quien_escribe(monkeypatch):
    from finmate.agent import orchestrator
    from finmate.services import usage

    seen = {}
    monkeypatch.setattr(orchestrator, "_handle_message",
                        lambda phone, *a, **k: seen.setdefault("who", usage._CURRENT.get()) or "ok")
    orchestrator.handle_message("whatsapp:+56973330009", "hola")
    assert seen["who"] == "56973330009" and usage._CURRENT.get() is None


def test_panel_muestra_costo_por_usuario_y_niveles(admin):
    from finmate.db.models import ConversationTurn, get_session
    from finmate.db.repository import get_or_create_user, set_access_status
    from finmate.services import usage

    u = get_or_create_user("whatsapp:+56973330002")
    set_access_status(u.id, "approved")
    s = get_session()
    for _ in range(40):
        s.add(ConversationTurn(user_id=u.id, role="user", content="hola"))
    s.commit(); s.close()
    with usage.for_user(u.phone):
        usage.record_claude("claude-haiku-5-5", _U())             # 1M in × 0,10 + 0,2M out × 0,50 = US$0,20
    admin.put("/admin/api/precios", json={"model": "claude-haiku-5-5", "in": 0.10, "out": 0.50}, headers=H)
    admin.put("/admin/api/precios", json={"whatsapp_template_usd": 0.01}, headers=H)
    usage.record_whatsapp("template", True, to="56973330002")      # + US$0,01

    d = admin.get("/admin/api/usuarios", headers=H).get_json()
    row = next(r for r in d["users"] if r["id"] == u.id)
    assert row["month_messages"] == 40
    assert row["cost_claude_usd"] == pytest.approx(0.2) and row["cost_whatsapp_usd"] == pytest.approx(0.01)
    assert row["cost_usd"] == pytest.approx(0.21) and row["cost_per_message_usd"] == pytest.approx(0.21 / 40, rel=1e-3)
    tiers = {t["key"]: t for t in d["costs"]["tiers"]}
    assert tiers["medio"]["users"] >= 1 and tiers["alto"]["typical_messages"] == 300
    assert d["costs"]["avg_cost_per_message_usd"] is not None
    assert all(t["projected_usd"] is not None for t in tiers.values())
    csv_text = admin.get("/admin/api/usuarios.csv").get_data(as_text=True)
    assert "Costo del mes (USD)" in csv_text
