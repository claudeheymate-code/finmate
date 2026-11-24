"""Registro de actividad sospechosa y avisos de seguridad.

record_event() nunca lanza errores: si la base falla, queda en el log y el
sistema sigue funcionando. Los eventos se ven en el panel admin (Inbox →
Seguridad). Los graves (high/critical) además llegan por WhatsApp a los
administradores, como máximo uno por tipo cada 30 minutos.
"""

import datetime as dt
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger("finmate.security")

SEVERITIES = ("info", "low", "medium", "high", "critical")
_GROUP_WINDOW = dt.timedelta(minutes=30)     # mismo tipo + IP dentro de esto → se suma a la misma fila
_NOTIFY_EVERY = 30 * 60                      # WhatsApp al admin: máx. 1 por tipo cada 30 min
_last_notified: dict = {}
_lock = threading.Lock()

# Títulos legibles para el panel (el detalle explica cada caso).
TITLES = {
    "webhook_forged": "Mensaje falso al webhook de WhatsApp",
    "webhook_bad_signature": "Firma inválida en el webhook de WhatsApp",
    "scanner": "Escaneo de vulnerabilidades",
    "flood": "Demasiadas solicitudes desde una IP",
    "login_bruteforce": "Muchos códigos de acceso incorrectos",
    "login_enumeration": "Prueba de números en el ingreso",
    "admin_denied": "Intento de entrar al admin con otra cuenta",
    "admin_oauth_error": "Error o manipulación en el ingreso con Google",
    "admin_login": "Ingreso al panel de administrador",
    "csrf_missing": "Solicitud sin protección anti-falsificación",
    "message_flood": "Un número está mandando demasiados mensajes",
    "config": "Configuración insegura",
    "integrity": "Archivos del servidor modificados",
    "dependency_vuln": "Vulnerabilidad en una librería",
    "spend_spike": "Consumo de Claude fuera de lo normal",
    "claude_error": "Claude no está respondiendo",
    "monthly_review": "Revisión mensual de limpieza y seguridad",
    "check_ok": "Chequeo de seguridad sin problemas",
}


def client_ip() -> Optional[str]:
    """IP real del visitante (Railway pasa la original en X-Forwarded-For)."""
    try:
        from flask import has_request_context, request

        if not has_request_context():
            return None
        fwd = request.headers.get("X-Forwarded-For", "")
        ip = fwd.split(",")[0].strip() if fwd else (request.remote_addr or "")
        return ip[:64] or None
    except Exception:  # noqa: BLE001
        return None


def _request_path() -> Optional[str]:
    try:
        from flask import has_request_context, request

        return request.path[:200] if has_request_context() else None
    except Exception:  # noqa: BLE001
        return None


def record_event(kind: str, severity: str, detail: str, ip: Optional[str] = None,
                 path: Optional[str] = None, notify: Optional[bool] = None) -> None:
    """Guarda (o agrupa) un evento de seguridad. Nunca lanza errores."""
    severity = severity if severity in SEVERITIES else "medium"
    ip = ip or client_ip()
    path = path or _request_path()
    log = logger.warning if severity in ("medium", "high", "critical") else logger.info
    log(f"[seguridad:{severity}] {kind} · {detail} · ip={ip or '-'} · ruta={path or '-'}")
    try:
        from finmate.db.models import SecurityEvent, get_session

        now = dt.datetime.utcnow()
        s = get_session()
        try:
            q = s.query(SecurityEvent).filter(SecurityEvent.kind == kind, SecurityEvent.status == "nuevo",
                                              SecurityEvent.last_seen >= now - _GROUP_WINDOW)
            q = q.filter(SecurityEvent.ip == ip) if ip else q.filter(SecurityEvent.ip.is_(None))
            ev = q.order_by(SecurityEvent.id.desc()).first()
            if ev is not None and kind not in ("monthly_review", "check_ok", "admin_login"):
                ev.count = (ev.count or 1) + 1
                ev.last_seen = now
                if SEVERITIES.index(severity) > SEVERITIES.index(ev.severity):
                    ev.severity = severity
                    ev.detail = detail[:4000]
            else:
                s.add(SecurityEvent(kind=kind[:40], severity=severity, detail=detail[:4000], ip=ip,
                                    path=path, created_at=now, last_seen=now))
            s.commit()
        finally:
            s.close()
    except Exception as e:  # noqa: BLE001
        logger.error(f"No pude guardar el evento de seguridad {kind}: {e}")
    if notify if notify is not None else severity in ("high", "critical"):
        _notify_admins(kind, severity, detail)


