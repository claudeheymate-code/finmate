"""
Finmate - Precios en tiempo real con el WebSocket gratis de Finnhub (Etapa B).

Antes, la alerta de watchlist ("NVDA se movió 5%") podía llegar hasta 30
minutos tarde, porque se revisaba por consulta periódica. Ahora:

1. Un hilo mantiene abierta la conexión wss://ws.finnhub.io y se suscribe a
   los símbolos de todas las watchlists (máximo REALTIME_MAX_SYMBOLS = 50,
   el límite del plan gratis). Cada operación actualiza el último precio.
2. Cada REALTIME_EVAL_SECONDS (default 20) se evalúan las alertas de
   watchlist con esos precios en vivo (misma función, mismo umbral por
   usuario y mismo estado de "ya avisé hoy" que el chequeo de cada 30 min,
   así que nunca se duplica un aviso).
3. La variación del día se calcula contra el cierre anterior, que se pide
   una vez por símbolo al endpoint REST /quote.

Si la conexión se cae (pasa a veces en el plan gratis, a veces sin aviso),
se reconecta sola con espera creciente (5 s → 60 s). El chequeo de cada 30
min sigue corriendo como respaldo.

Solo acciones de EE.UU. (lo que cubre el plan gratis). Los símbolos con
guion o dos puntos (ej. BTC-USD) se ignoran acá.
"""
import json
import logging
import re
import threading
import time
from typing import Callable, Iterable, Optional

import httpx

from config.settings import (
    FINNHUB_API_KEY,
    REALTIME_EVAL_SECONDS,
    REALTIME_MAX_SYMBOLS,
    REALTIME_PRICES_ENABLED,
)

logger = logging.getLogger(__name__)

WS_URL = "wss://ws.finnhub.io?token={token}"
REST_QUOTE = "https://finnhub.io/api/v1/quote"
STALE_SECONDS = 180            # un precio más viejo que esto no se usa
RESUBSCRIBE_SECONDS = 300      # cada cuánto se revisa qué símbolos seguir
PREV_CLOSE_MAX_AGE = 6 * 3600  # se vuelve a pedir el cierre anterior cada 6 h

_TICKER_RE = re.compile(r"^[A-Z][A-Z.]{0,9}$")


def _watchlist_symbols() -> list:
    from finmate.db.repository import get_all_watchlist_entries

    return [sym for _uid, _phone, sym in get_all_watchlist_entries()]


def _fetch_prev_close(symbol: str) -> Optional[float]:
    try:
        r = httpx.get(REST_QUOTE, params={"symbol": symbol, "token": FINNHUB_API_KEY}, timeout=10)
        r.raise_for_status()
        pc = (r.json() or {}).get("pc")
        return float(pc) if pc else None
    except Exception as e:
        logger.warning(f"No pude obtener el cierre anterior de {symbol}: {e}")
        return None


