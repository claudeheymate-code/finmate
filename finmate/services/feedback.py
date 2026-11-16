"""
Finmate - Feedback del panel web.

guardar_y_enviar(): guarda el mensaje en la tabla `feedback` y lo manda por
correo a FEEDBACK_EMAIL_TO en un hilo aparte (la respuesta al usuario no
espera al correo). Canal de envío:
  1. SMTP, si están SMTP_HOST, SMTP_USER y SMTP_PASSWORD (ej. Gmail con
     contraseña de aplicación).
  2. Si no, FormSubmit (formsubmit.co), gratis y sin credenciales.
Si el correo falla, el mensaje igual queda guardado en la base de datos.
"""
import datetime as dt
import logging
import smtplib
import threading
import time
from email.message import EmailMessage
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

TIPOS = {"idea": "💡 Idea", "problema": "🐞 Problema", "me_gusta": "❤️ Me gusta", "otro": "💬 Otro"}
MAX_PER_HOUR = 5
_recent: dict = {}
_lock = threading.Lock()


def rate_limited(user_id: int, now: Optional[float] = None) -> bool:
    """True si el usuario ya mandó MAX_PER_HOUR mensajes en la última hora."""
    now = now or time.time()
    with _lock:
        stamps = [t for t in _recent.get(user_id, []) if now - t < 3600]
        if len(stamps) >= MAX_PER_HOUR:
            _recent[user_id] = stamps
            return True
        stamps.append(now)
        _recent[user_id] = stamps
        return False


def _subject(tipo: str, rating: Optional[int]) -> str:
    stars = f" · {rating}/5" if rating else ""
    return f"[Finmate] Feedback: {TIPOS.get(tipo, tipo)}{stars}"


def _body(user_id: int, phone: str, tipo: str, rating: Optional[int], message: str, contact: bool) -> str:
    who = phone if contact else f"usuario #{user_id} (no autorizó contacto)"
    return (
        f"Tipo: {TIPOS.get(tipo, tipo)}\n"
        f"Experiencia: {str(rating) + '/5' if rating else 'sin calificar'}\n"
        f"De: {who}\n"
        f"Fecha: {dt.datetime.now().strftime('%d-%m-%Y %H:%M')}\n\n"
        f"{message}\n"
    )


def _send_smtp(subject: str, body: str) -> bool:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = settings.FEEDBACK_EMAIL_TO
    msg.set_content(body)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as s:
        s.starttls()
        s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        s.send_message(msg)
    return True


def _send_formsubmit(subject: str, body: str, fields: dict) -> bool:
    target = settings.FEEDBACK_FORMSUBMIT_ID or settings.FEEDBACK_EMAIL_TO
    r = httpx.post(
        f"https://formsubmit.co/ajax/{target}",
        json={**fields, "_subject": subject, "_template": "table", "mensaje_completo": body},
        headers={"Accept": "application/json", "Origin": settings.PUBLIC_BASE_URL,
                 "Referer": settings.PUBLIC_BASE_URL + "/"},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json() if r.content else {}
    return str(data.get("success", "")).lower() == "true"


def send_email(subject: str, body: str, fields: dict) -> bool:
    try:
        if settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD:
            return _send_smtp(subject, body)
        return _send_formsubmit(subject, body, fields)
    except Exception as e:  # noqa: BLE001
        logger.error(f"No se pudo enviar el feedback por correo: {e}")
        return False


def _mark_emailed(fb_id: int) -> None:
    from finmate.db.models import Feedback, get_session
    session = get_session()
    try:
        row = session.get(Feedback, fb_id)
        if row:
            row.emailed = True
            session.commit()
    finally:
        session.close()


def guardar_y_enviar(user_id: int, phone: str, tipo: str, rating: Optional[int], message: str,
                     contact: bool, sender=None, background: bool = True) -> int:
    """Guarda el feedback y dispara el correo. Devuelve el id guardado."""
    from finmate.db.models import Feedback, get_session

    session = get_session()
    try:
        row = Feedback(user_id=user_id, tipo=tipo, rating=rating, message=message, contact_ok=contact)
        session.add(row)
        session.commit()
        fb_id = row.id
    finally:
        session.close()

    subject = _subject(tipo, rating)
    body = _body(user_id, phone, tipo, rating, message, contact)
    fields = {"tipo": TIPOS.get(tipo, tipo), "experiencia": f"{rating}/5" if rating else "—",
              "mensaje": message, "contacto": phone if contact else "No autorizó contacto"}

    def job():
        send = sender or send_email
        if send(subject, body, fields):
            _mark_emailed(fb_id)
            logger.info(f"Feedback #{fb_id} enviado a {settings.FEEDBACK_EMAIL_TO}")

    if background:
        threading.Thread(target=job, name=f"feedback-{fb_id}", daemon=True).start()
    else:
        job()
    return fb_id