def _notify_admins(kind: str, severity: str, detail: str) -> None:
    with _lock:
        last = _last_notified.get(kind, 0)
        if time.time() - last < _NOTIFY_EVERY:
            return
        _last_notified[kind] = time.time()

    def _send():
        try:
            from config.settings import PANEL_BASE_URL, WHATSAPP_RECIPIENTS
            from finmate.whatsapp.messenger import WhatsAppMessenger

            icon = "🚨" if severity == "critical" else "⚠️"
            msg = (f"{icon} *Seguridad Finmate: {TITLES.get(kind, kind)}*\n{detail[:600]}\n\n"
                   f"Revísalo en {PANEL_BASE_URL.rstrip('/')}/admin/inbox#seguridad")
            m = WhatsAppMessenger()
            for admin in WHATSAPP_RECIPIENTS:
                m.send_message(admin, msg)
        except Exception as e:  # noqa: BLE001
            logger.info(f"No pude avisar al admin por WhatsApp del evento {kind}: {e}")

    threading.Thread(target=_send, daemon=True).start()


# ── Lectura para el panel admin ─────────────────────────────────────────

def _row(e) -> dict:
    return {"id": e.id, "kind": e.kind, "title": TITLES.get(e.kind, e.kind), "severity": e.severity,
            "detail": e.detail, "ip": e.ip or "", "path": e.path or "", "count": e.count or 1,
            "status": e.status, "created_at": e.created_at.isoformat() if e.created_at else None,
            "last_seen": e.last_seen.isoformat() if e.last_seen else None}


def list_events(limit: int = 200) -> list[dict]:
    from finmate.db.models import SecurityEvent, get_session

    s = get_session()
    try:
        rows = s.query(SecurityEvent).order_by(SecurityEvent.last_seen.desc()).limit(limit).all()
        return [_row(e) for e in rows]
    finally:
        s.close()


def open_counts() -> dict:
    """Eventos sin revisar por gravedad (para el resumen y el aviso del Inbox)."""
    out = {k: 0 for k in SEVERITIES}
    try:
        from sqlalchemy import func

        from finmate.db.models import SecurityEvent, get_session

        s = get_session()
        try:
            for sev, n in (s.query(SecurityEvent.severity, func.count(SecurityEvent.id))
                           .filter(SecurityEvent.status == "nuevo").group_by(SecurityEvent.severity)):
                out[sev] = n
        finally:
            s.close()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"No pude contar eventos de seguridad: {e}")
    return out


def set_status(event_id: Optional[int], status: str) -> int:
    """Marca un evento (o todos, con event_id=None) como revisado o nuevo."""
    if status not in ("nuevo", "revisado"):
        raise ValueError("Estado inválido")
    from finmate.db.models import SecurityEvent, get_session

    s = get_session()
    try:
        q = s.query(SecurityEvent)
        q = q.filter(SecurityEvent.id == event_id) if event_id else q.filter(SecurityEvent.status == "nuevo")
        n = q.update({SecurityEvent.status: status}, synchronize_session=False)
        s.commit()
        return n
    finally:
        s.close()


def prune(days: int = 180) -> int:
    """Borra eventos revisados más antiguos que `days` (los nuevos no se tocan)."""
    from finmate.db.models import SecurityEvent, get_session

    s = get_session()
    try:
        cutoff = dt.datetime.utcnow() - dt.timedelta(days=days)
        n = (s.query(SecurityEvent).filter(SecurityEvent.status == "revisado", SecurityEvent.last_seen < cutoff)
             .delete(synchronize_session=False))
        s.commit()
        return n
    finally:
        s.close()
