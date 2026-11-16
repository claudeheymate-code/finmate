"""Preferencias de avisos por usuario (panel web, etapa 1).

Si un usuario no tiene fila en `notification_settings`, se usan los valores
globales de config/settings.py, así nada cambia para quien nunca tocó sus
ajustes.
"""
import logging
from typing import Dict, Optional

from config.settings import WATCHLIST_ALERT_THRESHOLD_PCT

logger = logging.getLogger(__name__)

MIN_THRESHOLD = 0.5
MAX_THRESHOLD = 50.0


def _defaults() -> dict:
    return {
        "watchlist_threshold_pct": float(WATCHLIST_ALERT_THRESHOLD_PCT),
        "weekly_summary_enabled": True,
    }


def get_notification_settings(user_id: int) -> dict:
    from finmate.db.models import NotificationSettings, get_session

    session = get_session()
    try:
        row = session.query(NotificationSettings).filter_by(user_id=user_id).one_or_none()
        out = _defaults()
        if row is not None:
            if row.watchlist_threshold_pct is not None:
                out["watchlist_threshold_pct"] = float(row.watchlist_threshold_pct)
            out["weekly_summary_enabled"] = bool(row.weekly_summary_enabled)
        return out
    finally:
        session.close()


def set_notification_settings(
    user_id: int,
    watchlist_threshold_pct: Optional[float] = None,
    weekly_summary_enabled: Optional[bool] = None,
) -> dict:
    """Actualiza solo lo que se pasa. Valida el umbral (0,5% a 50%)."""
    from finmate.db.models import NotificationSettings, get_session

    if watchlist_threshold_pct is not None:
        pct = float(watchlist_threshold_pct)
        if not (MIN_THRESHOLD <= pct <= MAX_THRESHOLD):
            raise ValueError(
                f"El umbral tiene que estar entre {MIN_THRESHOLD:g}% y {MAX_THRESHOLD:g}%."
            )
        watchlist_threshold_pct = pct

    session = get_session()
    try:
        row = session.query(NotificationSettings).filter_by(user_id=user_id).one_or_none()
        if row is None:
            row = NotificationSettings(user_id=user_id, weekly_summary_enabled=True)
            session.add(row)
        if watchlist_threshold_pct is not None:
            row.watchlist_threshold_pct = watchlist_threshold_pct
        if weekly_summary_enabled is not None:
            row.weekly_summary_enabled = bool(weekly_summary_enabled)
        session.commit()
    finally:
        session.close()
    return get_notification_settings(user_id)


def get_thresholds_by_user() -> Dict[int, float]:
    """{user_id: umbral} solo de quienes lo personalizaron (para watchlist_alerts)."""
    from finmate.db.models import NotificationSettings, get_session

    session = get_session()
    try:
        rows = (
            session.query(NotificationSettings)
            .filter(NotificationSettings.watchlist_threshold_pct.isnot(None))
            .all()
        )
        return {r.user_id: float(r.watchlist_threshold_pct) for r in rows}
    finally:
        session.close()


def weekly_summary_enabled_for_phone(phone: str) -> bool:
    """True salvo que el usuario de ese teléfono lo haya desactivado.
    Ante cualquier error (p. ej. sin base de datos) devuelve True, para no
    dejar de mandar el resumen que ya funciona en producción."""
    try:
        from finmate.db.models import NotificationSettings, User, get_session

        session = get_session()
        try:
            row = (
                session.query(NotificationSettings)
                .join(User, User.id == NotificationSettings.user_id)
                .filter(User.phone == phone)
                .one_or_none()
            )
            return True if row is None else bool(row.weekly_summary_enabled)
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"No pude leer preferencias de resumen semanal ({phone}): {e}")
        return True
