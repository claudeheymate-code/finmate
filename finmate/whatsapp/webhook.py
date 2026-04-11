"""
Finmate - Webhook de WhatsApp (Twilio)
Recibe mensajes entrantes y responde con información financiera.
"""

import logging

import httpx
from flask import Blueprint, request
from twilio.twiml.messaging_response import MessagingResponse

from config.settings import FINNHUB_API_KEY

logger = logging.getLogger(__name__)

whatsapp_bp = Blueprint("whatsapp", __name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"

# Comandos disponibles
COMMANDS = {
    "resumen": "Recibe el resumen semanal de mercados",
    "mercados": "Estado actual de los principales índices",
    "ayuda": "Muestra los comandos disponibles",
    "hola": "Saludo y bienvenida",
}

# ETFs que representan los principales índices
MARKET_SYMBOLS = {
    "SPY": "S&P 500",
    "DIA": "Dow Jones",
    "QQQ": "Nasdaq 100",
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
        return f"{prefix}{num:,.2f}{suffix}"
    except (ValueError, TypeError):
        return str(value)


def _get_market_data() -> str:
    """Obtiene datos de mercado de Finnhub de forma síncrona."""
    try:
        lines = ["📈 *MERCADOS — AHORA*", ""]
        has_data = False

        with httpx.Client(timeout=10) as client:
            for symbol, name in MARKET_SYMBOLS.items():
                try:
                    resp = client.get(
                        f"{FINNHUB_BASE}/quote",
                        params={"symbol": symbol, "token": FINNHUB_API_KEY},
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    price = data.get("c")  # current price
                    change_pct = data.get("dp")  # percent change

                    if price and price > 0:
                        emoji = _change_emoji(change_pct)
                        lines.append(
                            f"{emoji} *{name}* ({symbol}): "
                            f"{_format_number(price, prefix='$')} "
                            f"({_format_number(change_pct, suffix='%')})"
                        )
                        has_data = True
                    else:
                        lines.append(f"⚪ *{name}*: _Sin datos_")

                except Exception as e:
                    logger.error(f"Error obteniendo {symbol}: {e}")
                    lines.append(f"⚪ *{name}*: _Error_")

        if not has_data:
            lines.append("")
            lines.append("_El mercado puede estar cerrado en este momento._")

        lines.append("")
        lines.append("_Finmate — Información, no recomendación._")
        return "\n".join(lines)

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
        market_text = _get_market_data()
        msg.body(market_text)

    elif incoming_msg in ("resumen", "semanal", "weekly"):
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
