"""
Finmate - Definición y ejecución de tools para el orquestador.

Fase 0: una sola tool (get_market_data) que reutiliza la lógica de mercados
ya probada en producción. Las tools de portafolio, noticias/económicos y
finanzas personales se agregan en las fases 2 a 5 del plan.
"""
import logging

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
    }
]

# Cache corto: si dos usuarios (o el mismo, dos veces) preguntan "mercados"
# con segundos de diferencia, no hace falta pegarle de nuevo a Finnhub/Alpha
# Vantage. 30s es prudente para no mostrar datos desactualizados.
_MARKET_DATA_CACHE_TTL = 30


def run_tool(name: str, tool_input: dict) -> str:
    if name == "get_market_data":
        return cached("finmate:market_data", _MARKET_DATA_CACHE_TTL, _get_market_data)
    logger.error(f"Tool desconocida solicitada por el modelo: {name}")
    return f"Error interno: la herramienta '{name}' no existe."
