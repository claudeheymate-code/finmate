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
    Boolean,
    Column,
    Date,
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
    personality = relationship(
        "PersonalitySettings", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    news_topics = relationship(
        "NewsTopicFollowed", back_populates="user", cascade="all, delete-orphan"
    )
    economic_indicators = relationship(
        "EconomicIndicatorFollowed", back_populates="user", cascade="all, delete-orphan"
    )
    transactions = relationship(
        "Transaction", back_populates="user", cascade="all, delete-orphan"
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


class PersonalitySettings(Base):
    """Configuración de personalidad por usuario (Plan Fase 1)."""

    __tablename__ = "personality_settings"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    humor = Column(Integer, default=5)               # 1-10: 1=serio, 10=muy gracioso
    sarcasmo = Column(Integer, default=3)             # 1-10
    frecuencia_chistes = Column(Integer, default=3)   # 1-10
    nivel_conversador = Column(Integer, default=5)    # 1-10: 1=muy conciso, 10=muy parlanchín
    tono = Column(String(50), default="profesional")  # profesional|casual|amigo
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False
    )

    user = relationship("User", back_populates="personality")


class NewsTopicFollowed(Base):
    """Temas de noticias que el usuario quiere seguir (Plan Fase 4)."""

    __tablename__ = "news_topics_followed"
    __table_args__ = (UniqueConstraint("user_id", "tipo", "valor", name="uq_news_user_tipo_valor"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tipo = Column(String(50), nullable=False)    # ticker | sector | pais | keyword
    valor = Column(String(200), nullable=False)  # AAPL | tecnología | Chile | inflación
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="news_topics")


class EconomicIndicatorFollowed(Base):
    """Indicadores macroeconómicos que el usuario quiere seguir (Plan Fase 4)."""

    __tablename__ = "economic_indicators_followed"
    __table_args__ = (UniqueConstraint("user_id", "indicator_code", name="uq_eco_user_code"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    indicator_code = Column(String(50), nullable=False)  # FED_RATE|CPI_US|NFP|GDP_US|IPC_CL
    country = Column(String(10), default="US")
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="economic_indicators")


class Transaction(Base):
    """Transacción de finanzas personales (Plan Fase 5).
    amount negativo = gasto, positivo = ingreso."""

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)        # negativo=gasto, positivo=ingreso
    category = Column(String(100), nullable=False)
    description = Column(String(500))
    date = Column(DateTime, nullable=False, index=True)
    raw_text = Column(String(500))               # texto original del usuario
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="transactions")


class BudgetCategory(Base):
    """Categoría de presupuesto — globales (user_id=None) o por usuario (Plan Fase 5)."""

    __tablename__ = "budget_categories"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_budget_user_name"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL = globales/default
    name = Column(String(100), nullable=False)
    monthly_limit = Column(Float, nullable=True)  # None = sin límite
    is_default = Column(Boolean, default=False)


class AlertLog(Base):
    """Log de alertas enviadas — reemplaza JSON state files gradualmente (Plan Fase 6)."""

    __tablename__ = "alerts_log"
    __table_args__ = (UniqueConstraint("user_id", "alert_type", "ref_id", name="uq_alert_log"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL = broadcast
    alert_type = Column(String(50), nullable=False)    # watchlist|earnings|macro|news|weekly
    ref_id = Column(String(200), nullable=False)        # ej: "AAPL_2026-10-29"
    sent_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False, index=True)


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
