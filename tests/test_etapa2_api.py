"""Etapa 2: API del panel (/api/*)."""
import datetime as dt

from tests.conftest import H


def test_sin_sesion_da_401(app):
    c = app.test_client()
    assert c.get("/api/resumen").status_code == 401
    assert c.get("/api/portafolio").status_code == 401


def test_cambios_sin_encabezado_csrf_se_rechazan(client):
    r = client.post("/api/watchlist", json={"symbol": "NVDA"})
    assert r.status_code == 403
    assert client.post("/api/watchlist", json={"symbol": "NVDA"}, headers=H()).status_code == 201


def test_dev_login_valida_numero(app):
    c = app.test_client()
    r = c.post("/api/auth/dev-login", json={"phone": "hola"}, headers=H())
    assert r.status_code == 400


def test_dev_login_apagado_por_defecto(app, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "PANEL_DEV_LOGIN", False)
    r = app.test_client().post("/api/auth/dev-login", json={"phone": "+56912345678"}, headers=H())
    assert r.status_code == 404


def test_portafolio_completo(client):
    for sym, q, a in [("AAPL", 10, 150), ("TLT", 25, 92), ("XOM", 12, 118)]:
        assert client.post("/api/portafolio", json={"symbol": sym, "quantity": q, "avg_cost": a}, headers=H()).status_code == 201
    d = client.get("/api/portafolio").get_json()
    assert d["totals"]["count"] == 3
    assert d["top_winners"][0]["symbol"] == "AAPL"
    assert {g["name"] for g in d["by_class"]} == {"Renta variable", "Renta fija"}
    # corregir el sector a mano
    assert client.patch("/api/portafolio/XOM", json={"sector": "Petróleo"}, headers=H()).status_code == 200
    d = client.get("/api/portafolio").get_json()
    assert "Petróleo" in {g["name"] for g in d["by_sector"]}
    assert client.delete("/api/portafolio/XOM", headers=H()).status_code == 200
    assert client.delete("/api/portafolio/XOM", headers=H()).status_code == 404


def test_portafolio_valida_entradas(client):
    assert client.post("/api/portafolio", json={"symbol": "no valido!", "quantity": 1}, headers=H()).status_code == 400
    assert client.post("/api/portafolio", json={"symbol": "AAPL", "quantity": 0}, headers=H()).status_code == 400
    assert client.patch("/api/portafolio/AAPL", json={"asset_class": "Cripto"}, headers=H()).status_code == 400


def test_watchlist(client):
    client.post("/api/watchlist", json={"symbol": "nvda"}, headers=H())
    items = client.get("/api/watchlist").get_json()["items"]
    assert items[0]["symbol"] == "NVDA" and items[0]["price"] == 186.64 and items[0]["threshold_pct"] == 5
    assert client.delete("/api/watchlist/NVDA", headers=H()).status_code == 200


def test_finanzas_flujo_completo(client):
    r = client.post("/api/finanzas/movimientos", json={"tipo": "gasto", "amount": 42000, "category": "Polola", "occasion": "Aniversario", "description": "Cena"}, headers=H())
    assert r.status_code == 201
    tx = r.get_json()
    assert tx["amount"] == -42000 and tx["occasion"] == "Aniversario"
    client.post("/api/finanzas/movimientos", json={"tipo": "gasto", "amount": "8000", "category": "Comidas"}, headers=H())
    res = client.get("/api/finanzas/resumen").get_json()
    assert res["actual"]["total_gastos"] == 50000
    assert "anterior" in res
    lst = client.get("/api/finanzas/movimientos?categoria=Polola").get_json()["items"]
    assert len(lst) == 1
    r = client.patch(f"/api/finanzas/movimientos/{tx['id']}", json={"category": "Regalos"}, headers=H())
    assert r.get_json()["category"] == "Regalos"
    assert client.patch(f"/api/finanzas/movimientos/{tx['id']}", json={"category": "Inventada"}, headers=H()).status_code == 400
    assert client.delete(f"/api/finanzas/movimientos/{tx['id']}", headers=H()).status_code == 200


def test_finanzas_valida(client):
    assert client.post("/api/finanzas/movimientos", json={"tipo": "gasto", "amount": 100}, headers=H()).status_code == 400
    assert client.post("/api/finanzas/movimientos", json={"tipo": "gasto", "amount": -5, "category": "Comidas"}, headers=H()).status_code == 400
    assert client.post("/api/finanzas/movimientos", json={"tipo": "gasto", "amount": 5, "category": "Comidas", "date": "ayer"}, headers=H()).status_code == 400
    assert client.post("/api/finanzas/movimientos", json={"tipo": "gasto", "amount": 5, "category": "Nada"}, headers=H()).status_code == 400
    assert client.get("/api/finanzas/movimientos?categoria=Nada").get_json()["items"] == []


