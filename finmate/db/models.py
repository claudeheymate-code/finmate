"""
Finmate - Modelos de base de datos (SQLAlchemy)

Fase 0: `users` y `conversation_history` — lo mínimo para que el agente
tenga memoria persistente entre mensajes.

Fase 1: `portfolio_holdings` y `watchlist_items` — el agente puede manejar
el portafolio y la watchlist del usuario por chat (sumar/restar posiciones,
seguir activos sin tenerlos). `transactions` (historial detallado de compras/
ventas) queda para una fase posterior; por ahora `portfolio_holdings` solo
guarda la posición neta actual por símbolo.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from config.settings import DATABASE_URL


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    # Número de WhatsApp tal como lo entrega Twilio, ej: "whatsapp:+56912345678"
    phone = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=True)
    timezone = Column(String(64), nullable=False, default="America/Santiago")
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    conversation_turns = relationship(
        "ConversationTurn", back_populates="user", cascade="all, delete-orphan"
    )
    portfolio_holdings = relationship(
        "PortfolioHolding", back_populates="user", cascade="all, delete-orphan"
    )
    watchlist_items = relationship(
        "WatchlistItem", back_populates="user", cascade="all, delete-orphan"
    )


class ConversationTurn(Base):
    __tablename__ = "conversation_history"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(16), nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, nullable=False, index=True)

    user = relationship("User", back_populates="conversation_turns")


class PortfolioHolding(Base):
    """Posición neta actual de un usuario en un símbolo (Fase 1).

    No es un libro de transacciones: cada fila es "cuánto tengo ahora" de
    un ticker. `avg_cost` es opcional (precio promedio de compra) y se usa
    solo para calcular ganancia/pérdida cuando el usuario lo informó.
    """

    __tablename__ = "portfolio_holdings"
    __table_args__ = (UniqueConstraint("user_id", "symbol", name="uq_portfolio_user_symbol"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String(16), nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    avg_cost = Column(Float, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False
    )

    user = relationship("User", back_populates="portfolio_holdings")


class WatchlistItem(Base):
    """Activo que el usuario sigue sin tenerlo (necesariamente) en el portafolio."""

    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("user_id", "symbol", name="uq_watchlist_user_symbol"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String(16), nullable=False, index=True)
    note = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="watchlist_items")


# ============================================================
# Engine / sesión
# ============================================================
# El engine se crea de forma perezosa (recién cuando se usa) y no al
# importar el módulo: así, si todavía no se configuró DATABASE_URL (p. ej.
# antes de provisionar Neon), la app entera no se cae al arrancar — el
# error queda contenido a los try/except de main.py y del orquestador.
#
# pool_pre_ping evita errores por conexiones que Neon/Railway cierran por
# inactividad; el pool se mantiene chico porque es un solo worker de gunicorn.
_engine = None
_SessionLocal = None


def _ensure_engine() -> None:
    global _engine, _SessionLocal
    if _engine is None:
        if not DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL no está configurada — provisioná Postgres "
                "(ver plan, decisión 02) y agregá la variable en Railway."
            )
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def init_db() -> None:
    """Crea las tablas si no existen. Alcanza para Fase 0 (sin Alembic todavía)."""
    _ensure_engine()
    Base.metadata.create_all(bind=_engine)


def get_session() -> Session:
    _ensure_engine()
    return _SessionLocal()
