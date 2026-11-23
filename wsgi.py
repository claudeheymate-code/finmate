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

# Cargar de entrada (en el hilo principal) lo que usan las respuestas de
# WhatsApp y los procesos de fondo. Si se importan por primera vez desde
# varios hilos a la vez, los imports pueden trabarse entre sí.
import finmate.agent.orchestrator  # noqa: E402,F401
import finmate.whatsapp.messenger  # noqa: E402,F401
import finmate.alerts.watchlist_alerts  # noqa: E402,F401
import finmate.alerts.news_alerts  # noqa: E402,F401
import finmate.services.quotes  # noqa: E402,F401

# Iniciar scheduler al cargar el módulo. Sin --preload: corre dentro del
# único worker, así la base y los clientes HTTP no se heredan de un fork.
scheduler = start_scheduler()

# Etapa B: precios en tiempo real (WebSocket de Finnhub) para alertas de
# watchlist en segundos. Si algo falla acá, el resto del bot sigue igual.
try:
    from finmate.realtime.price_stream import start_price_stream

    start_price_stream()
except Exception as _e:  # noqa: BLE001
    logging.getLogger(__name__).error(f"No se pudo iniciar el flujo de precios: {_e}")

# WhatsApp por Meta: revisar token y suscripción al arrancar, en segundo plano
# (si Meta tarda o falla, el bot arranca igual).
try:
    import threading

    from finmate.whatsapp.meta_cloud import startup_check

    threading.Thread(target=startup_check, daemon=True).start()
except Exception as _e:  # noqa: BLE001
    logging.getLogger(__name__).error(f"No se pudo revisar la conexión con Meta: {_e}")

# Gunicorn usa esta variable
application = app
