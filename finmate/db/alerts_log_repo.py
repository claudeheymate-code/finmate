"""Repositorio del log de alertas enviadas — complementa los JSON state files (Plan Fase 6).

Provee una alternativa en DB para el dedup de alertas. Convive con los JSON
existentes (alert_state.json, watchlist_alert_state.json) sin reemplazarlos
de golpe — la migración completa queda para el hardening (Plan Fase 8).
"""
import datetime as dt
import logging

logger = logging.getLogger(__name__)


def was_alert_sent(user_id, alert_type: str, ref_id: str) -> bool:
    """True si ya existe un registro de esta alerta (user_id puede ser None = broadcast)."""
    try:
        from finmate.db.models import AlertLog, get_session
    except Exception:
        return False

    session = get_session()
    try:
        query = session.query(AlertLog).filter_by(alert_type=alert_type, ref_id=ref_id)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        return query.first() is not None
    except Exception as e:
        logger.error(f"Error consultando alerts_log: {e}")
        return False
    finally:
        session.close()


def mark_alert_sent(user_id, alert_type: str, ref_id: str) -> None:
    """Registra que se mandó la alerta. No lanza excepción si falla."""
    try:
        from finmate.db.models import AlertLog, get_session
    except Exception:
        return

    session = get_session()
    try:
        existing = session.query(AlertLog).filter_by(
            user_id=user_id, alert_type=alert_type, ref_id=ref_id
        ).first()
        if not existing:
            session.add(AlertLog(user_id=user_id, alert_type=alert_type, ref_id=ref_id))
            session.commit()
    except Exception as e:
        logger.error(f"Error registrando alerta enviada: {e}")
        session.rollback()
    finally:
        session.close()


def cleanup_old_alerts(days: int = 30) -> int:
    """Borra entradas de alertas de más de N días. Devuelve cuántas borró."""
    try:
        from finmate.db.models import AlertLog, get_session
    except Exception:
        return 0

    session = get_session()
    try:
        cutoff = dt.datetime.utcnow() - dt.timedelta(days=days)
        deleted = session.query(AlertLog).filter(AlertLog.sent_at < cutoff).delete()
        session.commit()
        return deleted
    except Exception as e:
        logger.error(f"Error en cleanup de alerts_log: {e}")
        session.rollback()
        return 0
    finally:
        session.close()
