"""
Finmate - Configuración Central
Todas las variables de entorno y configuraciones del bot.
"""

import os
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# TWILIO (WhatsApp)
# ============================================================
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")  # Sandbox default

# Lista de números a los que se envían alertas (formato: whatsapp:+56912345678)
WHATSAPP_RECIPIENTS = [
    r.strip() for r in os.getenv("WHATSAPP_RECIPIENTS", "").split(",") if r.strip()
]

# ============================================================
# APIs Financieras (gratuitas)
# ============================================================
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
FMP_API_KEY = os.getenv("FMP_API_KEY", "")  # Financial Modeling Prep
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")

# ============================================================
# Google Calendar
# ============================================================
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

# ============================================================
# Scheduler
# ============================================================
# Día y hora del resumen semanal (default: domingo 20:00 hora de Chile)
WEEKLY_SUMMARY_DAY = os.getenv("WEEKLY_SUMMARY_DAY", "sun")
WEEKLY_SUMMARY_HOUR = int(os.getenv("WEEKLY_SUMMARY_HOUR", "20"))
WEEKLY_SUMMARY_MINUTE = int(os.getenv("WEEKLY_SUMMARY_MINUTE", "0"))

# Intervalo en minutos para chequear alertas en tiempo real
ALERT_CHECK_INTERVAL_MINUTES = int(os.getenv("ALERT_CHECK_INTERVAL_MINUTES", "30"))

# ============================================================
# Zona horaria
# ============================================================
TIMEZONE = os.getenv("TIMEZONE", "America/Santiago")

# ============================================================
# Flask (webhook de Twilio)
# ============================================================
FLASK_PORT = int(os.getenv("PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

# ============================================================
# Logging
# ============================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
