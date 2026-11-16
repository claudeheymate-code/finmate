"""
Finmate - WSGI entry point para Gunicorn.
Inicia el scheduler antes de servir la app.
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from main import app, start_scheduler

# Iniciar scheduler al cargar el módulo (gunicorn --preload)
scheduler = start_scheduler()

# Etapa B: precios en tiempo real (WebSocket de Finnhub) para alertas de
# watchlist en segundos. Si algo falla acá, el resto del bot sigue igual.
try:
    from finmate.realtime.price_stream import start_price_stream

    start_price_stream()
except Exception as _e:  # noqa: BLE001
    logging.getLogger(__name__).error(f"No se pudo iniciar el flujo de precios: {_e}")

# Gunicorn usa esta variable
application = app