class PriceStream:
    def __init__(
        self,
        api_key: str = FINNHUB_API_KEY,
        symbols_fn: Callable[[], Iterable[str]] = _watchlist_symbols,
        prev_close_fn: Callable[[str], Optional[float]] = _fetch_prev_close,
        evaluate_fn: Optional[Callable] = None,
        max_symbols: int = REALTIME_MAX_SYMBOLS,
        eval_seconds: int = REALTIME_EVAL_SECONDS,
        clock: Callable[[], float] = time.time,
    ):
        self.api_key = api_key
        self.symbols_fn = symbols_fn
        self.prev_close_fn = prev_close_fn
        self.evaluate_fn = evaluate_fn
        self.max_symbols = max_symbols
        self.eval_seconds = eval_seconds
        self.clock = clock
        self.last: dict = {}         # symbol -> (price, epoch_seconds)
        self.prev_close: dict = {}   # symbol -> (price, fetched_at)
        self.subscribed: set = set()
        self.ws = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._last_resub = 0.0

    # ── Precios ─────────────────────────────────────────────────────────
    def handle_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except (TypeError, ValueError):
            return
        if msg.get("type") != "trade":
            return  # "ping" y otros mensajes de control
        with self._lock:
            for t in msg.get("data") or []:
                sym, price, ts = t.get("s"), t.get("p"), t.get("t")
                if not sym or price is None or ts is None:
                    continue
                ts = ts / 1000.0  # Finnhub manda milisegundos
                prev = self.last.get(sym)
                if prev is None or ts >= prev[1]:
                    self.last[sym] = (float(price), ts)

    def get_quote(self, symbol: str) -> Optional[dict]:
        """Cotización en vivo con el mismo formato que _get_finnhub_quote,
        o None si no hay operación reciente o falta el cierre anterior."""
        with self._lock:
            last = self.last.get(symbol)
            pc = self.prev_close.get(symbol)
        if not last or not pc or not pc[0]:
            return None
        price, ts = last
        if self.clock() - ts > STALE_SECONDS:
            return None
        return {
            "price": price,
            "change_pct": (price - pc[0]) / pc[0] * 100.0,
            "is_closed": False,
            "timestamp": int(ts),
        }

    # ── Suscripciones ───────────────────────────────────────────────────
    def wanted_symbols(self) -> list:
        try:
            raw = self.symbols_fn() or []
        except Exception as e:
            logger.error(f"No pude leer los símbolos a seguir en tiempo real: {e}")
            return sorted(self.subscribed)
        clean = sorted({s.upper() for s in raw if s and _TICKER_RE.match(s.upper())})
        if len(clean) > self.max_symbols:
            logger.warning(f"{len(clean)} símbolos en watchlists; el plan gratis permite "
                           f"{self.max_symbols}, sigo los primeros")
        return clean[: self.max_symbols]

    def refresh_subscriptions(self, send: Optional[Callable[[str], None]] = None) -> None:
        send = send or (self.ws.send if self.ws else None)
        wanted = set(self.wanted_symbols())
        now = self.clock()
        for sym in wanted:
            pc = self.prev_close.get(sym)
            if pc is None or now - pc[1] > PREV_CLOSE_MAX_AGE:
                value = self.prev_close_fn(sym)
                if value:
                    with self._lock:
                        self.prev_close[sym] = (value, now)
        if send is None:
            return
        for sym in sorted(wanted - self.subscribed):
            send(json.dumps({"type": "subscribe", "symbol": sym}))
        for sym in sorted(self.subscribed - wanted):
            send(json.dumps({"type": "unsubscribe", "symbol": sym}))
            with self._lock:
                self.last.pop(sym, None)
        self.subscribed = wanted
        self._last_resub = now

    # ── Evaluación de alertas ───────────────────────────────────────────
    def evaluate(self) -> int:
        with self._lock:
            has_live = bool(self.last)
        if not has_live:
            return 0
        fn = self.evaluate_fn
        if fn is None:
            from finmate.alerts.watchlist_alerts import check_watchlist_alerts
            fn = check_watchlist_alerts
        return fn(quote_fn=self.get_quote)

    def _evaluator_loop(self) -> None:
        while not self._stop.wait(self.eval_seconds):
            try:
                if self.ws is not None and self.clock() - self._last_resub > RESUBSCRIBE_SECONDS:
                    self.refresh_subscriptions()
                self.evaluate()
            except Exception as e:
                logger.error(f"Error evaluando alertas en tiempo real: {e}")

    # ── Conexión ────────────────────────────────────────────────────────
    def _run_ws_forever(self) -> None:
        import websocket  # websocket-client

        backoff = 5
        while not self._stop.is_set():
            connected_at = time.time()

            def on_open(ws):
                logger.info("📡 Conectado al flujo de precios en tiempo real de Finnhub")
                self.subscribed = set()
                try:
                    self.refresh_subscriptions(ws.send)
                except Exception as e:
                    logger.error(f"Error suscribiendo símbolos: {e}")

            def on_message(_ws, message):
                self.handle_message(message)

            def on_error(_ws, error):
                logger.warning(f"Flujo de precios: error {error}")

            self.ws = websocket.WebSocketApp(
                WS_URL.format(token=self.api_key),
                on_open=on_open, on_message=on_message, on_error=on_error,
            )
            try:
                self.ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                logger.warning(f"Flujo de precios terminó con error: {e}")
            self.ws = None
            self.subscribed = set()
            if self._stop.is_set():
                break
            # Si duró más de un minuto conectado, se vuelve a la espera corta.
            backoff = 5 if time.time() - connected_at > 60 else min(backoff * 2, 60)
            logger.info(f"Flujo de precios desconectado; reintento en {backoff}s")
            self._stop.wait(backoff)

    def start(self) -> None:
        threading.Thread(target=self._run_ws_forever, name="finnhub-ws", daemon=True).start()
        threading.Thread(target=self._evaluator_loop, name="realtime-alerts", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass


_stream: Optional[PriceStream] = None


def start_price_stream() -> Optional[PriceStream]:
    """Arranca el flujo una sola vez (llamado desde wsgi.py). Devuelve None
    si está desactivado o falta FINNHUB_API_KEY."""
    global _stream
    if _stream is not None:
        return _stream
    if not REALTIME_PRICES_ENABLED or not FINNHUB_API_KEY:
        logger.info("Precios en tiempo real desactivados (REALTIME_PRICES_ENABLED o FINNHUB_API_KEY)")
        return None
    _stream = PriceStream()
    _stream.start()
    return _stream


def get_live_quote(symbol: str) -> Optional[dict]:
    """Precio en vivo si el flujo está corriendo y tiene dato reciente."""
    return _stream.get_quote(symbol.upper()) if _stream is not None else None
