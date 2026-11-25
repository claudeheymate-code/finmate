"""Anuncios del admin a todos los usuarios (pestaña Anuncios del panel admin).

WhatsApp solo deja mandar texto libre a quien escribió en las últimas 24 h.
Por eso cada usuario recibe el anuncio de una de estas formas:
  - "sent":     escribió hace poco → le llega al tiro.
  - "template": hay plantilla de aviso aprobada (TEMPLATE_MARKET_NOTIFY) → le
                llega el aviso corto y el texto completo apenas responde.
  - "pending":  sin plantilla → le llega apenas vuelva a escribirle al bot
                (justo después de la respuesta). Al llegar pasa a "later".
El anuncio queda en el historial de conversación, así el bot puede responder
preguntas sobre él.
"""

import datetime as dt
import logging
from typing import Optional

logger = logging.getLogger(__name__)

WINDOW_HOURS = 23.5          # un poco menos de 24 h, por si el envío se demora
MAX_TITLE = 120
MAX_BODY = 3000


def format_message(title: str, body: str) -> str:
    title = (title or "").strip().replace("*", "")
    body = (body or "").strip()
    return f"📣 *{title}*\n\n{body}" if title else f"📣 {body}"


def _recipients(audience: str) -> list:
    """[(user_id | None, phone, last_user_message_at | None)]."""
    from sqlalchemy import func

    from config.settings import WHATSAPP_RECIPIENTS
    from finmate.db.models import ConversationTurn, User, get_session

    s = get_session()
    try:
        last = (s.query(ConversationTurn.user_id, func.max(ConversationTurn.timestamp))
                .filter(ConversationTurn.role == "user").group_by(ConversationTurn.user_id).all())
        last = {uid: ts for uid, ts in last}
        users = s.query(User).all()
        if audience == "test":
            by_phone = {u.phone: u for u in users}
            return [((by_phone[p].id if p in by_phone else None), p, last.get(by_phone[p].id) if p in by_phone else None)
                    for p in WHATSAPP_RECIPIENTS]
        return [(u.id, u.phone, last.get(u.id)) for u in users
                if (u.access_status or "approved") == "approved"]
    finally:
        s.close()


def _in_window(last_at, now: Optional[dt.datetime] = None) -> bool:
    now = now or dt.datetime.utcnow()
    return bool(last_at) and (now - last_at) < dt.timedelta(hours=WINDOW_HOURS)


def preview_counts(audience: str = "all") -> dict:
    rows = _recipients(audience)
    now_n = sum(1 for _u, _p, last in rows if _in_window(last))
    return {"total": len(rows), "now": now_n, "later": len(rows) - now_n}


def send(title: str, body: str, audience: str = "all", admin: str = "", messenger=None) -> dict:
    """Crea el anuncio y lo entrega. Devuelve el anuncio con sus números."""
    from config.settings import TEMPLATE_MARKET_NOTIFY
    from finmate.db.models import Announcement, AnnouncementDelivery, get_session

    title, body = (title or "").strip(), (body or "").strip()
    if len(body) < 5:
        raise ValueError("Escribe el mensaje del anuncio.")
    if len(title) > MAX_TITLE or len(body) > MAX_BODY:
        raise ValueError(f"El título va hasta {MAX_TITLE} caracteres y el mensaje hasta {MAX_BODY}.")
    if audience not in ("all", "test"):
        raise ValueError("Elige a quién mandarlo: todos o solo a ti (prueba).")
    if messenger is None:
        from finmate.whatsapp.messenger import WhatsAppMessenger
        messenger = WhatsAppMessenger()
    text = format_message(title, body)
    rows = _recipients(audience)
    if audience == "test" and not rows:
        raise ValueError("No hay números de admin configurados (WHATSAPP_RECIPIENTS) para la prueba.")

    s = get_session()
    try:
        a = Announcement(title=title or None, body=body, audience=audience, created_by=admin or None)
        s.add(a)
        s.commit()
        aid = a.id
    finally:
        s.close()

    results = []
    for uid, phone, last in rows:
        status = "failed"
        try:
            if _in_window(last) or audience == "test":
                status = "sent" if messenger.send_message(phone, text) else "failed"
            elif TEMPLATE_MARKET_NOTIFY:
                from finmate.alerts.pending import queue_pending

                queue_pending(phone, text)
                status = "template" if messenger.send_template(phone, TEMPLATE_MARKET_NOTIFY,
                                                               {"1": "Anuncio de Finmate"}) else "pending"
            else:
                status = "pending"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Anuncio {aid}: no pude entregarlo a {phone}: {e}")
        if uid is not None:
            results.append((uid, status))
            if status == "sent":
                _save_history(uid, text)
    s = get_session()
    try:
        for uid, status in results:
            s.add(AnnouncementDelivery(announcement_id=aid, user_id=uid, status=status))
        s.commit()
    finally:
        s.close()
    logger.info(f"Anuncio {aid} ({audience}) por {admin}: " +
                ", ".join(f"{k}={v}" for k, v in _count([st for _u, st in results]).items()))
    return get(aid)


def _save_history(uid: int, text: str) -> None:
    try:
        from finmate.db.repository import save_turn

        save_turn(uid, "assistant", text)
    except Exception:  # noqa: BLE001
        pass


