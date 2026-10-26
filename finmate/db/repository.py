"""
Finmate - Acceso a datos para el orquestador del agente.

Funciones simples de lectura/escritura sobre users, conversation_history,
portfolio_holdings y watchlist_items. Cada función abre y cierra su propia
sesión — a esta escala (un worker, pocos requests concurrentes) es más
simple que manejar sesiones por request.
"""
import logging
from typing import List, Optional, Tuple

from .models import ConversationTurn, PortfolioHolding, User, WatchlistItem, get_session

logger = logging.getLogger(__name__)

# Cuántos turnos previos se le pasan al modelo como contexto. ~6 intercambios
# usuario/agente alcanza para memoria de corto plazo sin inflar el costo de
# tokens en cada mensaje.
MAX_HISTORY_TURNS = 12


def get_or_create_user(phone: str) -> User:
    session = get_session()
    try:
        user = session.query(User).filter_by(phone=phone).one_or_none()
        if user is None:
            user = User(phone=phone)
            session.add(user)
            session.commit()
            session.refresh(user)
            logger.info(f"Nuevo usuario creado: {phone}")
        return user
    finally:
        session.close()


def get_recent_history(user_id: int, limit: int = MAX_HISTORY_TURNS) -> List[Tuple[str, str]]:
    """Devuelve [(role, content), ...] en orden cronológico ascendente."""
    session = get_session()
    try:
        rows = (
            session.query(ConversationTurn)
            .filter_by(user_id=user_id)
            .order_by(ConversationTurn.timestamp.desc())
            .limit(limit)
            .all()
        )
        rows.reverse()
        return [(r.role, r.content) for r in rows]
    finally:
        session.close()


def save_turn(user_id: int, role: str, content: str) -> None:
    session = get_session()
    try:
        session.add(ConversationTurn(user_id=user_id, role=role, content=content))
        session.commit()
    finally:
        session.close()


# ============================================================
# Portafolio (Fase 1)
# ============================================================
def add_or_update_holding(
    user_id: int, symbol: str, quantity: float, avg_cost: Optional[float] = None
) -> Optional[PortfolioHolding]:
    """Suma `quantity` a la posición del usuario en `symbol` (puede ser negativa
    para vender). Si el símbolo no existía y quantity > 0, lo crea. Si la
    posición resultante queda en 0 o menos, se borra la fila y se devuelve None.
    Si se informa avg_cost en una compra (quantity > 0) y ya había una posición
    con costo cargado, se recalcula el costo promedio ponderado.
    """
    session = get_session()
    try:
        symbol = symbol.strip().upper()
        holding = (
            session.query(PortfolioHolding).filter_by(user_id=user_id, symbol=symbol).one_or_none()
        )

        if holding is None:
            if quantity <= 0:
                return None
            holding = PortfolioHolding(
                user_id=user_id, symbol=symbol, quantity=quantity, avg_cost=avg_cost
            )
            session.add(holding)
            session.commit()
            session.refresh(holding)
            return holding

        new_quantity = holding.quantity + quantity
        if new_quantity <= 0:
            session.delete(holding)
            session.commit()
            return None

        if quantity > 0 and avg_cost is not None:
            if holding.avg_cost is not None:
                total_cost = holding.avg_cost * holding.quantity + avg_cost * quantity
                holding.avg_cost = total_cost / new_quantity
            else:
                holding.avg_cost = avg_cost

        holding.quantity = new_quantity
        session.commit()
        session.refresh(holding)
        return holding
    finally:
        session.close()


def remove_holding(user_id: int, symbol: str) -> bool:
    """Borra por completo la posición del usuario en `symbol`. True si había algo que borrar."""
    session = get_session()
    try:
        symbol = symbol.strip().upper()
        holding = (
            session.query(PortfolioHolding).filter_by(user_id=user_id, symbol=symbol).one_or_none()
        )
        if holding is None:
            return False
        session.delete(holding)
        session.commit()
        return True
    finally:
        session.close()


def get_portfolio(user_id: int) -> List[Tuple[str, float, Optional[float]]]:
    """Devuelve [(symbol, quantity, avg_cost), ...] ordenado alfabéticamente."""
    session = get_session()
    try:
        rows = (
            session.query(PortfolioHolding)
            .filter_by(user_id=user_id)
            .order_by(PortfolioHolding.symbol)
            .all()
        )
        return [(r.symbol, r.quantity, r.avg_cost) for r in rows]
    finally:
        session.close()


# ============================================================
# Watchlist (Fase 1)
# ============================================================
def add_to_watchlist(user_id: int, symbol: str, note: Optional[str] = None) -> WatchlistItem:
    """Agrega `symbol` a la watchlist del usuario (o actualiza la nota si ya estaba)."""
    session = get_session()
    try:
        symbol = symbol.strip().upper()
        item = session.query(WatchlistItem).filter_by(user_id=user_id, symbol=symbol).one_or_none()
        if item is not None:
            if note:
                item.note = note
                session.commit()
                session.refresh(item)
            return item
        item = WatchlistItem(user_id=user_id, symbol=symbol, note=note)
        session.add(item)
        session.commit()
        session.refresh(item)
        return item
    finally:
        session.close()


def remove_from_watchlist(user_id: int, symbol: str) -> bool:
    session = get_session()
    try:
        symbol = symbol.strip().upper()
        item = session.query(WatchlistItem).filter_by(user_id=user_id, symbol=symbol).one_or_none()
        if item is None:
            return False
        session.delete(item)
        session.commit()
        return True
    finally:
        session.close()


def get_watchlist(user_id: int) -> List[Tuple[str, Optional[str]]]:
    """Devuelve [(symbol, note), ...] ordenado alfabéticamente."""
    session = get_session()
    try:
        rows = (
            session.query(WatchlistItem)
            .filter_by(user_id=user_id)
            .order_by(WatchlistItem.symbol)
            .all()
        )
        return [(r.symbol, r.note) for r in rows]
    finally:
        session.close()


def get_all_watchlist_entries() -> List[Tuple[int, str, str]]:
    """Devuelve [(user_id, phone, symbol), ...] de TODOS los usuarios con
    watchlist, sin importar a quién pertenece cada ítem. Usado por el chequeo
    periódico de alertas de watchlist (ver finmate/alerts/watchlist_alerts.py),
    separado a propósito de `get_watchlist` (que es por-usuario, para cuando
    el agente responde "mostrame mi watchlist" por chat)."""
    session = get_session()
    try:
        rows = (
            session.query(WatchlistItem.user_id, User.phone, WatchlistItem.symbol)
            .join(User, User.id == WatchlistItem.user_id)
            .all()
        )
        return [(r[0], r[1], r[2]) for r in rows]
    finally:
        session.close()
