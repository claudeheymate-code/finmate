"""
Finmate - Webhook de WhatsApp (Twilio)
Recibe mensajes entrantes y responde con información financiera.
"""

import logging
from datetime import datetime, timezone

import httpx
from flask import Blueprint, request
from twilio.twiml.messaging_response import MessagingResponse

from config.settings import FINNHUB_API_KEY, ALPHA_VANTAGE_API_KEY

logger = logging.getLogger(__name__)

whatsapp_bp = Blueprint("whatsapp", __name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"
ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"

# Comandos disponibles
COMMANDS = {
    "Resumen": "Recibe el resumen semanal de mercados",
    "Mercados": "Estado actual de los principales indices, divisas y commodities",
    "Contexto": "Ultimas 5 noticias de mayor impacto en los mercados",
    "Ayuda": "Muestra los comandos disponibles",
    "Hola": "Saludo y bienvenida",
}

# ETFs que representan los principales indices
MARKET_SYMBOLS = {
    "SPY": "S&P 500",
    "DIA": "Dow Jones",
    "QQQ": "Nasdaq 100",
}

# Commodities via ETFs
COMMODITY_SYMBOLS = {
    "GLD": "Oro (Gold)",
    "SLV": "Plata (Silver)",
}


def _get_help_message() -> str:
    lines = [
        "📊 *FINMATE - COMANDOS DISPONIBLES*",
        "",
    ]
    for cmd, desc in COMMANDS.items():
        lines.append(f"- *{cmd}* - {desc}")
    lines.append("")
    lines.append("_Envia cualquier comando para recibir informacion._")
    lines.append("_Finmate no emite recomendaciones de inversion._")
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


def _get_finnhub_quote(client, symbol: str) -> dict:
    """Obtiene quote de Finnhub. Retorna dict con price, change_pct, is_closed."""
    try:
        resp = client.get(
            f"{FINNHUB_BASE}/quote",
            params={"symbol": symbol, "token": FINNHUB_API_KEY},
        )
        resp.raise_for_status()
        data = resp.json()

        price = data.get("c")  # current price
        change_pct = data.get("dp")  # percent change
        prev_close = data.get("pc")  # previous close
        timestamp = data.get("t", 0)  # unix timestamp

        # Detectar mercado cerrado: si open=0 o change=0 y price=prev_close
        open_price = data.get("o", 0)
        is_closed = (open_price == 0 or price == prev_close) and change_pct == 0

        # Si price es 0 pero prev_close existe, usar prev_close
        if (not price or price == 0) and prev_close and prev_close > 0:
            price = prev_close
            is_closed = True

        return {
            "price": price,
            "change_pct": change_pct,
            "is_closed": is_closed,
            "timestamp": timestamp,
        }
    except Exception as e:
        logger.error(f"Error Finnhub quote {symbol}: {e}")
        return None


def _get_usd_clp(client) -> dict:
    """Obtiene tipo de cambio USD/CLP desde Alpha Vantage."""
    try:
        resp = client.get(
            ALPHA_VANTAGE_BASE,
            params={
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": "USD",
                "to_currency": "CLP",
                "apikey": ALPHA_VANTAGE_API_KEY,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        rate_data = data.get("Realtime Currency Exchange Rate", {})
        rate = rate_data.get("5. Exchange Rate")
        if rate:
            return {"price": float(rate)}
    except Exception as e:
        logger.error(f"Error obteniendo USD/CLP: {e}")
    return None


def _get_market_data() -> str:
    """Obtiene datos de mercado de Finnhub + Alpha Vantage de forma sincrona."""
    try:
        has_data = False
        any_closed = False

        with httpx.Client(timeout=10) as client:
            # --- Indices ---
            index_lines = ["📈 *MERCADOS - INDICES*", ""]
            for symbol, name in MARKET_SYMBOLS.items():
                quote = _get_finnhub_quote(client, symbol)
                if quote and quote["price"] and quote["price"] > 0:
                    emoji = _change_emoji(quote["change_pct"])
                    closed_tag = " 🕐" if quote["is_closed"] else ""
                    index_lines.append(
                        f"{emoji} *{name}* ({symbol}): "
                        f"{_format_number(quote['price'], prefix='$')} "
                        f"({_format_number(quote['change_pct'], suffix='%')}){closed_tag}"
                    )
                    has_data = True
                    if quote["is_closed"]:
                        any_closed = True
                else:
                    index_lines.append(f"⚪ *{name}*: _Sin datos_")

            # --- Commodities (Oro, Plata) ---
            commodity_lines = ["", "💰 *COMMODITIES*", ""]
            for symbol, name in COMMODITY_SYMBOLS.items():
                quote = _get_finnhub_quote(client, symbol)
                if quote and quote["price"] and quote["price"] > 0:
                    emoji = _change_emoji(quote["change_pct"])
                    closed_tag = " 🕐" if quote["is_closed"] else ""
                    commodity_lines.append(
                        f"{emoji} *{name}* ({symbol}): "
                        f"{_format_number(quote['price'], prefix='$')} "
                        f"({_format_number(quote['change_pct'], suffix='%')}){closed_tag}"
                    )
                    has_data = True
                    if quote["is_closed"]:
                        any_closed = True
                else:
                    commodity_lines.append(f"⚪ *{name}*: _Sin datos_")

            # --- Tipo de cambio USD/CLP ---
            fx_lines = ["", "💱 *TIPO DE CAMBIO*", ""]
            usd_clp = _get_usd_clp(client)
            if usd_clp and usd_clp["price"]:
                fx_lines.append(
                    f"🇺🇸🇨🇱 *USD/CLP*: {_format_number(usd_clp['price'], prefix='$')}"
                )
                has_data = True
            else:
                fx_lines.append("⚪ *USD/CLP*: _Sin datos_")

        # Armar mensaje final
        lines = index_lines + commodity_lines + fx_lines

        if any_closed:
            lines.append("")
            lines.append("🕐 _= Ultimo dato registrado (mercado cerrado)._")

        if not has_data:
            lines.append("")
            lines.append("_No se pudieron obtener datos en este momento._")

        lines.append("")
        lines.append("_Finmate - Informacion, no recomendacion._")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error obteniendo mercados: {e}", exc_info=True)
        return "❌ Error consultando mercados.\n_Intenta mas tarde._"


def _get_context_news() -> str:
    """Obtiene las ultimas 5 noticias de mayor impacto desde Finnhub."""
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{FINNHUB_BASE}/news",
                params={"category": "general", "token": FINNHUB_API_KEY},
            )
            resp.raise_for_status()
            data = resp.json()

        # Finnhub puede retornar dict con error en vez de lista
        if isinstance(data, dict):
            err = data.get("error", str(data))
            logger.error(f"Finnhub news error: {err}")
            return f"Error al obtener noticias: {err}"

        if not data:
            return "No hay noticias disponibles en este momento."

        top_news = data[:5]
        lines = ["*CONTEXTO - ULTIMAS NOTICIAS*", ""]

        for i, article in enumerate(top_news, 1):
            headline = article.get("headline", "Sin titulo")
            # Truncar headline largo
            if len(headline) > 90:
                headline = headline[:87] + "..."
            url = article.get("url", "")
            source = article.get("source", "")

            lines.append(f"*{i}.* {headline}")
            if source:
                lines.append(f"   _{source}_")
            if url:
                lines.append(f"   {url}")
            lines.append("")

        lines.append("_Finmate - Informacion, no recomendacion._")
        result = "\n".join(lines)

        # Limite WhatsApp ~1600 chars
        if len(result) > 1550:
            result = result[:1530] + "\n_[mensaje truncado]_"

        return result

    except Exception as e:
        logger.error(f"Error obteniendo noticias: {e}", exc_info=True)
        return f"Error consultando noticias: {type(e).__name__} - {str(e)[:100]}"


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
            "👋 *HOLA! SOY FINMATE*, Tu Asistente de Mercados Financieros.\n\n"
            "Te envio alertas y resumenes semanales sobre lo que mueve los mercados.\n\n"
            "Escribe *Ayuda* para ver los comandos disponibles.\n\n"
            "_Finmate informa, no recomienda inversiones._"
        )

    elif incoming_msg in ("ayuda", "help", "?", "comandos"):
        msg.body(_get_help_message())

    elif incoming_msg in ("mercados", "indices", "bolsa", "markets"):
        market_text = _get_market_data()
        msg.body(market_text)

    elif incoming_msg in ("resumen", "semanal", "weekly"):
        msg.body(
            "📊 *RESUMEN SEMANAL*\n\n"
            "_Usa el comando *Mercados* para ver los indices en tiempo real._\n\n"
            "_El resumen completo se envia automaticamente los domingos a las 20:00._\n\n"
            "_Finmate - Informacion, no recomendacion._"
        )

    elif incoming_msg in ("contexto", "noticias", "news", "context"):
        context_text = _get_context_news()
        msg.body(context_text)

    else:
        msg.body(
            f"No reconozco el comando *{incoming_msg}*.\n"
            "Escribe *Ayuda* para ver los comandos disponibles."
        )

    return str(resp)
