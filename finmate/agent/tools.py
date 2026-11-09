"""
Finmate - Definición y ejecución de tools para el orquestador.

Fase 0: get_market_data, que reutiliza la lógica de mercados ya probada en
producción.

Fase 1: tools de portafolio y watchlist (finmate/agent/portfolio_tools.py).
A diferencia de get_market_data, estas tools son por-usuario, así que
run_tool ahora recibe un user_id que se propaga desde el orquestador
(finmate/agent/orchestrator.py -> handle_message). Noticias/económicos y
finanzas personales más avanzadas quedan para fases siguientes del plan.

Fase 1.6: get_pending_notifications, para entregar el contenido real de
los avisos que el bot mandó como Content Template corto (resumen semanal,
alertas de mercado — ver finmate/alerts/pending.py y
finmate/alerts/engine.py). A diferencia de las tools de Fase 1, esta es
por-teléfono y no por user_id (la cola de pendientes vive por número de
WhatsApp, igual que WHATSAPP_RECIPIENTS), así que run_tool también recibe
un `phone` propagado desde el orquestador.
"""
import logging
from typing import Optional

from finmate.agent.finance_tools import (
    tool_add_expense,
    tool_get_monthly_summary,
    tool_get_recent_transactions,
)
from finmate.agent.market_tools import tool_explain_movement
from finmate.agent.news_tools import (
    tool_follow_indicator,
    tool_follow_news_topic,
    tool_get_economic_calendar,
    tool_get_my_news_topics,
    tool_unfollow_indicator,
    tool_unfollow_news_topic,
)
from finmate.agent.personality_tools import tool_get_personality, tool_set_personality
from finmate.agent.portfolio_tools import (
    tool_add_to_portfolio,
    tool_add_to_watchlist,
    tool_get_portfolio,
    tool_get_watchlist,
    tool_remove_from_portfolio,
    tool_remove_from_watchlist,
)
from finmate.alerts.pending import pop_pending
from finmate.db.cache import cached
from finmate.whatsapp.webhook import _get_market_data

logger = logging.getLogger(__name__)

