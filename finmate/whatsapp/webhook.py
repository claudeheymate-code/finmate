"""
Finmate - Webhook de WhatsApp (Twilio)
Recibe mensajes entrantes y responde con información financiera.
"""

import logging

import httpx
from flask import Blueprint, request
from twilio.twiml.messaging_response import MessagingResponse

from config.settings import FMP_API_KEY

logger = logging.getLogger(__name__)

whatsapp_bp = Blueprint("whatsapp", __name__)

FMP_BASE = "https://financialmodelingprep.com/api/v3"

# Comandos disponibles
COMMANDS = {
    "resumen": "Recibe el resumen semanal de mercados",
    "mercados": "Estado actual de los principales índices",
    "ayuda": "Muestra los comandos disponibles",
    "hola": "Saludo y bienvenida",
}

INDEX_NAMES = {
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones",
    "^IXIC": "Nasdaq",
}


def _get_help_message() -> str:
    lines = [
        "📊 *FINMATE — Comandos disponibles*",
        "",
    ]
    for cmd, desc in COMMANDS.items():
        lines.append(f"• *{cmd}* — {desc}")
    lines.append("")
    lines.append("_Envía cualquier comando para recibir información._")
    lines.append("_Finmate no emite recomendaciones de inversión._")
    return "\n".join(lines)


def _change_emoji(change_pct) -> str:
    try:
        pct = float(change_pct)
        if pct > 1:
            return "🟢📈"
        elif pct > 0:
            return "🟢"
        elif pct < -1:
            return "🔴📉"
        elif pct < 0:
            return "🔴"
        return "⚪"
    except (ValueError, TypeError):
        return ""


def _format_number(value, prefix: str = "", suffix: str = "") -> str:
    if value is None:
        return "N/D"
    try:
        num = float(value)
        if abs(num) >= 1_000_000_000:
            return f"{prefix}{num / 1_000_000_000:.1f}B{suffix}"
        if abs(num) >= 1_000_000:
            return f"{prefix}{num / 1_000_000:.1f}M{suffix}"
        return f"{prefix}{num:,.2f}{suffix}"
    except (ValueError, TypeError):
        return str(value)


def _get_market_data() -> str:
    """Obtiene datos de mercado de FMP de forma síncrona."""
    try:
        symbols = "^GSPC,^DJI,^IXIC"
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{FMP_BASE}/quote/{symbols}",
                params={"apikey": FMP_API_KEY},
            )
            resp.raise_for_status()
            data = resp.json()

        if not data or not isinstance(data, list):
            return "📈 *MERCADOS*\n\n_No se pudieron obtener datos en este momento._\n\n_Finmate — Información, no recomendación._"

        lines = ["📈 *MERCADOS — AHORA*", ""]
        for idx in data:
            name = INDEX_NAMES.get(idx.get("symbol", ""), idx.get("name", ""))
            emoji = _change_emoji(idx.get("changesPercentage"))
            price = _format_number(idx.get("price"))
            change = _format_number(idx.get("changesPercentage"), suffix="%")
            lines.append(f"{emoji} *{name}*: {price} ({change})")

        lines.append("")
        lines.append("_Finmate — Información, no recomendación._")
        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        logger.error(f"FMP HTTP error: {e.response.status_code}")
        return f"❌ Error consultando mercados (HTTP {e.response.status_code}).\n_Intenta más tarde._"
    except httpx.TimeoutException:
        logger.error("FMP timeout")
        return "❌ El servicio de datos tardó demasiado.\n_Intenta en unos minutos._"
    except Exception as e:
        logger.error(f"Error obteniendo mercados: {e}", exc_info=True)
        return f"❌ Error consultando mercados.\n_Intenta más tarde._"


@whatsapp_bp.route("/webhook", methods=["POST"])
def incoming_message():
    """Procesa mensajes entrantes de WhatsApp."""
    incoming_msg = request.values.get("Body", "").strip().lower()
    from_number = request.values.get("From", "")
    resp = MessagingResponse()
    msg = resp.message()

    logger.info(f"Mensaje recibido de {from_number}: {incoming_msg}")

    if incoming_msg in ("hola", "hi", "hello", "inicio"):
        msg.body(
            "👋 *¡Hola! Soy Finmate*, tu asistente de mercados financieros.\n\n"
            "Te envío alertas y resúmenes semanales sobre lo que mueve los mercados.\n\n"
            "Escribe *ayuda* para ver los comandos disponibles.\n\n"
            "_Finmate informa, no recomienda inversiones._"
        )

    elif incoming_msg in ("ayuda", "help", "?", "comandos"):
        msg.body(_get_help_message())

    elif incoming_msg in ("mercados", "indices", "bolsa", "markets"):
        # Obtener datos de mercado directamente (síncrono, ~2-5 seg)
        market_text = _get_market_data()
        msg.body(market_text)

    elif incoming_msg in ("resumen", "semanal", "weekly"):
        # El resumen es más pesado, responder con mensaje de espera
        msg.body(
            "📊 *Resumen semanal*\n\n"
            "_Usa el comando *mercados* para ver los índices en tiempo real._\n\n"
            "_El resumen completo se envía automáticamente los domingos a las 20:00._\n\n"
            "_Finmate — Información, no recomendación._"
        )

    else:
        msg.body(
            f"No reconozco el comando *{incoming_msg}*.\n"
            "Escribe *ayuda* para ver los comandos disponibles."
        )

    return str(resp)
