"""Configuración de tests: SQLite temporal, acceso de desarrollo y precios simulados.

Las variables de entorno se fijan ANTES de importar la app, porque
config/settings.py las lee al importarse.
"""
import os
import sys
import tempfile

_DB = os.path.join(tempfile.mkdtemp(prefix="finmate-tests-"), "test.db")
os.environ["DATABASE_URL"] = "sqlite:///" + _DB
os.environ["PANEL_DEV_LOGIN"] = "true"
os.environ["FLASK_DEBUG"] = "true"
os.environ["FLASK_SECRET_KEY"] = "test-secret"
os.environ.setdefault("FINNHUB_API_KEY", "test")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

PRICES = {
    "AAPL": {"price": 342.37, "change_pct": -0.52, "is_closed": False},
    "MSFT": {"price": 468.20, "change_pct": 0.84, "is_closed": False},
    "TLT": {"price": 88.70, "change_pct": 0.31, "is_closed": False},
    "XOM": {"price": 104.60, "change_pct": -1.87, "is_closed": False},
    "NVDA": {"price": 186.64, "change_pct": 2.78, "is_closed": False},
}
PROFILES = {"AAPL": {"finnhubIndustry": "Technology"}, "MSFT": {"finnhubIndustry": "Technology"},
            "XOM": {"finnhubIndustry": "Energy"}}


@pytest.fixture(autouse=True)
def fake_market(monkeypatch):
    from finmate.services import quotes

    monkeypatch.setattr(quotes, "get_quote", lambda s: PRICES.get(s.upper()))
    monkeypatch.setattr(quotes, "get_profile", lambda s: PROFILES.get(s.upper(), {}))


@pytest.fixture(scope="session", autouse=True)
def app():
    # Importar main corre init_db() (crea las tablas en la SQLite de tests).
    from main import app as flask_app

    flask_app.config.update(TESTING=True)
    return flask_app


_counter = {"n": 0}


@pytest.fixture
def client(app):
    """Cliente con sesión iniciada como un usuario nuevo (número único por test)."""
    _counter["n"] += 1
    c = app.test_client()
    r = c.post("/api/auth/dev-login", json={"phone": f"+5690000{_counter['n']:04d}"}, headers={"X-Finmate": "1"})
    assert r.status_code == 200, r.get_json()
    return c


def H():
    return {"X-Finmate": "1"}


@pytest.fixture(autouse=True)
def reset_security_guard():
    """Todos los tests salen de la misma IP: se reinician los límites entre tests."""
    from finmate.security import guard

    guard.reset()
    yield
    guard.reset()
