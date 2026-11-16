"""Carga datos de prueba para ver el panel web funcionando.

Uso (con DATABASE_URL apuntando a una base de PRUEBA, nunca a producción):
    python scripts/seed_demo.py +56900000000

Crea (o completa) el usuario de ese número con: 8 posiciones (AAPL y la
watchlist de NVDA son las de las pruebas del bot; el resto es ilustrativo),
gastos de este mes y del anterior con ocasión y categoría, personalidad,
seguimientos y avisos. Es idempotente para el portafolio y la watchlist;
los gastos se vuelven a crear solo si el usuario no tiene ninguno.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finmate.db import finance_repo, news_repo, personality_repo, repository, settings_repo  # noqa: E402
from finmate.db.models import Transaction, get_session, init_db  # noqa: E402
from finmate.services.portfolio import classify_symbol  # noqa: E402
from finmate.web.auth import normalize_phone  # noqa: E402

HOLDINGS = [  # símbolo, cantidad, costo promedio, (clase, sector) para no depender de la red
    ("AAPL", 10, 150.00, ("Renta variable", "Tecnología")),
    ("MSFT", 5, 410.50, ("Renta variable", "Tecnología")),
    ("TLT", 25, 92.00, None),
    ("JPM", 8, 245.00, ("Renta variable", "Financiero")),
    ("KO", 20, 68.00, ("Renta variable", "Consumo")),
    ("XOM", 12, 118.00, ("Renta variable", "Energía")),
    ("TSLA", 3, 420.00, ("Renta variable", "Consumo")),
    ("BND", 15, 72.00, None),
]
# (día, categoría, descripción, ocasión, comercio, monto)
THIS_MONTH = [
    (1, "Evento Social", "Bowling", "Cumpleaños de la Cata", "Bowling Center", 45000),
    (1, "Regalos", "Regalo", "Cumpleaños de la Cata", "Falabella", 25000),
    (7, "Copete", "Previa", "Previa en lo de Nico", "Botillería El Sol", 23500),
    (8, "Comidas", "Almuerzo", "Almuerzo de trabajo", "Café Altura", 8000),
    (9, "Polola", "Cena aniversario", "Aniversario de 1 año", "Restaurante Liguria", 42000),
    (10, "Comidas", "Sushi", "Pedido del domingo", "Sushi Express", 18300),
    (12, "Comidas", "Supermercado", "Compra de la semana", "Supermercado Líder", 28000),
    (14, "Polola", "Cine", "Salida del sábado", "Cinemark", 20000),
    (14, "Copete", "Bar", "Viernes con amigos", "Bar La Junta", 15000),
    (15, "Viajes", "Bus a Viña", "Fin de semana en la costa", "Turbus", 18900),
]
LAST_MONTH = [
    (5, "Evento Social", "Matrimonio", "Matrimonio de mi primo", "", 30000),
    (11, "Polola", "Cena", "Salida del viernes", "", 48000),
    (18, "Copete", "Carrete", "Fiestas Patrias atrasadas", "", 52000),
    (20, "Comidas", "Supermercado", "Compras del mes", "", 61200),
    (24, "Regalos", "Regalo", "Día del profesor", "", 15000),
    (26, "Viajes", "Pasajes", "Viaje al sur", "", 120000),
]


def main(raw_phone: str) -> None:
    phone = normalize_phone(raw_phone)
    if not phone:
        sys.exit("Número inválido. Ej: +56900000000")
    init_db()
    user = repository.get_or_create_user(phone)
    uid = user.id

    for sym, qty, avg, cls in HOLDINGS:
        if not any(h["symbol"] == sym for h in repository.get_portfolio_detailed(uid)):
            repository.add_or_update_holding(uid, sym, qty, avg)
        asset_class, sector = cls or classify_symbol(sym, profile_fn=lambda s: {})
        repository.set_holding_classification(uid, sym, asset_class, sector)
    repository.add_to_watchlist(uid, "NVDA")

    s = get_session()
    try:
        has_tx = s.query(Transaction).filter_by(user_id=uid).count() > 0
    finally:
        s.close()
    if not has_tx:
        today = dt.date.today()
        py, pm = finance_repo.previous_month(today.year, today.month)
        for day, cat, desc, occ, merch, amount in THIS_MONTH:
            d = dt.date(today.year, today.month, min(day, today.day))
            finance_repo.add_transaction(uid, -amount, cat, desc, d, occasion=occ, merchant=merch)
        for day, cat, desc, occ, merch, amount in LAST_MONTH:
            finance_repo.add_transaction(uid, -amount, cat, desc, dt.date(py, pm, min(day, 28)), occasion=occ, merchant=merch or None)
        finance_repo.add_transaction(uid, 500000, "Otros", "Sueldo", dt.date(today.year, today.month, 1))

    personality_repo.set_personality(uid, humor=8, tono="casual")
    news_repo.add_news_topic(uid, "sector", "bancos regionales")
    news_repo.add_economic_indicator(uid, "CPI_US", "US")
    settings_repo.set_notification_settings(uid, watchlist_threshold_pct=5, weekly_summary_enabled=True)
    print(f"Datos de prueba listos para {phone} (user_id={uid}).")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "+56900000000")
