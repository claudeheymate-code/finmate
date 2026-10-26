"""
Finmate - Alertas de watchlist por usuario (Fase 1.5)

Chequea los símbolos que cada usuario sigue en su watchlist (Fase 1) y le
manda una alerta de WhatsApp directa (1-a-1, no broadcast) cuando el precio
se movió más del umbral configurado en el día. Reutiliza la misma cotización
de Finnhub que ya usa `portfolio_tools.py`, para no duplicar el manejo de
"mercado cerrado" ni el formato de números.

Separado a propósito del motor de alertas broadcast (`alerts/engine.py`):
así un error acá (o que todavía no haya DATABASE_URL configurada) nunca
puede afectar earnings/macro/noticias, que ya funcionan en producción. Ver
la nota en CLAUDE.md sobre por qué esto quedó pendiente en la pasada de
Fase 1.

Fase 1.6: si hay un Content Template aprobado configurado
(TWILIO_TEMPLATE_WATCHLIST_ALERT_SID), la alerta se manda como template
(symbol, variación % y precio como variables — es corta y estructurada,
entra bien en un template). Si no está configurado, se cae al mensaje de
texto libre de siempre (sirve para sandbox/desarrollo). Ver
finmate/alerts/pending.py para el porqué de esta distinción.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

from config.settings import TWILIO_TEMPLATE_WATCHLIST_ALERT_SID, WATCHLIST_ALERT_THRESHOLD_PCT
from finmate.db.repository import get_all_watchlist_entries
from finmate.whatsapp.messenger import WhatsAppMessenger
from finmate.whatsapp.webhook import _change_emoji, _format_number, _get_finnhub_quote

logger = logging.getLogger(__name__)

# Separado del STATE_FILE del motor broadcast (alert_state.json) a propósito:
# son dos sistemas independientes y no deberían compartir estado.
STATE_FILE = "watchlist_alert_state.json"

# Si un mismo state file crece sin límite (muchos usuarios x muchos símbolos
# x muchos días), se poda a esta cantidad de entradas más recientes.
MAX_STATE_ENTRIES = 2000


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    try:
        if len(state) > MAX_STATE_ENTRIES:
            # Poda defensiva: conserva solo las últimas MAX_STATE_ENTRIES
            # (el orden de inserción de dict en Python 3.7+ está garantizado).
            for key in list(state.keys())[: len(state) - MAX_STATE_ENTRIES]:
                del state[key]
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Error guardando estado de alertas de watchlist: {e}")


def check_watchlist_alerts(messenger: Optional[WhatsAppMessenger] = None) -> int:
    """
    Chequea la watchlist de todos los usuarios y manda una alerta directa
    cuando un símbolo se movió más del umbral configurado (ver
    WATCHLIST_ALERT_THRESHOLD_PCT en config/settings.py, default 5%).

    Como máximo una alerta por usuario+símbolo+día (se resetea solo al día
    siguiente vía la fecha en la clave de estado). Si el mercado está
    cerrado para un símbolo, se lo salta (igual que el resto del bot).

    Devuelve la cantidad de alertas enviadas. Pensado para correr en el
    mismo intervalo que `AlertEngine.check_and_send_alerts` (ver main.py),
    pero como job separado — ver el docstring del módulo.
    """
    messenger = messenger or WhatsAppMessenger()
    entries = get_all_watchlist_entries()
    if not entries:
        return 0

    state = _load_state()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    alerts_sent = 0

    # Cache de cotizaciones dentro de esta corrida: si varios usuarios siguen
    # el mismo símbolo, se consulta a Finnhub una sola vez por símbolo.
    quote_cache: dict = {}

    with httpx.Client(timeout=10) as client:
        for user_id, phone, symbol in entries:
            if symbol not in quote_cache:
                quote_cache[symbol] = _get_finnhub_quote(client, symbol)
            quote = quote_cache[symbol]

            if not quote or not quote.get("price") or quote.get("is_closed"):
                continue

            try:
                change_pct = float(quote.get("change_pct"))
            except (TypeError, ValueError):
                continue

            if abs(change_pct) < WATCHLIST_ALERT_THRESHOLD_PCT:
                continue

            state_key = f"{user_id}_{symbol}_{today}"
            if state.get(state_key):
                continue

            change_fmt = _format_number(change_pct, suffix="%")
            price_fmt = _format_number(quote["price"], prefix="$")

            try:
                if TWILIO_TEMPLATE_WATCHLIST_ALERT_SID:
                    ok = messenger.send_template(
                        phone,
                        TWILIO_TEMPLATE_WATCHLIST_ALERT_SID,
                        {"1": symbol, "2": change_fmt, "3": price_fmt},
                    )
                else:
                    emoji = _change_emoji(change_pct)
                    msg = (
                        f"{emoji} *{symbol}* se movió {change_fmt} hoy\n"
                        f"Precio actual: {price_fmt}\n\n"
                        f"_Lo tenés en tu watchlist. Escribime si querés más detalle o sacarlo de la lista._"
                    )
                    ok = messenger.send_message(phone, msg)
            except Exception as e:
                logger.error(f"Error enviando alerta de watchlist a {phone} ({symbol}): {e}")
                ok = False

            if ok:
                state[state_key] = True
                alerts_sent += 1
                logger.info(f"Alerta de watchlist enviada a {phone}: {symbol} {change_pct:+.2f}%")

    _save_state(state)
    logger.info(f"Chequeo de alertas de watchlist completado: {alerts_sent} alertas enviadas")
    return alerts_sent
