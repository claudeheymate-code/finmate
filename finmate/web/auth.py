"""Sesión del panel web.

La sesión guarda el `users.id` del mismo usuario que usa el bot (se identifica
por su número de WhatsApp). El login definitivo por código de WhatsApp llega en
la etapa 4; mientras tanto existe un acceso de desarrollo (PANEL_DEV_LOGIN),
apagado por defecto.

Protección CSRF: toda petición que modifica datos debe traer el encabezado
`X-Finmate: 1`. Un sitio ajeno no puede agregar encabezados propios a una
petición hacia este dominio sin permiso CORS (que no damos), y la cookie va con
SameSite=Lax.
"""
import functools
import re
from typing import Optional

from flask import g, jsonify, request, session

from finmate.db.models import User, get_session

_PHONE_RE = re.compile(r"^\+?\d{8,15}$")
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def normalize_phone(raw: str) -> Optional[str]:
    """'+56 9 1234 5678' → 'whatsapp:+56912345678' (el formato que usa Twilio)."""
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("whatsapp:"):
        s = s[len("whatsapp:"):]
    s = re.sub(r"[\s\-().]", "", s)
    if not _PHONE_RE.match(s):
        return None
    if not s.startswith("+"):
        s = "+" + s
    return "whatsapp:" + s


def mask_phone(phone: str) -> str:
    digits = phone.replace("whatsapp:", "")
    return digits[:5] + " •••• " + digits[-4:] if len(digits) > 9 else digits


def login_user(user: User) -> None:
    session.clear()
    session["uid"] = user.id
    session.permanent = True


def logout_user() -> None:
    session.clear()


def current_user() -> Optional[User]:
    uid = session.get("uid")
    if not uid:
        return None
    s = get_session()
    try:
        user = s.get(User, uid)
    finally:
        s.close()
    # Si el admin le quitó el acceso, la sesión abierta deja de servir al tiro.
    if user is None or (user.access_status or "approved") != "approved":
        session.pop("uid", None)
        return None
    return user


def api_login_required(fn):
    """Para /api/*: 401 sin sesión, 403 si falta el encabezado anti-CSRF."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"error": "no_autenticado"}), 401
        if request.method in MUTATING and request.headers.get("X-Finmate") != "1":
            return jsonify({"error": "falta_encabezado_csrf"}), 403
        g.user = user
        return fn(*args, **kwargs)

    return wrapper
