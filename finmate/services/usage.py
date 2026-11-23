"""
Consumo del sistema medido por el propio bot (panel admin → Costos).

- Claude: tokens de entrada/salida por modelo y por mes (sale de
  `response.usage` de cada llamada al modelo).
- WhatsApp: mensajes enviados por mes, separados en texto libre (respuestas,
  gratis dentro de la ventana de 24 h) y plantillas (avisos que inicia el bot,
  que Meta cobra), más los fallidos.

Se guarda en kv_state (clave usage:<servicio>:<AAAA-MM>). Si algo falla no
interrumpe nada: es solo contabilidad.
"""
import datetime as dt
import logging
import threading

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()


def _month(d: dt.date = None) -> str:
    return (d or dt.datetime.utcnow()).strftime("%Y-%m")


def _bump(key: str, path: list, fields: dict) -> None:
    try:
        from finmate.db.state_store import load_json, save_json

        with _LOCK:
            data = load_json(key, {}) or {}
            node = data
            for p in path:
                node = node.setdefault(p, {})
            for k, v in fields.items():
                node[k] = (node.get(k) or 0) + (v or 0)
            save_json(key, data)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"No pude registrar consumo ({key}): {e}")


def record_claude(model: str, usage) -> None:
    if usage is None:
        return
    _bump(f"usage:claude:{_month()}", [model or "?"], {
        "calls": 1,
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    })


def record_whatsapp(kind: str, ok: bool) -> None:
    """kind: "text" | "template" | "read" (marcar como leído no se cuenta)."""
    if kind == "read":
        return
    _bump(f"usage:whatsapp:{_month()}", [], {kind if ok else "failed": 1})


def get_usage(month: str = None) -> dict:
    from finmate.db.state_store import load_json

    m = month or _month()
    return {
        "month": m,
        "claude": load_json(f"usage:claude:{m}", {}) or {},
        "whatsapp": load_json(f"usage:whatsapp:{m}", {}) or {},
    }
