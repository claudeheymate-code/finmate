"""Repositorio de finanzas personales: transacciones y categorías de presupuesto (Plan Fase 5)."""
import datetime as dt
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Categorías de gasto por defecto (definidas por Joaco el 16 nov 2026).
# Cada usuario puede sacar las que no use y agregar las suyas (solo para su
# cuenta). "Otros" siempre está disponible para lo que no encaje en ninguna y
# para los ingresos; no se puede sacar.
DEFAULT_CATEGORIES = [
    "Comidas", "Carretes", "Asados", "Regalos", "Suscripciones", "Polola", "Copete", "Bets",
]
FALLBACK_CATEGORY = "Otros"
MAX_CUSTOM_CATEGORIES = 20
MAX_CATEGORY_LEN = 30


def ensure_default_categories() -> None:
    """Crea las categorías globales por defecto si no existen."""
    try:
        from finmate.db.models import BudgetCategory, get_session
    except Exception:
        return

    session = get_session()
    try:
        wanted = DEFAULT_CATEGORIES + [FALLBACK_CATEGORY]
        for name in wanted:
            existing = session.query(BudgetCategory).filter_by(
                user_id=None, name=name
            ).first()
            if not existing:
                session.add(BudgetCategory(user_id=None, name=name, is_default=True))
        # Las globales que ya no están en la lista se borran (los gastos viejos
        # guardan el nombre como texto, así que no se pierde nada).
        for c in session.query(BudgetCategory).filter_by(user_id=None).all():
            if c.name not in wanted:
                session.delete(c)
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


def clean_category_name(raw) -> str:
    """Normaliza el nombre de una categoría nueva: sin espacios de más y con
    la primera letra en mayúscula ("  bencina " -> "Bencina")."""
    name = " ".join(str(raw or "").split())[:MAX_CATEGORY_LEN]
    return name[:1].upper() + name[1:] if name else ""


def _same(a: str, b: str) -> bool:
    return (a or "").casefold() == (b or "").casefold()


def category_settings(user_id: int) -> List[dict]:
    """Todas las categorías que el usuario puede ver en Ajustes de gastos:
    [{"name", "default": bool, "active": bool}] — primero las por defecto
    (activas o no), después las propias, y al final "Otros"."""
    from finmate.db.models import BudgetCategory, HiddenCategory, get_session

    session = get_session()
    try:
        hidden = {h.name for h in session.query(HiddenCategory).filter_by(user_id=user_id)}
        custom = [c.name for c in session.query(BudgetCategory)
                  .filter_by(user_id=user_id).order_by(BudgetCategory.id)]
    except Exception as e:
        logger.error(f"Error leyendo categorías del usuario: {e}")
        hidden, custom = set(), []
    finally:
        session.close()
    out = [{"name": n, "default": True, "active": n not in hidden} for n in DEFAULT_CATEGORIES]
    out += [{"name": n, "default": False, "active": True} for n in custom
            if not any(_same(n, d) for d in DEFAULT_CATEGORIES + [FALLBACK_CATEGORY])]
    out.append({"name": FALLBACK_CATEGORY, "default": True, "active": True, "fixed": True})
    return out


def get_categories(user_id: int) -> List[str]:
    """Categorías que el usuario puede usar hoy (las por defecto que no sacó,
    las propias y "Otros" al final)."""
    try:
        return [c["name"] for c in category_settings(user_id) if c["active"]]
    except Exception as e:
        logger.error(f"Error leyendo categorías: {e}")
        return DEFAULT_CATEGORIES + [FALLBACK_CATEGORY]


def resolve_category(user_id: int, raw: str) -> Optional[str]:
    """Devuelve el nombre exacto de una categoría activa del usuario que
    coincida con raw (sin importar mayúsculas), o None."""
    for c in get_categories(user_id):
        if _same(c, (raw or "").strip()):
            return c
    return None


