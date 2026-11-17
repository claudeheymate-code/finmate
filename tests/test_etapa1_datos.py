"""Etapa 1: modelo de datos, migración, valorización y categorías."""
import datetime as dt

from sqlalchemy import create_engine, inspect, text


def _user(phone):
    from finmate.db.repository import get_or_create_user

    return get_or_create_user(phone).id


def test_migracion_agrega_columnas_a_tablas_viejas(tmp_path, monkeypatch):
    """Una base con las tablas de antes recibe las columnas nuevas sin perder datos."""
    from finmate.db import models

    url = "sqlite:///" + str(tmp_path / "vieja.db")
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text("CREATE TABLE portfolio_holdings (id INTEGER PRIMARY KEY, user_id INTEGER, symbol VARCHAR(16), quantity FLOAT, avg_cost FLOAT, created_at DATETIME, updated_at DATETIME)"))
        c.execute(text("CREATE TABLE transactions (id INTEGER PRIMARY KEY, user_id INTEGER, amount FLOAT, category VARCHAR(100), description VARCHAR(500), date DATETIME, raw_text VARCHAR(500), created_at DATETIME)"))
        c.execute(text("INSERT INTO portfolio_holdings (user_id, symbol, quantity) VALUES (1, 'AAPL', 10)"))
    monkeypatch.setattr(models, "_engine", eng)
    models._ensure_added_columns()
    cols = {c["name"] for c in inspect(eng).get_columns("portfolio_holdings")}
    assert {"asset_class", "sector"} <= cols
    tcols = {c["name"] for c in inspect(eng).get_columns("transactions")}
    assert {"occasion", "merchant", "receipt_url"} <= tcols
    with eng.connect() as c:
        assert c.execute(text("SELECT symbol FROM portfolio_holdings")).scalar() == "AAPL"
    models._ensure_added_columns()  # segunda vez: no rompe


def test_clasificacion_de_activos():
    from finmate.services.portfolio import classify_symbol

    assert classify_symbol("TLT", lambda s: {}) == ("Renta fija", "Bonos")
    assert classify_symbol("VOO", lambda s: {}) == ("Renta variable", "Índice amplio")
    assert classify_symbol("XOM", lambda s: {"finnhubIndustry": "Energy"}) == ("Renta variable", "Energía")
    assert classify_symbol("ZZZ", lambda s: {}) == ("Renta variable", "Otros")


def test_valorizacion_ganancia_distribucion_y_top():
    from finmate.db.repository import add_or_update_holding
    from finmate.services.portfolio import compute_portfolio

    uid = _user("whatsapp:+56911110001")
    add_or_update_holding(uid, "AAPL", 10, 150)
    add_or_update_holding(uid, "TLT", 25, 92)
    add_or_update_holding(uid, "XOM", 12, 118)
    add_or_update_holding(uid, "NOPRICE", 1, 10)
    pf = compute_portfolio(uid)

    t = pf["totals"]
    assert round(t["value"], 2) == round(3423.70 + 2217.50 + 1255.20, 2)
    assert round(t["pnl"], 2) == round(1923.70 - 82.50 - 160.80, 2)
    assert pf["missing_prices"] == ["NOPRICE"]
    by_class = {g["name"]: round(g["pct"], 1) for g in pf["by_class"]}
    assert set(by_class) == {"Renta variable", "Renta fija"}
    assert round(sum(by_class.values())) == 100
    assert [p["symbol"] for p in pf["top_winners"]] == ["AAPL"]
    assert [p["symbol"] for p in pf["top_losers"]] == ["XOM", "TLT"]
    sectors = {g["name"] for g in pf["by_sector"]}
    assert {"Tecnología", "Bonos", "Energía"} <= sectors


def test_clasificacion_queda_guardada():
    from finmate.db.repository import add_or_update_holding, get_portfolio_detailed
    from finmate.services.portfolio import compute_portfolio

    uid = _user("whatsapp:+56911110002")
    add_or_update_holding(uid, "MSFT", 1, 400)
    compute_portfolio(uid)
    h = get_portfolio_detailed(uid)[0]
    assert (h["asset_class"], h["sector"]) == ("Renta variable", "Tecnología")


def test_categorias_nuevas_y_desglose_mensual():
    from finmate.db import finance_repo

    uid = _user("whatsapp:+56911110003")
    today = dt.date.today()
    py, pm = finance_repo.previous_month(today.year, today.month)
    finance_repo.add_transaction(uid, -8000, "Comidas", "Almuerzo", today, occasion="Trabajo")
    finance_repo.add_transaction(uid, -42000, "Polola", "Cena", today)
    finance_repo.add_transaction(uid, -5000, "Alimentación", "vieja", today)  # categoría vieja: aparece aparte
    finance_repo.add_transaction(uid, 500000, "Otros", "Sueldo", today)
    finance_repo.add_transaction(uid, -30000, "Viajes", "Bus", dt.date(py, pm, 10))

    cur = finance_repo.month_breakdown(uid, today.year, today.month)
    assert cur["total_gastos"] == 55000 and cur["count"] == 3
    amounts = {c["name"]: c["amount"] for c in cur["categories"]}
    assert amounts["Comidas"] == 8000 and amounts["Polola"] == 42000 and amounts["Alimentación"] == 5000
    names = [c["name"] for c in cur["categories"]]
    assert names[:8] == finance_repo.DEFAULT_CATEGORIES and names[-1] == "Otros"
    assert sum(c["amount"] for c in cur["categories"]) == cur["total_gastos"]  # el total siempre cuadra
    prev = finance_repo.month_breakdown(uid, py, pm)
    assert prev["total_gastos"] == 30000

    items = finance_repo.list_transactions(uid, today.year, today.month, "Comidas")
    assert items[0]["occasion"] == "Trabajo"
    tx = finance_repo.update_transaction(uid, items[0]["id"], category="Copete")
    assert tx["category"] == "Copete"
    assert finance_repo.update_transaction(uid + 999, items[0]["id"], category="Asados") is None


