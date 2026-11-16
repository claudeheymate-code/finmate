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

# --- Etapa A de fuentes (16 nov 2026) ---
# FRED (Fed de St. Louis): macro de EE.UU. y calendario de publicaciones.
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
# Banco Central de Chile (API BDE): dólar observado, UF, TPM, IPC.
BCCH_API_TOKEN = os.getenv("BCCH_API_TOKEN", "")
# Marketaux: noticias por empresa con sentimiento. Plan gratis = 100 req/día,
# por eso se consulta como máximo cada MARKETAUX_MIN_INTERVAL_MINUTES.
MARKETAUX_API_KEY = os.getenv("MARKETAUX_API_KEY", "")
MARKETAUX_MIN_INTERVAL_MINUTES = int(os.getenv("MARKETAUX_MIN_INTERVAL_MINUTES", "20"))
# Cada cuántos minutos se buscan noticias de los activos de cada usuario.
NEWS_CHECK_INTERVAL_MINUTES = int(os.getenv("NEWS_CHECK_INTERVAL_MINUTES", "3"))
# Máximo de avisos de noticias por usuario por día (evita saturar WhatsApp).
NEWS_ALERTS_MAX_PER_USER_PER_DAY = int(os.getenv("NEWS_ALERTS_MAX_PER_USER_PER_DAY", "6"))

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

# Umbral de variación diaria (%) para disparar una alerta de watchlist
# por usuario (Fase 1.5, finmate/alerts/watchlist_alerts.py). Separado del
# motor de alertas broadcast de arriba. Default 5% si no se configura.
WATCHLIST_ALERT_THRESHOLD_PCT = float(os.getenv("WATCHLIST_ALERT_THRESHOLD_PCT", "5"))

# ============================================================
# WhatsApp Business Templates (Fase 1.6)
# Content SIDs (HXxxxxx...) de los templates aprobados por Meta, creados en
# Twilio Content Template Builder. Un mensaje que el bot manda por su
# propia iniciativa (no como respuesta directa) necesita un template
# aprobado fuera de la ventana de 24hs de mensajería libre de WhatsApp.
#
# Mientras estas variables no estén configuradas, el bot sigue mandando
# los mensajes como texto libre (así funciona hoy en el sandbox de Twilio,
# que no exige templates) — no se rompe nada existente. En cuanto Joaco
# cree los templates en Twilio y pegue acá sus SIDs, el envío pasa a usar
# el template corto + cola de contenido pendiente (ver
# finmate/alerts/pending.py) automáticamente.
# ============================================================
TWILIO_TEMPLATE_WATCHLIST_ALERT_SID = os.getenv("TWILIO_TEMPLATE_WATCHLIST_ALERT_SID", "")
TWILIO_TEMPLATE_MARKET_NOTIFY_SID = os.getenv("TWILIO_TEMPLATE_MARKET_NOTIFY_SID", "")
TWILIO_TEMPLATE_WEEKLY_SUMMARY_NOTIFY_SID = os.getenv("TWILIO_TEMPLATE_WEEKLY_SUMMARY_NOTIFY_SID", "")

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
ANTHROPIC_MODEL_ANALYSIS = os.getenv("ANTHROPIC_MODEL_ANALYSIS", "claude-sonnet-4-6")

# ============================================================
# Scheduler de apertura/cierre de mercados (Plan Fase 2)
# NYSE abre 9:30 ET = 13:30 UTC. Cierra 16:00 ET = 20:00 UTC.
# Por defecto deshabilitados — activar en Railway cuando estén
# las plantillas de WhatsApp Business aprobadas por Meta.
# ============================================================
MARKET_OPEN_ALERT_ENABLED = os.getenv("MARKET_OPEN_ALERT_ENABLED", "false").lower() == "true"
MARKET_CLOSE_ALERT_ENABLED = os.getenv("MARKET_CLOSE_ALERT_ENABLED", "false").lower() == "true"
MARKET_OPEN_HOUR_UTC = int(os.getenv("MARKET_OPEN_HOUR_UTC", "13"))
MARKET_OPEN_MINUTE_UTC = int(os.getenv("MARKET_OPEN_MINUTE_UTC", "30"))
MARKET_CLOSE_HOUR_UTC = int(os.getenv("MARKET_CLOSE_HOUR_UTC", "20"))
MARKET_CLOSE_MINUTE_UTC = int(os.getenv("MARKET_CLOSE_MINUTE_UTC", "0"))

# ============================================================
# Panel web (etapas 2 y 3)
# FLASK_SECRET_KEY firma la cookie de sesión del panel. En Railway hay que
# cargar un valor largo y aleatorio (ej: `python -c "import secrets;
# print(secrets.token_hex(32))"`). Si falta, se genera uno al arrancar y las
# sesiones se pierden con cada reinicio (sirve para desarrollo, no para prod).
#
# PANEL_DEV_LOGIN habilita un acceso sin código (solo con el número) para
# probar el panel antes de que exista el login por WhatsApp (etapa 4).
# NUNCA activarlo en producción: cualquiera podría entrar con un número ajeno.
# ============================================================
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "")
PANEL_DEV_LOGIN = os.getenv("PANEL_DEV_LOGIN", "false").lower() == "true"