def _count(statuses) -> dict:
    out = {"sent": 0, "template": 0, "pending": 0, "later": 0, "failed": 0}
    for st in statuses:
        out[st] = out.get(st, 0) + 1
    return out


def _as_dict(a, statuses) -> dict:
    c = _count(statuses)
    return {"id": a.id, "title": a.title or "", "body": a.body, "audience": a.audience,
            "created_by": a.created_by or "", "created_at": a.created_at.isoformat() if a.created_at else None,
            "text": format_message(a.title, a.body), "counts": c, "total": len(statuses),
            "delivered": c["sent"] + c["later"]}


def get(aid: int) -> Optional[dict]:
    from finmate.db.models import Announcement, AnnouncementDelivery, get_session

    s = get_session()
    try:
        a = s.get(Announcement, aid)
        if a is None:
            return None
        sts = [d.status for d in s.query(AnnouncementDelivery).filter_by(announcement_id=aid).all()]
        return _as_dict(a, sts)
    finally:
        s.close()


def history(limit: int = 30) -> list:
    from finmate.db.models import Announcement, AnnouncementDelivery, get_session

    s = get_session()
    try:
        items = s.query(Announcement).order_by(Announcement.created_at.desc()).limit(limit).all()
        ids = [a.id for a in items]
        sts: dict = {i: [] for i in ids}
        if ids:
            for d in s.query(AnnouncementDelivery).filter(AnnouncementDelivery.announcement_id.in_(ids)).all():
                sts[d.announcement_id].append(d.status)
        return [_as_dict(a, sts[a.id]) for a in items]
    finally:
        s.close()


def cancel_pending(aid: int) -> dict:
    """Deja de entregar el anuncio a quienes todavía no lo recibieron."""
    from finmate.db.models import AnnouncementDelivery, get_session

    s = get_session()
    try:
        for d in s.query(AnnouncementDelivery).filter_by(announcement_id=aid, status="pending").all():
            d.status = "failed"
        s.commit()
    finally:
        s.close()
    return get(aid)


def take_pending(user_id: int) -> list:
    """Textos de anuncios que este usuario todavía no recibe; quedan marcados como entregados.
    Se llama cuando el usuario escribe (la ventana de 24 h está abierta)."""
    from finmate.db.models import Announcement, AnnouncementDelivery, get_session

    s = get_session()
    try:
        rows = (s.query(AnnouncementDelivery, Announcement)
                .join(Announcement, Announcement.id == AnnouncementDelivery.announcement_id)
                .filter(AnnouncementDelivery.user_id == user_id, AnnouncementDelivery.status == "pending")
                .order_by(Announcement.created_at.asc()).all())
        texts = []
        for d, a in rows:
            d.status = "later"
            texts.append(format_message(a.title, a.body))
        s.commit()
        return texts
    finally:
        s.close()


def deliver_pending(phone: str, messenger=None) -> int:
    """Manda los anuncios pendientes de este número (después de responderle)."""
    try:
        from finmate.db.repository import find_user_by_phone

        user = find_user_by_phone(phone)
        if user is None or (user.access_status or "approved") != "approved":
            return 0
        texts = take_pending(user.id)
        if not texts:
            return 0
        if messenger is None:
            from finmate.whatsapp.messenger import WhatsAppMessenger
            messenger = WhatsAppMessenger()
        for t in texts:
            messenger.send_message(phone, t)
            _save_history(user.id, t)
        return len(texts)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Anuncios: no pude entregar los pendientes a {phone}: {e}")
        return 0


_DRAFT_SYSTEM = (
    "Eres Finmate, un asistente financiero por WhatsApp. Redacta un anuncio para TODOS los usuarios a partir "
    "de las notas del administrador. Español de Chile, tuteo (nunca voseo), cercano y claro, sin tecnicismos "
    "de programación. Formato WhatsApp: párrafos cortos y, si ayuda, viñetas con '•'. Usa negrita (*así*) solo "
    "en uno o dos subtítulos, nunca en cada línea. Sin saludo largo ni despedida larga. Máximo 900 caracteres. "
    "Explica qué cambió, para qué le sirve al usuario y qué tiene que hacer (si algo). No inventes funciones "
    "que no estén en las notas. Responde en JSON con las claves \"title\" (máx. 60 caracteres, sin emojis) y "
    "\"body\"."
)


def draft_with_ai(notes: str) -> dict:
    """Convierte notas sueltas en un anuncio listo (título + mensaje)."""
    import json
    import re

    from finmate.agent.orchestrator import ANTHROPIC_MODEL_DEFAULT, _client, _record_usage

    notes = (notes or "").strip()
    if len(notes) < 10:
        raise ValueError("Escribe primero algunas notas de qué quieres anunciar.")
    if _client is None:
        raise ValueError("Falta la clave de Claude (ANTHROPIC_API_KEY) para redactar.")
    r = _client.messages.create(model=ANTHROPIC_MODEL_DEFAULT, max_tokens=900, system=_DRAFT_SYSTEM,
                                messages=[{"role": "user", "content": notes[:4000]}])
    _record_usage(ANTHROPIC_MODEL_DEFAULT, r)
    raw = "".join(b.text for b in r.content if b.type == "text").strip()
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        data = {}
    title = str(data.get("title") or "").strip()[:MAX_TITLE]
    body = str(data.get("body") or raw).strip()[:MAX_BODY]
    return {"title": title, "body": body}