def add_user_category(user_id: int, raw_name: str) -> Tuple[bool, str]:
    """Agrega una categoría propia (o reactiva una por defecto que el usuario
    había sacado). Devuelve (ok, mensaje_o_nombre)."""
    from finmate.db.models import BudgetCategory, HiddenCategory, get_session

    name = clean_category_name(raw_name)
    if len(name) < 2:
        return False, "Escribe un nombre de al menos 2 letras."
    session = get_session()
    try:
        for d in DEFAULT_CATEGORIES + [FALLBACK_CATEGORY]:
            if _same(d, name):
                h = session.query(HiddenCategory).filter_by(user_id=user_id, name=d).one_or_none()
                if h is None:
                    return False, f"{d} ya está en tu lista."
                session.delete(h); session.commit()
                return True, d
        custom = session.query(BudgetCategory).filter_by(user_id=user_id).all()
        if any(_same(c.name, name) for c in custom):
            return False, f"{name} ya está en tu lista."
        if len(custom) >= MAX_CUSTOM_CATEGORIES:
            return False, f"Puedes tener hasta {MAX_CUSTOM_CATEGORIES} categorías propias."
        session.add(BudgetCategory(user_id=user_id, name=name, is_default=False))
        session.commit()
        return True, name
    except Exception as e:
        session.rollback()
        logger.error(f"Error agregando categoría: {e}")
        return False, "No se pudo guardar la categoría."
    finally:
        session.close()


def set_category_active(user_id: int, name: str, active: bool) -> bool:
    """Saca o vuelve a poner una categoría. Las por defecto se ocultan (se
    pueden reactivar); las propias se borran. "Otros" no se puede sacar.
    Los gastos ya registrados no se tocan."""
    from finmate.db.models import BudgetCategory, HiddenCategory, get_session

    if _same(name, FALLBACK_CATEGORY):
        return False
    session = get_session()
    try:
        default = next((d for d in DEFAULT_CATEGORIES if _same(d, name)), None)
        if default:
            h = session.query(HiddenCategory).filter_by(user_id=user_id, name=default).one_or_none()
            if active and h is not None:
                session.delete(h)
            elif not active and h is None:
                session.add(HiddenCategory(user_id=user_id, name=default))
            session.commit()
            return True
        if active:
            return add_user_category(user_id, name)[0]
        c = next((c for c in session.query(BudgetCategory).filter_by(user_id=user_id)
                  if _same(c.name, name)), None)
        if c is None:
            return False
        session.delete(c); session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error cambiando categoría: {e}")
        return False
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


def range_breakdown(user_id: int, start: dt.datetime, end: dt.datetime) -> dict:
    """Gastos por categoría entre start (incluido) y end (excluido).

    {"total_gastos", "total_ingresos", "count", "categories": [{"name", "amount", "pct"}]}
    Aparecen todas las categorías activas del usuario (aunque estén en 0) y,
    además, cualquier otra que tenga gastos en el período (por ejemplo una que
    el usuario sacó después de usarla), para que el total siempre cuadre.
    """
    from finmate.db.models import Transaction, get_session

    session = get_session()
    try:
        rows = session.query(Transaction).filter(
            Transaction.user_id == user_id, Transaction.date >= start, Transaction.date < end,
        ).all()
    finally:
        session.close()
    amounts = {c: 0.0 for c in get_categories(user_id)}
    gastos = ingresos = 0.0
    count = 0
    for t in rows:
        if t.amount < 0:
            amounts[t.category] = amounts.get(t.category, 0.0) + abs(t.amount)
            gastos += abs(t.amount); count += 1
        else:
            ingresos += t.amount
    # "Otros" siempre al final
    if FALLBACK_CATEGORY in amounts:
        amounts[FALLBACK_CATEGORY] = amounts.pop(FALLBACK_CATEGORY)
    return {
        "total_gastos": gastos,
        "total_ingresos": ingresos,
        "count": count,
        "categories": [
            {"name": c, "amount": a, "pct": (a / gastos * 100) if gastos else 0.0}
            for c, a in amounts.items()
        ],
    }


def month_breakdown(user_id: int, year: int, month: int) -> dict:
    """Gastos del mes por categoría (ver range_breakdown) más year/month."""
    start, end = _month_bounds(year, month)
    return {"year": year, "month": month, **range_breakdown(user_id, start, end)}


def year_to_date_breakdown(user_id: int, year: int, month: int) -> dict:
    """Gastos desde el 1 de enero hasta el fin del mes indicado."""
    _, end = _month_bounds(year, month)
    return {"year": year, "month": month, **range_breakdown(user_id, dt.datetime(year, 1, 1), end)}


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
