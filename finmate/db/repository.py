"""
Finmate - Acceso a datos para el orquestador del agente.

Funciones simples de lectura/escritura sobre users y conversation_history.
Cada función abre y cierra su propia sesión — a esta escala (un worker,
pocos requests concurrentes) es más simple que manejar sesiones por request.
"""
import logging
from typing import List, Tuple

from .models import ConversationTurn, User, get_session

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
