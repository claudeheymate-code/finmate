"""Repositorio de finanzas personales: transacciones y categorías de presupuesto (Plan Fase 5)."""
import datetime as dt
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Categorías de gasto (definidas por Joaco el 16 nov 2026 para el panel web).
# "Otros" queda para lo que no encaje en ninguna.
DEFAULT_CATEGORIES = [
    "Evento Social", "Polola", "Copete", "Comidas", "Regalos", "Viajes", "Otros"
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
    occasion: Optional[str] = None,
    merchant: Optional[str] = None,
    receipt_url: Optional[str] = None,
):
    """Agrega una transacción. amount negativo = gasto, positivo = ingreso."""
    from finmate.db.models import Transaction, get_session

    if isinstance(date, dt.date) and not isinstance(date, dt.datetime):
        date = dt.datetime(date.year, date.month, date.day, 12, 0)

    session = get_session()
    try:
        txn = Transaction(
            user_id=user_id,
            amount=amount,
            category=category,
            description=description,
            date=date or dt.datetime.utcnow(),
            raw_text=raw_text,
            occasion=occasion or None,
            merchant=merchant or None,
            receipt_url=receipt_url or None,
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


# ============================================================
# Panel web (etapa 1): listados, desglose por mes y edición
# ============================================================
def _month_bounds(year: int, month: int):
    start = dt.datetime(year, month, 1)
    end = dt.datetime(year + 1, 1, 1) if month == 12 else dt.datetime(year, month + 1, 1)
    return start, end


def previous_month(year: int, month: int) -> Tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def tx_to_dict(t) -> dict:
    return {
        "id": t.id,
        "amount": t.amount,
        "tipo": "ingreso" if t.amount >= 0 else "gasto",
        "category": t.category,
        "description": t.description or "",
        "occasion": t.occasion or "",
        "merchant": t.merchant or "",
        "receipt_url": t.receipt_url or "",
        "has_receipt": bool(t.receipt_url),
        "date": t.date.date().isoformat() if t.date else None,
    }


def list_transactions(
    user_id: int, year: int, month: int, category: Optional[str] = None
) -> List[dict]:
    """Movimientos del mes (más nuevos primero), opcionalmente de una categoría."""
    from finmate.db.models import Transaction, get_session

    start, end = _month_bounds(year, month)
    session = get_session()
    try:
        q = session.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.date >= start,
            Transaction.date < end,
        )
        if category:
            q = q.filter(Transaction.category == category)
        rows = q.order_by(Transaction.date.desc(), Transaction.id.desc()).all()
        return [tx_to_dict(t) for t in rows]
    finally:
        session.close()


def month_breakdown(user_id: int, year: int, month: int) -> dict:
    """Gastos del mes por categoría, en el orden de DEFAULT_CATEGORIES.

    {"year", "month", "total_gastos", "total_ingresos", "count",
     "categories": [{"name", "amount", "pct"}]}
    Las categorías viejas o desconocidas se suman en "Otros".
    """
    ingresos, gastos, por_cat = get_monthly_summary(user_id, year, month)
    amounts = {c: 0.0 for c in DEFAULT_CATEGORIES}
    for cat, amount in por_cat.items():
        key = cat if cat in amounts else "Otros"
        amounts[key] += amount
    count = sum(1 for t in list_transactions(user_id, year, month) if t["amount"] < 0)
    return {
        "year": year,
        "month": month,
        "total_gastos": gastos,
        "total_ingresos": ingresos,
        "count": count,
        "categories": [
            {"name": c, "amount": a, "pct": (a / gastos * 100) if gastos else 0.0}
            for c, a in amounts.items()
        ],
    }


def update_transaction(user_id: int, tx_id: int, **fields) -> Optional[dict]:
    """Edita categoría, ocasión, descripción o comercio de un movimiento propio.
    Devuelve el movimiento actualizado o None si no existe o es de otro usuario."""
    from finmate.db.models import Transaction, get_session

    allowed = {"category", "occasion", "description", "merchant"}
    session = get_session()
    try:
        t = session.query(Transaction).filter_by(id=tx_id, user_id=user_id).one_or_none()
        if t is None:
            return None
        for k, v in fields.items():
            if k in allowed and v is not None:
                setattr(t, k, v)
        session.commit()
        session.refresh(t)
        return tx_to_dict(t)
    finally:
        session.close()


def delete_transaction(user_id: int, tx_id: int) -> bool:
    from finmate.db.models import Transaction, get_session

    session = get_session()
    try:
        t = session.query(Transaction).filter_by(id=tx_id, user_id=user_id).one_or_none()
        if t is None:
            return False
        session.delete(t)
        session.commit()
        return True
    finally:
        session.close()
