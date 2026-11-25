"""Jornada de cada usuario: cuándo el bot puede escribirle por iniciativa propia.

  - Al inicio de la jornada: un párrafo con lo relevante del mercado desde la
    jornada anterior (más los avisos que quedaron guardados fuera de horario).
  - Durante la jornada: los avisos de siempre (watchlist, noticias, macro,
    resultados, podcast).
  - Fuera de la jornada: el bot no escribe por su cuenta; solo responde si el
    usuario le pregunta algo. Los avisos de esas horas se guardan y entran en
    el resumen del inicio siguiente.

Cada usuario elige sus horas en el panel (Ajustes) o por chat. Por defecto:
lunes a viernes de 08:30 a 18:30, hora de Chile.
"""

import datetime as dt
import logging
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

DEFAULT_TZ = "America/Santiago"
HELD_MAX = 40
EDGE_WINDOW_MIN = 45          # si el tick se atrasa (deploy), se manda igual dentro de esta ventana
SENT_KEY = "workday:sent"


def _tz(name: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except Exception:  # noqa: BLE001
        return ZoneInfo(DEFAULT_TZ)


def _hm(value: str) -> dt.time:
    hh, mm = (int(x) for x in value.split(":", 1))
    return dt.time(hh, mm)


def _user_info(phone: str):
    """(user_id, timezone) o (None, None) si el número no es de un usuario."""
    try:
        from finmate.db.repository import find_user_by_phone

        u = find_user_by_phone(phone)
        return (u.id, getattr(u, "timezone", None) or DEFAULT_TZ) if u else (None, None)
    except Exception:  # noqa: BLE001
        return None, None


# ── Ventana de 24 h de WhatsApp ─────────────────────────────────────────
# Meta solo entrega texto libre a quien le escribió al bot en las últimas 24 h.
# Fuera de esa ventana el envío "sale" pero Meta lo rechaza después (error
# 131047) y el mensaje se pierde. Mientras no haya plantillas aprobadas, lo que
# el bot quiera mandar por su cuenta se guarda y llega cuando el usuario escriba.
WINDOW_HOURS = 23.5          # un poco menos de 24 h, por si el envío se atrasa


def last_user_message_at(user_id: int) -> Optional[dt.datetime]:
    from sqlalchemy import func

    from finmate.db.models import ConversationTurn, get_session

    s = get_session()
    try:
        return (s.query(func.max(ConversationTurn.timestamp))
                .filter(ConversationTurn.user_id == user_id, ConversationTurn.role == "user").scalar())
    finally:
        s.close()


def window_open(user_id: int, now: Optional[dt.datetime] = None) -> bool:
    """¿El usuario le escribió al bot en las últimas ~24 h? (si no se puede saber, se asume que sí)."""
    try:
        last = last_user_message_at(user_id)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Jornada: no pude revisar la ventana de 24 h del usuario {user_id}: {e}")
        return True
    return bool(last) and (now or dt.datetime.utcnow()) - last < dt.timedelta(hours=WINDOW_HOURS)


def can_message(user_id: int) -> bool:
    """¿Se le puede escribir por iniciativa propia ahora? Sí si la ventana está abierta o hay plantilla."""
    from config.settings import TEMPLATE_MARKET_NOTIFY

    return bool(TEMPLATE_MARKET_NOTIFY) or window_open(user_id)


def in_workday(user_id: int, tz_name: str = DEFAULT_TZ, now: Optional[dt.datetime] = None) -> bool:
    from finmate.db.settings_repo import get_notification_settings

    s = get_notification_settings(user_id)
    if not s.get("workday_enabled", True):
        return True                       # jornada apagada: los avisos llegan a cualquier hora
    local = (now or dt.datetime.now(dt.timezone.utc)).astimezone(_tz(tz_name))
    if local.weekday() >= 5 and not s.get("workday_weekends"):
        return False
    start, end, t = _hm(s["workday_start"]), _hm(s["workday_end"]), local.time()
    return start <= t < end if start < end else (t >= start or t < end)   # jornada que cruza medianoche


# ── Avisos guardados fuera de horario ───────────────────────────────────

def _held_key(user_id: int) -> str:
    return f"held:{user_id}"


def hold(user_id: int, text: str, kind: str) -> None:
    from finmate.db.state_store import load_json, save_json

    items = load_json(_held_key(user_id), []) or []
    items.append({"at": dt.datetime.utcnow().isoformat(timespec="minutes"), "kind": kind, "text": (text or "")[:700]})
    save_json(_held_key(user_id), items[-HELD_MAX:])


def pop_held(user_id: int) -> list:
    from finmate.db.state_store import load_json, save_json

    items = load_json(_held_key(user_id), []) or []
    if items:
        save_json(_held_key(user_id), [])
    return items


def in_workday_for_phone(phone: str) -> bool:
    """¿Se le puede mandar un aviso ahora a este número? Dentro de su jornada y con la
    ventana de 24 h de WhatsApp abierta (o plantilla). True si no es usuario o si falla."""
    uid, tz_name = _user_info(phone)
    if uid is None:
        return True
    try:
        return in_workday(uid, tz_name) and can_message(uid)
    except Exception:  # noqa: BLE001
        return True


def allow(phone: str, text: str, kind: str) -> bool:
    """¿Se puede mandar este aviso ahora? Si el usuario está fuera de su jornada,
    se guarda para el resumen del inicio siguiente y devuelve False."""
    uid, tz_name = _user_info(phone)
    if uid is None:
        return True
    try:
        if in_workday(uid, tz_name):
            if can_message(uid):
                return True
            hold(uid, text, kind)
            logger.info(f"Jornada: aviso '{kind}' para el usuario {uid} guardado (no escribe hace más de 24 h: "
                        "WhatsApp no deja mandárselo ahora).")
            return False
        hold(uid, text, kind)
        logger.info(f"Jornada: aviso '{kind}' para el usuario {uid} guardado para el próximo inicio de jornada.")
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Jornada: no pude revisar el horario del usuario {uid}: {e}")
        return True


def filter_recipients(phones: list, text: str, kind: str) -> list:
    return [p for p in (phones or []) if allow(p, text, kind)]


# ── Resumen de inicio y cierre (job cada 5 minutos) ─────────────────────

def _approved_users():
    from finmate.db.models import User, get_session

    s = get_session()
    try:
        return [(u.id, u.phone, getattr(u, "timezone", None) or DEFAULT_TZ, u.name or "")
                for u in s.query(User).all() if (u.access_status or "approved") == "approved"]
    finally:
        s.close()


def due_edges(user_id: int, tz_name: str, now: Optional[dt.datetime] = None) -> list:
    """Qué resúmenes ("start"/"end") tocan ahora para este usuario."""
    from finmate.db.settings_repo import get_notification_settings

    s = get_notification_settings(user_id)
    if not s.get("workday_enabled", True):
        return []
    local = (now or dt.datetime.now(dt.timezone.utc)).astimezone(_tz(tz_name))
    out = []
    for edge in ("start", "end"):
        t = _hm(s[f"workday_{edge}"])
        edge_dt = local.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if edge == "end" and edge_dt > local:          # cierre de una jornada que empezó ayer (cruza medianoche)
            edge_dt -= dt.timedelta(days=1)
        if edge_dt.weekday() >= 5 and not s.get("workday_weekends"):
            continue
        if 0 <= (local - edge_dt).total_seconds() < EDGE_WINDOW_MIN * 60:
            out.append((edge, edge_dt.date().isoformat()))
    return out


def run_workday_tick(now: Optional[dt.datetime] = None) -> int:
    """Manda los resúmenes de inicio/cierre que correspondan. Devuelve cuántos mandó."""
    from finmate.db.state_store import load_json, save_json
    from finmate.services.daily_brief import send_brief

    sent = load_json(SENT_KEY, {}) or {}
    cutoff = (dt.date.today() - dt.timedelta(days=4)).isoformat()
    sent = {k: v for k, v in sent.items() if k.rsplit(":", 1)[-1] >= cutoff or v >= cutoff}
    n = 0
    for uid, phone, tz_name, name in _approved_users():
        try:
            for edge, day in due_edges(uid, tz_name, now):
                key = f"{uid}:{edge}:{day}"
                if key in sent:
                    continue
                sent[key] = day                         # se marca antes: nunca se manda dos veces
                save_json(SENT_KEY, sent)
                if send_brief(uid, phone, edge, name=name, tz_name=tz_name):
                    n += 1
        except Exception as e:  # noqa: BLE001
            logger.error(f"Jornada: error con el usuario {uid}: {e}", exc_info=True)
    return n
