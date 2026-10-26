"""
Finmate - Aplicación Principal
Bot financiero informativo para WhatsApp.

Ejecuta:
  1. Servidor Flask (webhook de WhatsApp)
  2. Scheduler de alertas periódicas
  3. Scheduler de resumen semanal
"""

import asyncio
import logging
import sys
import threading
from datetime import datetime

from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz

from config.settings import (
    FLASK_PORT,
    FLASK_DEBUG,
    LOG_LEVEL,
    TIMEZONE,
    WEEKLY_SUMMARY_DAY,
    WEEKLY_SUMMARY_HOUR,
    WEEKLY_SUMMARY_MINUTE,
    ALERT_CHECK_INTERVAL_MINUTES,
)
from finmate.whatsapp.webhook import whatsapp_bp
from finmate.alerts.engine import AlertEngine
from finmate.db.models import init_db

# ============================================================
# Logging
# ============================================================
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("finmate")

# ============================================================
# Base de datos (Fase 0 — memoria persistente del agente)
# Se corre acá, a nivel de módulo, para que también se ejecute cuando
# gunicorn importa wsgi.py (no solo con `python main.py`). Si todavía no
# se configuró DATABASE_URL, se loguea el error pero no se cae la app —
# el webhook sigue respondiendo (avisando que falta memoria) y /health
# sigue funcionando para que Railway no marque el deploy como caído.
# ============================================================
try:
    init_db()
    logger.info("Base de datos inicializada (tablas creadas si no existían).")
except Exception as e:
    logger.error(f"No se pudo inicializar la base de datos — ¿falta DATABASE_URL? Detalle: {e}")


# ============================================================
# Flask App
# ============================================================
app = Flask(__name__)
app.register_blueprint(whatsapp_bp, url_prefix="/whatsapp")


@app.route("/")
def index():
    return {
        "app": "Finmate",
        "version": "2.0.0-fase0",
        "status": "running",
        "description": "Agente financiero personal para WhatsApp",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.route("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# ============================================================
# Scheduler Jobs
# ============================================================
def run_alert_check():
    """Job: chequea y envía alertas en tiempo real."""
    logger.info("⏰ Ejecutando chequeo de alertas programado...")
    engine = AlertEngine()
    asyncio.run(engine.check_and_send_alerts())


def run_weekly_summary():
    """Job: genera y envía el resumen semanal."""
    logger.info("📊 Ejecutando resumen semanal programado...")
    engine = AlertEngine()
    asyncio.run(engine.send_weekly_summary())


def run_watchlist_alert_check():
    """Job: chequea alertas de watchlist por usuario (Fase 1.5).

    Deliberadamente separado de `run_alert_check` y envuelto en su propio
    try/except: necesita DATABASE_URL (consulta la watchlist por usuario) y
    si falla por lo que sea, no debe tocar el chequeo de alertas broadcast
    (earnings/macro/noticias) que ya funciona en producción. El import de
    `check_watchlist_alerts` se hace acá adentro, no arriba del archivo, por
    la misma razón: que un problema en ese módulo no le impida ni siquiera
    arrancar al resto del bot.
    """
    logger.info("⏰ Ejecutando chequeo de alertas de watchlist...")
    try:
        from finmate.alerts.watchlist_alerts import check_watchlist_alerts

        check_watchlist_alerts()
    except Exception as e:
        logger.error(f"Error en chequeo de alertas de watchlist (no afecta el resto del bot): {e}")


def start_scheduler():
    """Inicializa y arranca el scheduler."""
    tz = pytz.timezone(TIMEZONE)
    scheduler = BackgroundScheduler(timezone=tz)

    # Chequeo de alertas cada X minutos (solo en horario de mercado: 7am - 11pm)
    scheduler.add_job(
        run_alert_check,
        IntervalTrigger(minutes=ALERT_CHECK_INTERVAL_MINUTES),
        id="alert_check",
        name="Chequeo de alertas",
        replace_existing=True,
    )

    # Resumen semanal
    day_map = {
        "mon": "mon", "tue": "tue", "wed": "wed", "thu": "thu",
        "fri": "fri", "sat": "sat", "sun": "sun",
    }
    day = day_map.get(WEEKLY_SUMMARY_DAY.lower(), "sun")

    scheduler.add_job(
        run_weekly_summary,
        CronTrigger(
            day_of_week=day,
            hour=WEEKLY_SUMMARY_HOUR,
            minute=WEEKLY_SUMMARY_MINUTE,
        ),
        id="weekly_summary",
        name="Resumen semanal",
        replace_existing=True,
    )

    # Alertas de watchlist por usuario (Fase 1.5) — mismo intervalo que el
    # chequeo de alertas broadcast de arriba, pero como job separado para
    # que un error acá nunca afecte earnings/macro/noticias.
    scheduler.add_job(
        run_watchlist_alert_check,
        IntervalTrigger(minutes=ALERT_CHECK_INTERVAL_MINUTES),
        id="watchlist_alert_check",
        name="Chequeo de alertas de watchlist",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        f"Scheduler iniciado: alertas cada {ALERT_CHECK_INTERVAL_MINUTES}min, "
        f"resumen semanal los {WEEKLY_SUMMARY_DAY} a las {WEEKLY_SUMMARY_HOUR}:{WEEKLY_SUMMARY_MINUTE:02d}, "
        f"alertas de watchlist cada {ALERT_CHECK_INTERVAL_MINUTES}min"
    )
    return scheduler


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    logger.info("🚀 Iniciando Finmate...")
    logger.info(f"   Timezone: {TIMEZONE}")
    logger.info(f"   Puerto: {FLASK_PORT}")
    logger.info(f"   Alertas cada: {ALERT_CHECK_INTERVAL_MINUTES} min")
    logger.info(f"   Resumen semanal: {WEEKLY_SUMMARY_DAY} {WEEKLY_SUMMARY_HOUR}:{WEEKLY_SUMMARY_MINUTE:02d}")

    # Iniciar scheduler en background
    scheduler = start_scheduler()

    # Ejecutar un chequeo inicial
    logger.info("Ejecutando chequeo inicial de alertas...")
    try:
        run_alert_check()
    except Exception as e:
        logger.warning(f"Chequeo inicial falló (es normal si faltan API keys): {e}")

    # Iniciar Flask
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=FLASK_DEBUG)