TOOLS = [
    {
        "name": "get_market_data",
        "description": (
            "Obtiene el estado actual de los principales índices bursátiles "
            "(S&P 500, Dow Jones, Nasdaq 100), commodities (oro, plata) y el "
            "tipo de cambio USD/CLP, con su variación del día. Usar cuando "
            "el usuario pregunte por el estado de los mercados, los índices, "
            "o cómo están las bolsas hoy."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_portfolio",
        "description": (
            "Muestra el portafolio actual del usuario: cada activo, cantidad, "
            "precio actual, valor total y ganancia/pérdida (si cargó el costo "
            "promedio de compra). Usar cuando el usuario pregunte por su "
            "portafolio, sus inversiones, cuánto tiene, o cómo le está yendo."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_to_portfolio",
        "description": (
            "Agrega (o suma cantidad a) un activo en el portafolio del usuario. "
            "Usar cuando diga que compró algo o quiera cargar una posición que "
            "ya tiene. Si no da el precio de compra, se puede omitir avg_cost."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Ticker del activo, ej: AAPL, NVDA, SPY",
                },
                "quantity": {
                    "type": "number",
                    "description": "Cantidad de unidades/acciones a agregar",
                },
                "avg_cost": {
                    "type": "number",
                    "description": "Precio promedio de compra por unidad, si lo sabe (opcional)",
                },
            },
            "required": ["symbol", "quantity"],
        },
    },
    {
        "name": "remove_from_portfolio",
        "description": (
            "Quita (o resta cantidad de) un activo del portafolio del usuario. "
            "Usar cuando diga que vendió algo. Si no da cantidad, se quita el "
            "activo por completo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker del activo"},
                "quantity": {
                    "type": "number",
                    "description": "Cantidad a quitar (opcional; si se omite, se quita todo)",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_watchlist",
        "description": (
            "Muestra la watchlist del usuario: activos que sigue sin tenerlos "
            "necesariamente en el portafolio, con su precio actual. Usar cuando "
            "pregunte qué está siguiendo o por el estado de su watchlist."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_to_watchlist",
        "description": (
            "Agrega un activo a la watchlist del usuario, para seguirlo sin "
            "cargarlo como posición de portafolio. Usar cuando diga 'seguime a "
            "X' o 'quiero ver cómo le va a X'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker del activo"},
                "note": {
                    "type": "string",
                    "description": "Nota opcional sobre por qué lo sigue",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "remove_from_watchlist",
        "description": "Quita un activo de la watchlist del usuario.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker del activo"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_pending_notifications",
        "description": (
            "Entrega el contenido completo de avisos de Finmate que quedaron "
            "pendientes (resumen semanal, alertas de resultados corporativos, "
            "datos macro o noticias). Usar cuando el usuario responda a un "
            "aviso corto de Finmate tipo 'tenés novedades de mercado' o 'tu "
            "resumen semanal está listo' con algo afirmativo (ej: 'sí', "
            "'dale', 'mostrame', 'ver', 'mandalo', 'quiero verlo'). Si no hay "
            "nada pendiente, la tool lo informa — no hace falta preguntarle "
            "al usuario antes de llamarla."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    # ── Finanzas personales (Plan Fase 5) ──────────────────────────────────
    {
        "name": "add_expense",
        "description": "Registra un gasto o ingreso personal. Usar cuando el usuario diga algo como 'gasté X en Y', 'pagué X', 'cobré X', 'ingresé X'. Extraé el monto (negativo para gasto, positivo para ingreso), la categoría y una descripción corta.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo":        {"type": "string",  "enum": ["gasto", "ingreso"], "description": "gasto (gasté, pagué, compré) o ingreso (cobré, me pagaron, ingresé)"},
                "amount":      {"type": "number",  "description": "Monto — negativo para gasto, positivo para ingreso"},
                "category":    {"type": "string",  "description": "Categoría: Vivienda|Alimentación|Transporte|Ocio|Salud|Educación|Otros"},
                "description": {"type": "string",  "description": "Descripción corta (ej: almuerzo, uber, netflix)"},
                "date_str":    {"type": "string",  "description": "Fecha YYYY-MM-DD (opcional, default hoy)"},
                "raw_text":    {"type": "string",  "description": "Texto original del usuario (opcional)"},
            },
            "required": ["tipo", "amount", "category", "description"],
        },
    },
    {
        "name": "get_monthly_summary",
        "description": "Muestra el resumen de ingresos y gastos del mes. Usar cuando el usuario pregunte 'cuánto gasté este mes', 'cómo van mis finanzas', 'resumen de gastos'. Si no indica mes, usar el mes actual.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year":  {"type": "integer", "description": "Año (opcional, default año actual)"},
                "month": {"type": "integer", "description": "Mes 1-12 (opcional, default mes actual)"},
            },
        },
    },
    {
        "name": "get_recent_transactions",
        "description": "Muestra los últimos movimientos registrados. Usar cuando el usuario pregunte por sus últimas transacciones o historial reciente.",
        "input_schema": {"type": "object", "properties": {}},
    },
    # ── Noticias e indicadores económicos (Plan Fase 4) ────────────────────
    {
        "name": "get_my_news_topics",
        "description": "Muestra los temas de noticias e indicadores económicos que el usuario está siguiendo. Usar cuando pregunte qué está siguiendo o quiera ver su configuración de alertas.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "follow_news_topic",
        "description": "Agrega un tema de noticias para seguir. Usar cuando el usuario diga 'seguime las noticias de X', 'avisame sobre X'. Tipos: ticker (ej: AAPL), sector (ej: tecnología), pais (ej: Chile), keyword (ej: inflación).",
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo":  {"type": "string", "description": "ticker|sector|pais|keyword"},
                "valor": {"type": "string", "description": "El valor a seguir"},
            },
            "required": ["tipo", "valor"],
        },
    },
    {
        "name": "unfollow_news_topic",
        "description": "Quita un tema de noticias. Usar cuando el usuario quiera dejar de recibir noticias sobre algo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo":  {"type": "string", "description": "ticker|sector|pais|keyword"},
                "valor": {"type": "string", "description": "El valor a quitar"},
            },
            "required": ["tipo", "valor"],
        },
    },
    {
        "name": "get_economic_calendar",
        "description": "Muestra el calendario de indicadores económicos del usuario o el catálogo completo. Usar cuando pregunte por indicadores macro, datos económicos, o el calendario.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "follow_indicator",
        "description": "Agrega un indicador económico macro para seguir. Usar cuando el usuario diga 'seguime el CPI', 'avisame del NFP', etc. Códigos: FED_RATE, CPI_US, NFP, GDP_US, PCE_US, IPC_CL, BCCh_RATE, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator_code": {"type": "string", "description": "Código del indicador (ej: CPI_US, NFP, FED_RATE)"},
            },
            "required": ["indicator_code"],
        },
    },
    {
        "name": "unfollow_indicator",
        "description": "Quita un indicador económico de los seguimientos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator_code": {"type": "string", "description": "Código del indicador a quitar"},
            },
            "required": ["indicator_code"],
        },
    },
    # ── Explicar movimiento de mercado (Plan Fase 2) ───────────────────────
    {
        "name": "explain_movement",
        "description": "Explica el movimiento reciente de un activo: precio, variación del día y noticias relacionadas. Usar cuando el usuario pregunte 'por qué se movió X', 'qué pasó con AAPL', 'explicame el movimiento de Tesla'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker del activo (ej: AAPL, NVDA, BTC-USD)"},
            },
            "required": ["symbol"],
        },
    },
    # ── Personalidad (Plan Fase 1) ─────────────────────────────────────────
    {
        "name": "get_personality",
        "description": "Muestra la configuración de personalidad actual de Finmate para este usuario: humor, sarcasmo, frecuencia de chistes, nivel conversador y tono. Usar cuando el usuario pregunte cómo configuró el bot o quiera ver su perfil de personalidad.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_personality",
        "description": "Cambia uno o más parámetros de personalidad de Finmate para este usuario. Usar cuando diga 'poneme más humor', 'quiero que seas más gracioso', 'cambié el tono a casual', etc. Parámetros: humor (1-10), sarcasmo (1-10), frecuencia_chistes (1-10), nivel_conversador (1-10), tono (profesional|casual|amigo).",
        "input_schema": {
            "type": "object",
            "properties": {
                "humor": {"type": "integer", "minimum": 1, "maximum": 10},
                "sarcasmo": {"type": "integer", "minimum": 1, "maximum": 10},
                "frecuencia_chistes": {"type": "integer", "minimum": 1, "maximum": 10},
                "nivel_conversador": {"type": "integer", "minimum": 1, "maximum": 10},
                "tono": {"type": "string", "enum": ["profesional", "casual", "amigo"]},
            },
        },
    },
]

