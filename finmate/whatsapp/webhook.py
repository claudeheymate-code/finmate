"""
Finmate - Webhook de WhatsApp (Meta Cloud API o Twilio)
Recibe mensajes entrantes y responde con información financiera.

La misma ruta /whatsapp/webhook atiende a los dos proveedores:
  - Meta: GET para verificar el webhook (una vez, al configurarlo) y POST
    con JSON. Se responde 200 al tiro y la respuesta del bot se manda
    aparte, en un hilo, porque Meta reintenta si tarda unos segundos y el
    agente puede demorar más (se ignoran los reintentos por id de mensaje).
  - Twilio: POST con formulario; se responde con TwiML, como siempre.

Fase 0: el enrutado por palabra exacta (hola/ayuda/mercados/...) se
reemplazó por el orquestador del agente (finmate.agent.orchestrator), que
usa Claude con tool-calling para decidir qué hacer con cada mensaje. Las
funciones de abajo (_get_market_data, _get_context_news, etc.) se mantienen
tal cual porque las reutiliza finmate.agent.tools como implementación de
las herramientas del agente.
"""

import logging
import os
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone

import httpx
from flask import Blueprint, abort, request
from twilio.twiml.messaging_response import MessagingResponse

from config.settings import FINNHUB_API_KEY, ALPHA_VANTAGE_API_KEY, META_VERIFY_TOKEN
from finmate.whatsapp import meta_cloud

logger = logging.getLogger(__name__)

whatsapp_bp = Blueprint("whatsapp", __name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"
ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"

# ETFs que representan los principales índices
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
    """Obtiene datos de mercado de Finnhub + Alpha Vantage de forma síncrona."""
    try:
        has_data = False
        any_closed = False

        with httpx.Client(timeout=10) as client:
            # --- Índices ---
            index_lines = ["📈 *MERCADOS — ÍNDICES*", ""]
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
            lines.append("🕐 _= Último dato registrado (mercado cerrado)._")

        if not has_data:
            lines.append("")
            lines.append("_No se pudieron obtener datos en este momento._")

        lines.append("")
        lines.append("_Finmate — Información, no recomendación._")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error obteniendo mercados: {e}", exc_info=True)
        return "❌ Error consultando mercados.\n_Intenta más tarde._"


def _get_context_news() -> str:
    """Obtiene las ultimas 5 noticias de mayor impacto desde Finnhub."""
    try:
        # Leer key directamente del env para evitar problemas de import
        fh_key = FINNHUB_API_KEY or os.getenv("FINNHUB_API_KEY", "")
        if not fh_key:
            return "Error: FINNHUB_API_KEY no configurada en Railway."

        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{FINNHUB_BASE}/news",
                params={"category": "general", "token": fh_key},
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


@whatsapp_bp.route("/webhook", methods=["GET"])
def verify_webhook():
    """Meta llama a esta URL una vez al configurar el webhook: si el token
    coincide con META_VERIFY_TOKEN, hay que devolver el `hub.challenge`."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token", "")
    challenge = request.args.get("hub.challenge", "")
    if mode == "subscribe" and META_VERIFY_TOKEN and token == META_VERIFY_TOKEN:
        logger.info("Webhook de Meta verificado.")
        return challenge, 200
    logger.warning("Verificación de webhook de Meta rechazada (token distinto o META_VERIFY_TOKEN vacío).")
    abort(403)


# Ids de mensajes de Meta ya atendidos (Meta reintenta el mismo webhook).
_SEEN: "OrderedDict[str, float]" = OrderedDict()
_SEEN_LOCK = threading.Lock()
_SEEN_MAX = 2000
RUN_IN_BACKGROUND = True  # los tests lo apagan para correr todo en el mismo hilo


def _first_time(msg_id: str) -> bool:
    if not msg_id:
        return True
    with _SEEN_LOCK:
        if msg_id in _SEEN:
            return False
        _SEEN[msg_id] = time.time()
        while len(_SEEN) > _SEEN_MAX:
            _SEEN.popitem(last=False)
        return True


def _answer_meta(msg: dict) -> None:
    from finmate.agent.orchestrator import handle_message
    from finmate.whatsapp.messenger import WhatsAppMessenger

    phone = meta_cloud.to_internal(msg["from"])
    try:
        meta_cloud.mark_as_read(msg["id"])
        if not msg["text"]:
            reply = "Por ahora solo puedo leer mensajes de texto. Escríbeme tu pregunta y te respondo."
        else:
            reply = handle_message(phone, msg["text"])
        ok = WhatsAppMessenger().send_message(phone, reply)
        logger.info(f"Respuesta a {msg['from']} {'enviada' if ok else 'NO enviada'} ({len(reply)} caracteres)")
    except Exception as e:
        logger.error(f"Error respondiendo a {phone} por Meta: {e}", exc_info=True)


def _incoming_meta():
    raw = request.get_data()
    if not meta_cloud.valid_signature(raw, request.headers.get("X-Hub-Signature-256")):
        logger.warning("Webhook de Meta con firma inválida: se ignora.")
        abort(403)
    payload = request.get_json(silent=True) or {}
    for st in meta_cloud.parse_statuses(payload):
        if st["status"] == "failed":
            logger.warning(f"Meta: mensaje a {st['to']} FALLÓ: {'; '.join(st['errors']) or 'sin detalle'}")
        else:
            logger.info(f"Meta: estado {st['status']} para {st['to']}")
    if not payload:
        logger.info("Webhook de Meta sin contenido JSON")
    for msg in meta_cloud.parse_incoming(payload):
        if not _first_time(msg["id"]):
            continue
        logger.info(f"Mensaje recibido (Meta) de {msg['from']}: {msg['text'] or '[' + msg['type'] + ']'}")
        if RUN_IN_BACKGROUND:
            threading.Thread(target=_answer_meta, args=(msg,), daemon=True).start()
        else:
            _answer_meta(msg)
    return "ok", 200  # siempre 200 rápido; los avisos de estado (entregado/leído) también llegan acá


@whatsapp_bp.route("/webhook", methods=["POST"])
def incoming_message():
    """Procesa mensajes entrantes de WhatsApp vía el orquestador del agente."""
    if request.is_json:
        return _incoming_meta()

    # Twilio (formulario + respuesta TwiML).
    # Import diferido: evita el ciclo de imports (agent.tools importa de este
    # mismo módulo para reusar _get_market_data).
    from finmate.agent.orchestrator import handle_message

    incoming_msg = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "")
    resp = MessagingResponse()
    msg = resp.message()

    logger.info(f"Mensaje recibido de {from_number}: {incoming_msg}")

    if not incoming_msg:
        msg.body("No recibí ningún texto. Escríbeme algo y te respondo.")
        return str(resp)

    reply_text = handle_message(from_number, incoming_msg)
    msg.body(reply_text)

    return str(resp)
