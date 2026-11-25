"""
Consumo del sistema medido por el propio bot (panel admin → Costos).

- Claude: tokens de entrada/salida por modelo y por mes (sale de
  `response.usage` de cada llamada al modelo).
- WhatsApp: mensajes enviados por mes, separados en texto libre (respuestas,
  gratis dentro de la ventana de 24 h) y plantillas (avisos que inicia el bot,
  que Meta cobra), más los fallidos.

Se guarda en kv_state (clave usage:<servicio>:<AAAA-MM>). Si algo falla no
interrumpe nada: es solo contabilidad.

Por usuario (desde el 25 nov 2026, panel admin → Usuarios): cada llamada a
Claude y cada mensaje de WhatsApp se anota también bajo el número que lo
generó, en usage:users:<AAAA-MM> → {"56912345678": {"claude": {modelo: {...}},
"wa": {"text": n, "template": n}}}. El número se toma del destinatario (WhatsApp)
o del contexto que fija el código que atiende a ese usuario (`for_user`).
"""
import contextlib
import contextvars
import datetime as dt
import logging
import re
import threading

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()
_CURRENT = contextvars.ContextVar("finmate_usage_phone", default=None)
SINCE_KEY = "usage:users:since"


def phone_key(phone) -> str:
    """'whatsapp:+56 9 1234 5678' / '56912345678' → '56912345678'."""
    return re.sub(r"\D", "", str(phone or ""))


@contextlib.contextmanager
def for_user(phone):
    """Todo el consumo de Claude dentro de este bloque se anota a este número."""
    token = _CURRENT.set(phone_key(phone) or None)
    try:
        yield
    finally:
        _CURRENT.reset(token)


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


def _mark_since() -> None:
    try:
        from finmate.db.state_store import load_json, save_json

        if not load_json(SINCE_KEY, None):
            save_json(SINCE_KEY, dt.datetime.utcnow().isoformat(timespec="minutes"))
    except Exception:  # noqa: BLE001
        pass


def record_claude(model: str, usage) -> None:
    if usage is None:
        return
    fields = {
        "calls": 1,
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }
    _bump(f"usage:claude:{_month()}", [model or "?"], fields)
    who = _CURRENT.get()
    if who:
        _mark_since()
        _bump(f"usage:users:{_month()}", [who, "claude", model or "?"], fields)


def record_whatsapp(kind: str, ok: bool, to=None) -> None:
    """kind: "text" | "template" | "interactive" | "read" (marcar como leído no se cuenta)."""
    if kind == "read":
        return
    key = kind if ok else "failed"
    _bump(f"usage:whatsapp:{_month()}", [], {key: 1})
    who = phone_key(to)
    if who:
        _mark_since()
        _bump(f"usage:users:{_month()}", [who, "wa"], {key: 1})


def get_user_usage(month: str = None) -> dict:
    from finmate.db.state_store import load_json

    return load_json(f"usage:users:{month or _month()}", {}) or {}


def tracking_since():
    from finmate.db.state_store import load_json

    return load_json(SINCE_KEY, None)


def get_usage(month: str = None) -> dict:
    from finmate.db.state_store import load_json

    m = month or _month()
    return {
        "month": m,
        "claude": load_json(f"usage:claude:{m}", {}) or {},
        "whatsapp": load_json(f"usage:whatsapp:{m}", {}) or {},
    }
