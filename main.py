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
# Flask App
# ============================================================
app = Flask(__name__)
app.register_blueprint(whatsapp_bp, url_prefix="/whatsapp")


@app.route("/")
def index():
    return {
        "app": "Finmate",
        "version": "1.0.0",
        "status": "running",
        "description": "Bot financiero informativo para WhatsApp",
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

    scheduler.start()
    logger.info(
        f"Scheduler iniciado: alertas cada {ALERT_CHECK_INTERVAL_MINUTES}min, "
        f"resumen semanal los {WEEKLY_SUMMARY_DAY} a las {WEEKLY_SUMMARY_HOUR}:{WEEKLY_SUMMARY_MINUTE:02d}"
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
