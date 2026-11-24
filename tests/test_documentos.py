"""Fotos y PDFs: llegan a Claude como imagen/documento, se usa el modelo de análisis,
el historial guarda solo una nota, y las tools en bloque registran gastos y posiciones."""
from types import SimpleNamespace


def _fake_client(calls, text="Encontré 3 gastos: ¿los registro?"):
    def create(**kw):
        calls.append(kw)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)], usage=None)
    return SimpleNamespace(messages=SimpleNamespace(create=create))


def test_foto_llega_a_claude_con_modelo_de_analisis(monkeypatch):
    from finmate.agent import orchestrator as orch
    from finmate.db.repository import get_or_create_user, get_recent_history

    calls = []
    monkeypatch.setattr(orch, "_client", _fake_client(calls))
    u = get_or_create_user("whatsapp:+56933330001")
    att = [{"kind": "image", "media_type": "image/jpeg", "data": "QUJD", "name": "foto"},
           {"kind": "pdf", "media_type": "application/pdf", "data": "UERG", "name": "cartola.pdf"}]
    r = orch.handle_message("whatsapp:+56933330001", "registra mis gastos", attachments=att)
    assert "registro" in r
    kw = calls[0]
    assert kw["model"] == orch.ANTHROPIC_MODEL_ANALYSIS
    content = kw["messages"][-1]["content"]
    assert [b["type"] for b in content] == ["image", "document", "text"]
    hist = get_recent_history(u.id)
    assert any(role == "user" and "[Mandó 1 foto y archivo(s): cartola.pdf]" in txt for role, txt in hist)
    assert not any("QUJD" in txt for _, txt in hist)          # la imagen no se guarda


def test_respuesta_sin_texto_se_completa(monkeypatch):
    """Antes: 'No pude generar una respuesta' cuando se acababan las rondas de tools."""
    from finmate.agent import orchestrator as orch

    calls = []

    def create(**kw):
        calls.append(kw)
        if kw.get("tool_choice", {}).get("type") == "none":
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Listo, aquí va.")], usage=None)
        return SimpleNamespace(stop_reason="tool_use", usage=None,
                               content=[SimpleNamespace(type="tool_use", id=f"t{len(calls)}", name="get_market_data", input={})])

    monkeypatch.setattr(orch, "_client", SimpleNamespace(messages=SimpleNamespace(create=create)))
    monkeypatch.setattr(orch, "run_tool", lambda *a, **k: "datos")
    from finmate.db.repository import get_or_create_user

    get_or_create_user("whatsapp:+56933330002")          # usuario con acceso
    r = orch.handle_message("whatsapp:+56933330002", "¿cómo está todo el mercado hoy?")
    assert r == "Listo, aquí va."
    assert calls[-1]["tool_choice"] == {"type": "none"}


def test_error_de_clave_de_claude_avisa_en_admin(monkeypatch):
    from finmate.agent import orchestrator as orch
    from finmate.security.monitor import list_events

    def create(**kw):
        raise RuntimeError("Error code: 401 - authentication_error invalid x-api-key")

    monkeypatch.setattr(orch, "_client", SimpleNamespace(messages=SimpleNamespace(create=create)))
    monkeypatch.setattr("finmate.security.monitor._notify_admins", lambda *a: None)
    from finmate.db.repository import get_or_create_user

    get_or_create_user("whatsapp:+56933330003")
    orch.handle_message("whatsapp:+56933330003", "hola")
    assert any(e["kind"] == "claude_error" for e in list_events())


def test_registrar_gastos_en_bloque():
    from finmate.agent.document_tools import tool_add_expenses_batch
    from finmate.db.repository import get_or_create_user

    u = get_or_create_user("whatsapp:+56933330004")
    r = tool_add_expenses_batch(u.id, {"items": [
        {"tipo": "gasto", "amount": 12000, "category": "Comidas", "description": "almuerzo", "date_str": "2026-11-20"},
        {"tipo": "gasto", "amount": 8990, "category": "Suscripciones", "description": "netflix"},
        {"tipo": "ingreso", "amount": 50000, "category": "Otros", "description": "devolución"},
    ]})
    assert r.startswith("✅ Registré 3 de 3")


def test_importar_portafolio_reemplaza_cantidades():
    from finmate.agent.document_tools import tool_import_portfolio
    from finmate.db.repository import add_or_update_holding, get_or_create_user, get_portfolio

    u = get_or_create_user("whatsapp:+56933330005")
    add_or_update_holding(u.id, "AAPL", 3, 100)
    add_or_update_holding(u.id, "TSLA", 1, 200)
    r = tool_import_portfolio(u.id, {"mode": "replace", "positions": [
        {"symbol": "AAPL", "quantity": 10, "avg_cost": 150}, {"symbol": "MSFT", "quantity": 5}]})
    assert "AAPL 10" in r and "TSLA" in r          # avisa que TSLA no venía en el documento
    pf = {sym: qty for sym, qty, _ in get_portfolio(u.id)}
    assert pf["AAPL"] == 10 and pf["MSFT"] == 5 and pf["TSLA"] == 1