def test_tool_add_expense_usa_categorias_y_ocasion():
    from finmate.agent.finance_tools import _normalize_category, tool_add_expense
    from finmate.db import finance_repo

    assert _normalize_category("comidas") == "Comidas"
    assert _normalize_category("almuerzo") == "Comidas"
    assert _normalize_category("cumpleaños") == "Carretes"
    assert _normalize_category("netflix") == "Suscripciones" and _normalize_category("apuesta") == "Bets"
    assert _normalize_category("bencina", ["Comidas", "Bencina", "Otros"]) == "Bencina"
    assert _normalize_category("asado", ["Comidas", "Otros"]) == "Otros"  # Asados sacada por el usuario
    assert _normalize_category("algo raro") == "Otros"
    uid = _user("whatsapp:+56911110004")
    msg = tool_add_expense(uid, {"tipo": "gasto", "amount": 25000, "category": "regalos", "description": "regalo", "occasion": "Cumpleaños de la Cata"})
    assert "Regalos" in msg and "Cumpleaños de la Cata" in msg
    t = finance_repo.list_transactions(uid, dt.date.today().year, dt.date.today().month)[0]
    assert t["amount"] == -25000 and t["occasion"] == "Cumpleaños de la Cata"


def test_avisos_por_usuario():
    from finmate.db import settings_repo

    uid = _user("whatsapp:+56911110005")
    assert settings_repo.get_notification_settings(uid)["weekly_summary_enabled"] is True
    settings_repo.set_notification_settings(uid, watchlist_threshold_pct=3, weekly_summary_enabled=False)
    assert settings_repo.get_thresholds_by_user()[uid] == 3
    assert settings_repo.weekly_summary_enabled_for_phone("whatsapp:+56911110005") is False
    assert settings_repo.weekly_summary_enabled_for_phone("whatsapp:+56999999999") is True
    try:
        settings_repo.set_notification_settings(uid, watchlist_threshold_pct=99)
        raise AssertionError("debía rechazar 99%")
    except ValueError:
        pass


def test_alerta_watchlist_respeta_umbral_por_usuario(monkeypatch):
    from finmate.alerts import watchlist_alerts
    from finmate.db import repository, settings_repo

    a = _user("whatsapp:+56911110006")
    b = _user("whatsapp:+56911110007")
    repository.add_to_watchlist(a, "NVDA")
    repository.add_to_watchlist(b, "NVDA")
    settings_repo.set_notification_settings(a, watchlist_threshold_pct=2)   # NVDA +2,78% → avisa
    settings_repo.set_notification_settings(b, watchlist_threshold_pct=10)  # no avisa

    monkeypatch.setattr(watchlist_alerts, "get_all_watchlist_entries", lambda: [(a, "whatsapp:+56911110006", "NVDA"), (b, "whatsapp:+56911110007", "NVDA")])
    monkeypatch.setattr(watchlist_alerts, "_get_finnhub_quote", lambda client, s: {"price": 186.64, "change_pct": 2.78, "is_closed": False})
    monkeypatch.setattr(watchlist_alerts, "_load_state", lambda: {})
    monkeypatch.setattr(watchlist_alerts, "_save_state", lambda st: None)
    sent = []

    class FakeMessenger:
        def send_message(self, to, body):
            sent.append(to)
            return True

        def send_template(self, to, sid, variables=None):
            sent.append(to)
            return True

    watchlist_alerts.check_watchlist_alerts(FakeMessenger())
    assert sent == ["whatsapp:+56911110006"]


def test_bot_maneja_categorias_por_usuario():
    from finmate.agent.finance_tools import tool_add_expense, tool_manage_expense_categories
    from finmate.db import finance_repo

    uid = _user("whatsapp:+56911110009")
    assert "Bencina" in tool_manage_expense_categories(uid, {"action": "add", "name": "bencina"})
    msg = tool_add_expense(uid, {"tipo": "gasto", "amount": 30000, "category": "bencina", "description": "estanque"})
    assert "Bencina" in msg
    assert "Saqué" in tool_manage_expense_categories(uid, {"action": "remove", "name": "Bets"})
    lista = tool_manage_expense_categories(uid, {"action": "list"})
    assert "Bencina" in lista and "Sacaste: Bets" in lista
    # Con Bets sacada, "apuesta" ya no cae en Bets
    tool_add_expense(uid, {"tipo": "gasto", "amount": 5000, "category": "apuesta", "description": "partido"})
    t = finance_repo.list_transactions(uid, dt.date.today().year, dt.date.today().month)[0]
    assert t["category"] == "Otros"
    assert "Bencina" not in finance_repo.get_categories(_user("whatsapp:+56911110010"))
