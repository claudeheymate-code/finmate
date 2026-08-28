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


# ============================================================
# Base de datos (Fase 0 — memoria persistente del agente)
# Postgres gestionado (ej. Neon: https://neon.tech). Neon entrega la URL como
# postgres://... o postgresql://... — se normaliza al driver psycopg (v3) acá
# para no tener que editar la variable de entorno a mano.
# ============================================================
_raw_database_url = os.getenv("DATABASE_URL", "")
if _raw_database_url.startswith("postgres://"):
    _raw_database_url = _raw_database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif _raw_database_url.startswith("postgresql://"):
    _raw_database_url = _raw_database_url.replace("postgresql://", "postgresql+psycopg://", 1)
DATABASE_URL = _raw_database_url

# ============================================================
# Cache (Fase 0 — Redis gestionado, ej. Upstash: https://upstash.com)
# Opcional: si no está seteado, el agente funciona igual pero sin cache
# (más requests a las APIs financieras).
# ============================================================
REDIS_URL = os.getenv("REDIS_URL", "")

# ============================================================
# Agente (Fase 0 — orquestador con Claude)
# Enrutado económico: Haiku por defecto, Sonnet para análisis más profundo.
# Verificar los IDs vigentes en https://platform.claude.com/docs/en/about-claude/models/overview
# antes de desplegar, por si Anthropic publicó modelos más nuevos.
# ============================================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL_DEFAULT = os.getenv("ANTHROPIC_MODEL_DEFAULT", "claude-haiku-4-5-20251001")
ANTHROPIC_MODEL_ANALYSIS = os.getenv("ANTHROPIC_MODEL_ANALYSIS", "claude-sonnet-5")
