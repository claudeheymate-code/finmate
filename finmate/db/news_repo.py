"""Repositorio de temas de noticias e indicadores económicos seguidos (Plan Fase 4)."""
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


def get_news_topics(user_id: int) -> List[Tuple[str, str]]:
    """Devuelve [(tipo, valor), ...] de los temas que sigue el usuario."""
    try:
        from finmate.db.models import NewsTopicFollowed, get_session
    except Exception:
        return []

    session = get_session()
    try:
        rows = session.query(NewsTopicFollowed).filter_by(user_id=user_id).all()
        return [(r.tipo, r.valor) for r in rows]
    except Exception as e:
        logger.error(f"Error leyendo news topics de user {user_id}: {e}")
        return []
    finally:
        session.close()


def add_news_topic(user_id: int, tipo: str, valor: str) -> bool:
    """Agrega un tema. Devuelve True si se agregó, False si ya existía."""
    try:
        from finmate.db.models import NewsTopicFollowed, get_session
    except Exception:
        return False

    session = get_session()
    try:
        existing = session.query(NewsTopicFollowed).filter_by(
            user_id=user_id, tipo=tipo, valor=valor
        ).first()
        if existing:
            return False
        session.add(NewsTopicFollowed(user_id=user_id, tipo=tipo, valor=valor))
        session.commit()
        return True
    except Exception as e:
        logger.error(f"Error agregando news topic: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def remove_news_topic(user_id: int, tipo: str, valor: str) -> bool:
    """Quita un tema. Devuelve True si existía y se quitó."""
    try:
        from finmate.db.models import NewsTopicFollowed, get_session
    except Exception:
        return False

    session = get_session()
    try:
        row = session.query(NewsTopicFollowed).filter_by(
            user_id=user_id, tipo=tipo, valor=valor
        ).first()
        if not row:
            return False
        session.delete(row)
        session.commit()
        return True
    except Exception as e:
        logger.error(f"Error removiendo news topic: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def get_economic_indicators(user_id: int) -> List[str]:
    """Devuelve [indicator_code, ...] de los indicadores macro que sigue el usuario."""
    try:
        from finmate.db.models import EconomicIndicatorFollowed, get_session
    except Exception:
        return []

    session = get_session()
    try:
        rows = session.query(EconomicIndicatorFollowed).filter_by(user_id=user_id).all()
        return [r.indicator_code for r in rows]
    except Exception as e:
        logger.error(f"Error leyendo indicadores de user {user_id}: {e}")
        return []
    finally:
        session.close()


def add_economic_indicator(user_id: int, indicator_code: str, country: str = "US") -> bool:
    """Agrega un indicador. Devuelve True si se agregó, False si ya existía."""
    try:
        from finmate.db.models import EconomicIndicatorFollowed, get_session
    except Exception:
        return False

    session = get_session()
    try:
        existing = session.query(EconomicIndicatorFollowed).filter_by(
            user_id=user_id, indicator_code=indicator_code
        ).first()
        if existing:
            return False
        session.add(EconomicIndicatorFollowed(
            user_id=user_id, indicator_code=indicator_code, country=country
        ))
        session.commit()
        return True
    except Exception as e:
        logger.error(f"Error agregando indicador económico: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def remove_economic_indicator(user_id: int, indicator_code: str) -> bool:
    """Quita un indicador. Devuelve True si existía y se quitó."""
    try:
        from finmate.db.models import EconomicIndicatorFollowed, get_session
    except Exception:
        return False

    session = get_session()
    try:
        row = session.query(EconomicIndicatorFollowed).filter_by(
            user_id=user_id, indicator_code=indicator_code
        ).first()
        if not row:
            return False
        session.delete(row)
        session.commit()
        return True
    except Exception as e:
        logger.error(f"Error removiendo indicador: {e}")
        session.rollback()
        return False
    finally:
        session.close()