def test_mes_anterior_y_fechas(client):
    today = dt.date.today()
    prev = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=10)
    client.post("/api/finanzas/movimientos", json={"tipo": "gasto", "amount": 30000, "category": "Asados", "date": prev.isoformat()}, headers=H())
    res = client.get("/api/finanzas/resumen").get_json()
    assert res["anterior"]["total_gastos"] == 30000 and res["actual"]["total_gastos"] == 0


def test_aislamiento_entre_usuarios(app, client):
    client.post("/api/portafolio", json={"symbol": "AAPL", "quantity": 1}, headers=H())
    tx = client.post("/api/finanzas/movimientos", json={"tipo": "gasto", "amount": 1000, "category": "Comidas"}, headers=H()).get_json()
    otro = app.test_client()
    otro.post("/api/auth/dev-login", json={"phone": "+56977777777"}, headers=H())
    assert otro.get("/api/portafolio").get_json()["totals"]["count"] == 0
    assert otro.patch(f"/api/finanzas/movimientos/{tx['id']}", json={"category": "Copete"}, headers=H()).status_code == 404
    assert otro.delete(f"/api/finanzas/movimientos/{tx['id']}", headers=H()).status_code == 404


def test_personalidad(client):
    assert client.get("/api/personalidad").get_json()["tono"] == "profesional"
    r = client.put("/api/personalidad", json={"humor": 8, "tono": "casual"}, headers=H())
    assert r.get_json()["humor"] == 8 and r.get_json()["tono"] == "casual"
    assert client.put("/api/personalidad", json={"humor": 11}, headers=H()).status_code == 400
    assert client.put("/api/personalidad", json={"tono": "grosero"}, headers=H()).status_code == 400


def test_seguimientos(client):
    s = client.post("/api/seguimientos", json={"tipo": "indicador", "valor": "cpi_us"}, headers=H()).get_json()
    assert s["indicadores"][0]["code"] == "CPI_US"
    s = client.post("/api/seguimientos", json={"tipo": "sector", "valor": "bancos regionales"}, headers=H()).get_json()
    assert s["temas"] == [{"tipo": "sector", "valor": "bancos regionales"}]
    assert client.post("/api/seguimientos", json={"tipo": "indicador", "valor": "NADA"}, headers=H()).status_code == 400
    assert len(client.get("/api/seguimientos").get_json()["catalogo"]) > 10
    s = client.delete("/api/seguimientos", json={"tipo": "indicador", "valor": "CPI_US"}, headers=H()).get_json()
    assert s["indicadores"] == []


def test_avisos(client):
    base = {"earnings_alerts": "mine", "macro_alerts": False, "market_news_alerts": False}
    assert client.get("/api/avisos").get_json() == {"watchlist_threshold_pct": 5.0, "weekly_summary_enabled": True,
                                                    "news_max_per_day": 6, **base}
    r = client.put("/api/avisos", json={"watchlist_threshold_pct": 3, "weekly_summary_enabled": False,
                                        "news_max_per_day": 2, "earnings_alerts": "all", "macro_alerts": True}, headers=H())
    assert r.get_json() == {"watchlist_threshold_pct": 3.0, "weekly_summary_enabled": False, "news_max_per_day": 2,
                            "earnings_alerts": "all", "macro_alerts": True, "market_news_alerts": False}
    assert client.put("/api/avisos", json={"earnings_alerts": "algunas"}, headers=H()).status_code == 400
    assert client.put("/api/avisos", json={"macro_alerts": "si"}, headers=H()).status_code == 400
    assert client.put("/api/avisos", json={"news_max_per_day": 20}, headers=H()).status_code == 400
    assert client.put("/api/avisos", json={"watchlist_threshold_pct": 0.1}, headers=H()).status_code == 400
    assert client.put("/api/avisos", json={"weekly_summary_enabled": "si"}, headers=H()).status_code == 400


