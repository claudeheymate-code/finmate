"""Repositorio de configuración de personalidad por usuario (Plan Fase 1)."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULTS = dict(
    humor=5,
    sarcasmo=3,
    frecuencia_chistes=3,
    nivel_conversador=5,
    tono="profesional",
)


def get_personality(user_id: int) -> dict:
    """Devuelve la personalidad del usuario (o defaults si no tiene una guardada)."""
    try:
        from finmate.db.models import PersonalitySettings, get_session
    except Exception:
        return dict(_DEFAULTS)

    session = get_session()
    try:
        p = session.query(PersonalitySettings).filter_by(user_id=user_id).first()
        if p is None:
            return dict(_DEFAULTS)
        return dict(
            humor=p.humor,
            sarcasmo=p.sarcasmo,
            frecuencia_chistes=p.frecuencia_chistes,
            nivel_conversador=p.nivel_conversador,
            tono=p.tono,
        )
    except Exception as e:
        logger.error(f"Error leyendo personalidad de user {user_id}: {e}")
        return dict(_DEFAULTS)
    finally:
        session.close()


def set_personality(user_id: int, **kwargs) -> dict:
    """Actualiza uno o más parámetros de personalidad. Crea el registro si no existe.
    Campos válidos: humor, sarcasmo, frecuencia_chistes, nivel_conversador, tono."""
    try:
        from finmate.db.models import PersonalitySettings, get_session
    except Exception:
        return dict(_DEFAULTS)

    session = get_session()
    try:
        p = session.query(PersonalitySettings).filter_by(user_id=user_id).first()
        if p is None:
            init_vals = {k: v for k, v in kwargs.items() if k in _DEFAULTS}
            p = PersonalitySettings(user_id=user_id, **init_vals)
            session.add(p)
        else:
            for key, val in kwargs.items():
                if key in _DEFAULTS and hasattr(p, key):
                    setattr(p, key, val)
        session.commit()
        session.refresh(p)
        return dict(
            humor=p.humor,
            sarcasmo=p.sarcasmo,
            frecuencia_chistes=p.frecuencia_chistes,
            nivel_conversador=p.nivel_conversador,
            tono=p.tono,
        )
    except Exception as e:
        logger.error(f"Error guardando personalidad de user {user_id}: {e}")
        session.rollback()
        return get_personality(user_id)
    finally:
        session.close()
