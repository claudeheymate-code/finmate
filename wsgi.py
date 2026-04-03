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

# Gunicorn usa esta variable
application = app