def test_resumen(client):
    client.post("/api/portafolio", json={"symbol": "AAPL", "quantity": 10, "avg_cost": 150}, headers=H())
    client.post("/api/watchlist", json={"symbol": "NVDA"}, headers=H())
    client.post("/api/finanzas/movimientos", json={"tipo": "gasto", "amount": 8000, "category": "Comidas"}, headers=H())
    d = client.get("/api/resumen").get_json()
    assert round(d["portfolio"]["totals"]["value"], 2) == 3423.70
    assert d["watchlist"][0]["symbol"] == "NVDA"
    assert d["finanzas"]["total_gastos"] == 8000 and d["finanzas"]["top_category"] == "Comidas"


def test_chat_usa_el_mismo_agente(client, monkeypatch):
    from finmate.agent import orchestrator

    seen = {}

    def fake_handle(phone, msg):
        seen["phone"], seen["msg"] = phone, msg
        return "Respuesta del agente"

    monkeypatch.setattr(orchestrator, "handle_message", fake_handle)
    r = client.post("/api/chat", json={"message": "¿cómo va Apple?"}, headers=H())
    assert r.get_json() == {"reply": "Respuesta del agente"}
    assert seen["phone"].startswith("whatsapp:+569") and seen["msg"] == "¿cómo va Apple?"
    assert client.post("/api/chat", json={"message": ""}, headers=H()).status_code == 400


def test_me_enmascara_numero(client):
    d = client.get("/api/me").get_json()
    assert "••••" in d["phone"]


def test_categorias_por_usuario(app, client):
    """Cada usuario elige sus categorías: saca las por defecto que no usa y
    agrega las suyas, sin afectar a los demás."""
    c = client.get("/api/finanzas/categorias").get_json()
    assert c["categories"] == ["Comidas", "Carretes", "Asados", "Regalos", "Suscripciones", "Polola", "Copete", "Bets", "Otros"]
    r = client.post("/api/finanzas/categorias", json={"name": "  bencina "}, headers=H())
    assert r.status_code == 201 and r.get_json()["added"] == "Bencina"
    assert client.post("/api/finanzas/categorias", json={"name": "BENCINA"}, headers=H()).status_code == 400  # repetida
    assert client.post("/api/finanzas/categorias", json={"name": "x"}, headers=H()).status_code == 400
    r = client.put("/api/finanzas/categorias", json={"name": "Bets", "active": False}, headers=H()).get_json()
    assert "Bets" not in r["categories"] and "Bencina" in r["categories"] and r["categories"][-1] == "Otros"
    assert {"name": "Bets", "default": True, "active": False} in r["all"]
    assert client.put("/api/finanzas/categorias", json={"name": "Otros", "active": False}, headers=H()).status_code == 400
    # Se puede registrar en la propia, no en la sacada
    assert client.post("/api/finanzas/movimientos", json={"tipo": "gasto", "amount": 20000, "category": "bencina"}, headers=H()).get_json()["category"] == "Bencina"
    assert client.post("/api/finanzas/movimientos", json={"tipo": "gasto", "amount": 5000, "category": "Bets"}, headers=H()).status_code == 400
    # Volver a agregarla por nombre la reactiva
    assert "Bets" in client.post("/api/finanzas/categorias", json={"name": "bets"}, headers=H()).get_json()["categories"]
    # Otro usuario no ve Bencina
    otro = app.test_client()
    otro.post("/api/auth/dev-login", json={"phone": "+56966666666"}, headers=H())
    assert "Bencina" not in otro.get("/api/finanzas/categorias").get_json()["categories"]
    # Al sacar una propia con gastos, el gasto sigue contando en el resumen
    client.put("/api/finanzas/categorias", json={"name": "Bencina", "active": False}, headers=H())
    res = client.get("/api/finanzas/resumen").get_json()
    amounts = {x["name"]: x["amount"] for x in res["actual"]["categories"]}
    assert amounts["Bencina"] == 20000 and res["actual"]["total_gastos"] == sum(amounts.values())
    assert res["anio"]["total_gastos"] >= res["actual"]["total_gastos"]


def test_resumen_trae_el_anio(client):
    today = dt.date.today()
    if today.month > 1:
        client.post("/api/finanzas/movimientos", json={"tipo": "gasto", "amount": 7000, "category": "Comidas", "date": today.replace(month=1, day=15).isoformat()}, headers=H())
    client.post("/api/finanzas/movimientos", json={"tipo": "gasto", "amount": 3000, "category": "Comidas"}, headers=H())
    client.post("/api/finanzas/movimientos", json={"tipo": "gasto", "amount": 9000, "category": "Comidas", "date": today.replace(year=today.year - 1).isoformat()}, headers=H())
    res = client.get("/api/finanzas/resumen").get_json()
    assert res["anio"]["total_gastos"] == (10000 if today.month > 1 else 3000)