# Cache corto: si dos usuarios (o el mismo, dos veces) preguntan "mercados"
# con segundos de diferencia, no hace falta pegarle de nuevo a Finnhub/Alpha
# Vantage. 30s es prudente para no mostrar datos desactualizados.
_MARKET_DATA_CACHE_TTL = 30

# Tools que operan sobre datos del usuario (necesitan user_id).
_USER_SCOPED_TOOLS = {
    "get_portfolio": lambda user_id, _input: tool_get_portfolio(user_id),
    "add_to_portfolio": tool_add_to_portfolio,
    "remove_from_portfolio": tool_remove_from_portfolio,
    "get_watchlist": lambda user_id, _input: tool_get_watchlist(user_id),
    "add_to_watchlist": tool_add_to_watchlist,
    "remove_from_watchlist": tool_remove_from_watchlist,
    "get_personality":           lambda user_id, _input: tool_get_personality(user_id),
    "set_personality":           tool_set_personality,
    # Finanzas personales
    "add_expense":               tool_add_expense,
    "get_monthly_summary":       tool_get_monthly_summary,
    "get_recent_transactions":   lambda user_id, _input: tool_get_recent_transactions(user_id),
    # Noticias e indicadores
    "get_my_news_topics":        lambda user_id, _input: tool_get_my_news_topics(user_id),
    "follow_news_topic":         tool_follow_news_topic,
    "unfollow_news_topic":       tool_unfollow_news_topic,
    "get_economic_calendar":     lambda user_id, _input: tool_get_economic_calendar(user_id),
    "follow_indicator":          tool_follow_indicator,
    "unfollow_indicator":        tool_unfollow_indicator,
}

# Tools que operan sobre el teléfono crudo, no sobre el user_id de la DB
# (Fase 1.6: la cola de notificaciones pendientes vive por número de
# WhatsApp — ver finmate/alerts/pending.py).
_PHONE_SCOPED_TOOLS = {
    "get_pending_notifications": lambda phone, _input: (
        pop_pending(phone) or "No tenés avisos pendientes en este momento."
    ),
}


def run_tool(
    name: str, tool_input: dict, user_id: Optional[int] = None, phone: Optional[str] = None
) -> str:
    if name == "get_market_data":
        return cached("finmate:market_data", _MARKET_DATA_CACHE_TTL, _get_market_data)

    if name == "explain_movement":
        return tool_explain_movement(tool_input)

    if name in _USER_SCOPED_TOOLS:
        if user_id is None:
            logger.error(f"Tool {name} llamada sin user_id")
            return "Error interno: no pude identificar al usuario para esta operación."
        return _USER_SCOPED_TOOLS[name](user_id, tool_input)

    if name in _PHONE_SCOPED_TOOLS:
        if phone is None:
            logger.error(f"Tool {name} llamada sin phone")
            return "Error interno: no pude identificar al usuario para esta operación."
        return _PHONE_SCOPED_TOOLS[name](phone, tool_input)

    logger.error(f"Tool desconocida solicitada por el modelo: {name}")
    return f"Error interno: la herramienta '{name}' no existe."
