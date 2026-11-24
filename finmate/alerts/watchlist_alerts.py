"""
Finmate - Alertas de watchlist por usuario (Fase 1.5)

Chequea los símbolos que cada usuario sigue en su watchlist (Fase 1) y le
manda una alerta de WhatsApp directa (1-a-1, no broadcast) cuando el precio
se movió más del umbral configurado en el día. Reutiliza la misma cotización
de Finnhub que ya usa `portfolio_tools.py`, para no duplicar el manejo de
"mercado cerrado" ni el formato de números.

Separado a propósito del motor de alertas broadcast (`alerts/engine.py`):
así un error aquí (o que todavía no haya DATABASE_URL configurada) nunca
puede afectar earnings/macro/noticias, que ya funcionan en producción. Ver
la nota en CLAUDE.md sobre por qué esto quedó pendiente en la pasada de
Fase 1.

Fase 1.6: si hay un Content Template aprobado configurado
(TEMPLATE_WATCHLIST_ALERT), la alerta se manda como template
(symbol, variación % y precio como variables — es corta y estructurada,
entra bien en un template). Si no está configurado, se cae al mensaje de
texto libre de siempre (sirve para sandbox/desarrollo). Ver
finmate/alerts/pending.py para el porqué de esta distinción.
"""
import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx

from config.settings import TEMPLATE_WATCHLIST_ALERT, WATCHLIST_ALERT_THRESHOLD_PCT
from finmate.db.repository import get_all_watchlist_entries
from finmate.db.state_store import load_json, save_json
from finmate.whatsapp.messenger import WhatsAppMessenger
from finmate.whatsapp.webhook import _change_emoji, _format_number, _get_finnhub_quote

logger = logging.getLogger(__name__)

# Separado del STATE_FILE del motor broadcast (alert_state.json) a propósito:
# son dos sistemas independientes y no deberían compartir estado.
STATE_FILE = "watchlist_alert_state.json"

# Si un mismo state file crece sin límite (muchos usuarios x muchos símbolos
# x muchos días), se poda a esta cantidad de entradas más recientes.
MAX_STATE_ENTRIES = 2000

# Movimientos en vivo de este tamaño o más se confirman con la cotización
# normal; si difieren en más de la tolerancia, se descartan.
EXTREME_MOVE_PCT = 15.0
EXTREME_MOVE_TOLERANCE_PCT = 3.0

# Etapa B: el flujo de precios en tiempo real (finmate/realtime/price_stream.py)
# llama a check_watchlist_alerts desde su propio hilo, y el job de cada 30 min
# desde el scheduler. Este lock evita que los dos lean/escriban el estado a la
# vez (y así nunca se manda la misma alerta dos veces).
_LOCK = threading.Lock()


def _load_state() -> dict:
    return load_json(STATE_FILE, {})


def _save_state(state: dict) -> None:
    try:
        if len(state) > MAX_STATE_ENTRIES:
            # Poda defensiva: conserva solo las últimas MAX_STATE_ENTRIES
            # (el orden de inserción de dict en Python 3.7+ está garantizado).
            for key in list(state.keys())[: len(state) - MAX_STATE_ENTRIES]:
                del state[key]
        save_json(STATE_FILE, state)
    except Exception as e:
        logger.error(f"Error guardando estado de alertas de watchlist: {e}")


_logged_once: set = set()


def _first_log_today(key: str) -> bool:
    """Para no repetir la misma advertencia cada 20 segundos."""
    if key in _logged_once:
        return False
    if len(_logged_once) > 5000:
        _logged_once.clear()
    _logged_once.add(key)
    return True


def check_watchlist_alerts(
    messenger: Optional[WhatsAppMessenger] = None,
    quote_fn: Optional[Callable[[str], Optional[dict]]] = None,
) -> int:
    """Ver _check_watchlist_alerts. `quote_fn(symbol)` permite usar precios
    en tiempo real (Etapa B); si devuelve None para un símbolo, se salta."""
    with _LOCK:
        return _check_watchlist_alerts(messenger, quote_fn)


