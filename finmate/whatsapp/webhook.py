"""
Finmate - Webhook de WhatsApp (Twilio)
Recibe mensajes entrantes y responde con información financiera.
"""

import asyncio
import logging
import threading

from flask import Blueprint, request
from twilio.twiml.messaging_response import MessagingResponse

from finmate.alerts.engine import AlertEngine

logger = logging.getLogger(__name__)

whatsapp_bp = Blueprint("whatsapp", __name__)

# Comandos disponibles
COMMANDS = {
    "resumen": "Recibe el resumen semanal de mercados",
    "mercados": "Estado actual de los principales índices",
    "ayuda": "Muestra los comandos disponibles",
    "hola": "Saludo y bienvenida",
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

    elif incoming_msg in ("resumen", "semanal", "weekly"):
        msg.body(
            "📊 Preparando tu resumen semanal...\n"
            "_Esto puede tomar unos segundos._"
        )
        # Enviar resumen en background thread para no bloquear la respuesta a Twilio
        engine = AlertEngine()
        thread = threading.Thread(
            target=_run_async_in_thread,
            args=(engine.send_on_demand_summary(from_number),),
            daemon=True,
        )
        thread.start()

    elif incoming_msg in ("mercados", "indices", "bolsa", "markets"):
        msg.body(
            "📈 Consultando mercados...\n"
            "_Recibirás la información en unos segundos._"
        )
        # Enviar datos de mercado en background thread para no bloquear la respuesta a Twilio
        engine = AlertEngine()
        thread = threading.Thread(
            target=_run_async_in_thread,
            args=(_send_market_snapshot(engine, from_number),),
            daemon=True,
        )
        thread.start()

    else:
        msg.body(
            f"No reconozco el comando *{incoming_msg}*.\n"
            "Escribe *ayuda* para ver los comandos disponibles."
        )

    return str(resp)


def _run_async_in_thread(coro):
    """Ejecuta una coroutine en un nuevo event loop dentro de un thread."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"Error en background thread: {e}")
    finally:
        loop.close()


async def _send_market_snapshot(engine: AlertEngine, to: str):
    """Envía un snapshot rápido del mercado."""
    try:
        indices = await engine.aggregator.fmp.get_major_indices()
        movers = await engine.aggregator.fmp.get_market_movers()

        from finmate.whatsapp.formatter import _change_emoji, _format_number, INDEX_NAMES

        lines = ["📈 *MERCADOS — AHORA*", ""]
        for idx in indices:
            name = INDEX_NAMES.get(idx.get("symbol", ""), idx.get("name", ""))
            emoji = _change_emoji(idx.get("change_pct"))
            price = _format_number(idx.get("price"))
            change = _format_number(idx.get("change_pct"), suffix="%")
            lines.append(f"{emoji} *{name}*: {price} ({change})")

        lines.append("")
        gainers = movers.get("gainers", [])[:3]
        losers = movers.get("losers", [])[:3]
        if gainers:
            lines.append("🟢 _Top Ganadores:_")
            for g in gainers:
                lines.append(f"  {g['symbol']} ({_format_number(g.get('change_pct'), suffix='%')})")
        if losers:
            lines.append("🔴 _Top Perdedores:_")
            for l in losers:
                lines.append(f"  {l['symbol']} ({_format_number(l.get('change_pct'), suffix='%')})")

        lines.append("")
        lines.append("_Finmate — Información, no recomendación._")

        engine.messenger.send_message(to, "\n".join(lines))
    except Exception as e:
        logger.error(f"Error en market snapshot: {e}")
        engine.messenger.send_message(to, "❌ Error consultando mercados. Intenta más tarde.")
