"""Repositorio de finanzas personales: transacciones y categorías de presupuesto (Plan Fase 5)."""
import datetime as dt
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_CATEGORIES = [
    "Vivienda", "Alimentación", "Transporte", "Ocio", "Salud", "Educación", "Otros"
]


def ensure_default_categories() -> None:
    """Crea las categorías globales por defecto si no existen."""
    try:
        from finmate.db.models import BudgetCategory, get_session
    except Exception:
        return

    session = get_session()
    try:
        for name in DEFAULT_CATEGORIES:
            existing = session.query(BudgetCategory).filter_by(
                user_id=None, name=name
            ).first()
            if not existing:
                session.add(BudgetCategory(user_id=None, name=name, is_default=True))
        session.commit()
    except Exception as e:
        logger.error(f"Error creando categorías default: {e}")
        session.rollback()
    finally:
        session.close()


def add_transaction(
    user_id: int,
    amount: float,
    category: str,
    description: str,
    date: Optional[dt.datetime] = None,
    raw_text: str = "",
):
    """Agrega una transacción. amount negativo = gasto, positivo = ingreso."""
    from finmate.db.models import Transaction, get_session

    session = get_session()
    try:
        txn = Transaction(
            user_id=user_id,
            amount=amount,
            category=category,
            description=description,
            date=date or dt.datetime.utcnow(),
            raw_text=raw_text,
        )
        session.add(txn)
        session.commit()
        session.refresh(txn)
        return txn
    except Exception as e:
        logger.error(f"Error guardando transacción: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def get_monthly_summary(
    user_id: int, year: int, month: int
) -> Tuple[float, float, dict]:
    """Devuelve (total_ingresos, total_gastos, gastos_por_categoria) del mes."""
    try:
        from finmate.db.models import Transaction, get_session
    except Exception:
        return 0.0, 0.0, {}

    session = get_session()
    try:
        start = dt.datetime(year, month, 1)
        end = dt.datetime(year + 1, 1, 1) if month == 12 else dt.datetime(year, month + 1, 1)
        txns = session.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.date >= start,
            Transaction.date < end,
        ).all()
        ingresos = sum(t.amount for t in txns if t.amount > 0)
        gastos = sum(abs(t.amount) for t in txns if t.amount < 0)
        por_categoria: dict = {}
        for t in txns:
            if t.amount < 0:
                por_categoria[t.category] = por_categoria.get(t.category, 0) + abs(t.amount)
        return ingresos, gastos, por_categoria
    except Exception as e:
        logger.error(f"Error en resumen mensual: {e}")
        return 0.0, 0.0, {}
    finally:
        session.close()


def get_recent_transactions(user_id: int, limit: int = 10) -> list:
    """Devuelve las últimas N transacciones del usuario."""
    try:
        from finmate.db.models import Transaction, get_session
    except Exception:
        return []

    session = get_session()
    try:
        return (
            session.query(Transaction)
            .filter_by(user_id=user_id)
            .order_by(Transaction.date.desc())
            .limit(limit)
            .all()
        )
    except Exception as e:
        logger.error(f"Error leyendo transacciones: {e}")
        return []
    finally:
        session.close()


def get_categories(user_id: int) -> List[str]:
    """Devuelve las categorías disponibles para el usuario (globales + las propias)."""
    try:
        from finmate.db.models import BudgetCategory, get_session
    except Exception:
        return list(DEFAULT_CATEGORIES)

    session = get_session()
    try:
        defaults = session.query(BudgetCategory).filter_by(user_id=None).all()
        custom = session.query(BudgetCategory).filter_by(user_id=user_id).all()
        default_names = {c.name for c in defaults}
        all_cats = [c.name for c in defaults] + [
            c.name for c in custom if c.name not in default_names
        ]
        return all_cats if all_cats else list(DEFAULT_CATEGORIES)
    except Exception as e:
        logger.error(f"Error leyendo categorías: {e}")
        return list(DEFAULT_CATEGORIES)
    finally:
        session.close()
