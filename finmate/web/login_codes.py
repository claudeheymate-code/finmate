"""
Ingreso al panel sin contraseña (etapa 4).

Dos caminos, ambos atados al número de WhatsApp del usuario:
1. Código: la web pide el número, el bot le manda un código de 6 dígitos por
   WhatsApp y el usuario lo escribe en la web (vale 10 min, 5 intentos).
2. Link: el usuario le escribe "panel" al bot y recibe un link de un solo uso
   que abre la sesión directo (vale 15 min).

Los códigos se guardan con hash (HMAC con FLASK_SECRET_KEY), nunca en claro,
en la tabla kv_state.
"""
import datetime as dt
import hashlib
import hmac
import secrets
from typing import Optional

from config import settings
from finmate.db.state_store import load_json, save_json

CODE_TTL_MIN = 10
LINK_TTL_MIN = 15
MAX_ATTEMPTS = 5
RESEND_SECONDS = 60


def _now() -> dt.datetime:
    return dt.datetime.utcnow()


def _hash(value: str) -> str:
    key = (settings.FLASK_SECRET_KEY or "finmate").encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def create_code(phone: str) -> Optional[str]:
    """Nuevo código para ese teléfono, o None si pidió otro hace menos de 60 s."""
    key = f"login_code:{phone}"
    prev = load_json(key, {}) or {}
    if prev.get("created") and (_now() - dt.datetime.fromisoformat(prev["created"])).total_seconds() < RESEND_SECONDS:
        return None
    code = f"{secrets.randbelow(1_000_000):06d}"
    save_json(key, {
        "hash": _hash(f"{phone}:{code}"),
        "created": _now().isoformat(),
        "expires": (_now() + dt.timedelta(minutes=CODE_TTL_MIN)).isoformat(),
        "attempts": 0,
    })
    return code


def verify_code(phone: str, code: str) -> bool:
    key = f"login_code:{phone}"
    data = load_json(key, {}) or {}
    if not data.get("hash"):
        return False
    if _now() > dt.datetime.fromisoformat(data["expires"]) or data.get("attempts", 0) >= MAX_ATTEMPTS:
        save_json(key, {})
        return False
    if hmac.compare_digest(data["hash"], _hash(f"{phone}:{(code or '').strip()}")):
        save_json(key, {})  # un solo uso
        return True
    data["attempts"] = data.get("attempts", 0) + 1
    save_json(key, data)
    return False


def create_link_token(user_id: int) -> str:
    token = secrets.token_urlsafe(24)
    save_json(f"login_link:{_hash(token)}", {
        "uid": user_id,
        "expires": (_now() + dt.timedelta(minutes=LINK_TTL_MIN)).isoformat(),
    })
    return token


def consume_link_token(token: str) -> Optional[int]:
    if not token:
        return None
    key = f"login_link:{_hash(token)}"
    data = load_json(key, {}) or {}
    if not data.get("uid"):
        return None
    save_json(key, {})  # un solo uso
    if _now() > dt.datetime.fromisoformat(data["expires"]):
        return None
    return int(data["uid"])


def panel_link(user_id: int) -> str:
    return f"{settings.PANEL_BASE_URL.rstrip('/')}/panel/entrar?t={create_link_token(user_id)}"