def _check_watchlist_alerts(
    messenger: Optional[WhatsAppMessenger] = None,
    quote_fn: Optional[Callable[[str], Optional[dict]]] = None,
) -> int:
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
    confirmed_cache: dict = {}

    # Umbral por usuario (panel web → Ajustes). Quien no lo cambió usa el global.
    try:
        from finmate.db.settings_repo import get_thresholds_by_user

        thresholds = get_thresholds_by_user()
    except Exception as e:
        logger.warning(f"No pude leer umbrales por usuario, uso el global: {e}")
        thresholds = {}

    client = httpx.Client(timeout=10) if quote_fn is None else None
    try:
        for user_id, phone, symbol in entries:
            if symbol not in quote_cache:
                quote_cache[symbol] = (
                    quote_fn(symbol) if quote_fn is not None else _get_finnhub_quote(client, symbol)
                )
            quote = quote_cache[symbol]

            # TODO(review): `not quote.get("price")` saltea precio==0.0, válido
            # en teoría para penny stocks extremos. Comportamiento consistente con el resto del bot.
            if not quote or not quote.get("price") or quote.get("is_closed"):
                continue

            try:
                change_pct = float(quote.get("change_pct"))
            except (TypeError, ValueError):
                continue

            if abs(change_pct) < thresholds.get(user_id, WATCHLIST_ALERT_THRESHOLD_PCT):
                continue

            # Un movimiento extremo con precio en vivo puede ser una operación
            # mal registrada en el flujo (23 nov 2026: NVDA "+34%"). Se confirma
            # con la cotización normal de Finnhub antes de avisar.
            if quote_fn is not None and abs(change_pct) >= EXTREME_MOVE_PCT:
                if symbol not in confirmed_cache:
                    with httpx.Client(timeout=10) as c:
                        confirmed_cache[symbol] = _get_finnhub_quote(c, symbol)
                rest = confirmed_cache[symbol]
                try:
                    rest_change = float((rest or {}).get("change_pct"))
                except (TypeError, ValueError):
                    rest_change = None
                # Si la cotización normal también muestra un movimiento grande, el
                # movimiento es real y se avisa con esa cifra (antes se descartaba si
                # el precio en vivo difería unos puntos: 24 nov, NVDA +31% sin aviso).
                if rest_change is None or (abs(rest_change - change_pct) > EXTREME_MOVE_TOLERANCE_PCT
                                           and abs(rest_change) < thresholds.get(user_id, WATCHLIST_ALERT_THRESHOLD_PCT)):
                    if _first_log_today(f"mismatch:{symbol}:{today}"):
                        logger.warning(
                            f"Watchlist: {symbol} {change_pct:+.2f}% en vivo no coincide con la "
                            f"cotización normal ({rest_change}); no se avisa."
                        )
                    continue
                quote = rest
                change_pct = rest_change
                if abs(change_pct) < thresholds.get(user_id, WATCHLIST_ALERT_THRESHOLD_PCT):
                    continue

            state_key = f"{user_id}_{symbol}_{today}"
            if state.get(state_key):
                continue

            change_fmt = _format_number(change_pct, suffix="%")
            price_fmt = _format_number(quote["price"], prefix="$")

            # Jornada: fuera de horario no se escribe; el aviso entra en el próximo resumen.
            from finmate.services.workday import allow as _workday_allow

            if not _workday_allow(phone, f"{symbol} se movió {change_fmt} (precio {price_fmt})", "watchlist"):
                state[state_key] = True
                continue

            try:
                if TEMPLATE_WATCHLIST_ALERT:
                    ok = messenger.send_template(
                        phone,
                        TEMPLATE_WATCHLIST_ALERT,
                        {"1": symbol, "2": change_fmt, "3": price_fmt},
                    )
                else:
                    emoji = _change_emoji(change_pct)
                    msg = (
                        f"{emoji} *{symbol}* se movió {change_fmt} hoy\n"
                        f"Precio actual: {price_fmt}\n\n"
                        f"_Lo tienes en tu watchlist. Escríbeme si quieres más detalle o sacarlo de la lista._"
                    )
                    ok = messenger.send_message(phone, msg)
            except Exception as e:
                logger.error(f"Error enviando alerta de watchlist a {phone} ({symbol}): {e}")
                ok = False

            if ok:
                state[state_key] = True
                alerts_sent += 1
                logger.info(f"Alerta de watchlist enviada a {phone}: {symbol} {change_pct:+.2f}%")
    finally:
        if client is not None:
            client.close()

    _save_state(state)
    (logger.info if alerts_sent else logger.debug)(
        f"Chequeo de alertas de watchlist completado: {alerts_sent} alertas enviadas")
    return alerts_sent
