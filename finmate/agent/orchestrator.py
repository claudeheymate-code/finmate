"""
Finmate - Orquestador del agente (Fase 0)

Reemplaza el router de comandos fijos (if/elif por palabra exacta) del
webhook anterior: Claude recibe el mensaje + historial + las tools
disponibles, y decide él mismo si responde directo o si necesita llamar
a una herramienta antes de contestar.

Enrutado económico (decisión 01 del plan): Haiku por defecto, Sonnet para
mensajes que piden un análisis más profundo. Con una sola tool (mercados)
la diferencia todavía no es enorme, pero el hook queda listo para cuando
se sumen portafolio y datos económicos en las próximas fases.
"""
import logging

import anthropic

from config.settings import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL_ANALYSIS,
    ANTHROPIC_MODEL_DEFAULT,
)
from finmate.agent.tools import TOOLS, run_tool
from finmate.db.repository import get_or_create_user, get_recent_history, save_turn

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

SYSTEM_PROMPT = """Sos Finmate, un asistente financiero personal que responde por WhatsApp.

Tu trabajo es informar e interpretar mercados, no dar recomendaciones de
inversión. Nunca le digas al usuario que compre, venda o mantenga un activo
específico — podés explicar contexto, riesgos y qué está pasando, pero la
decisión siempre es de él.

Reglas de estilo:
- Respondé en español, tono cercano pero profesional.
- Sé conciso: esto es WhatsApp, no un informe — evitá párrafos largos.
- Si no tenés información suficiente o una herramienta falla, decilo con
  claridad en vez de inventar datos.
- Dejá siempre la puerta abierta a que el usuario pregunte más.

Herramientas disponibles: get_market_data te da el estado actual de
índices, commodities y tipo de cambio. Usala cuando el usuario pregunte
por mercados o cuando el contexto de la conversación lo pida."""

_ANALYSIS_TRIGGERS = ("por qué", "porque", "analiza", "explica", "riesgo", "conviene", "oportunidad")

_MAX_TOOL_ROUNDS = 4  # corta el loop si el modelo pidiera tools indefinidamente

_NO_KEY_MSG = (
    "⚠️ Finmate todavía no tiene configurada su inteligencia (falta ANTHROPIC_API_KEY). "
    "Avisale al administrador."
)
_NO_MEMORY_MSG = (
    "❌ No pude acceder a mi memoria en este momento (problema de base de datos). "
    "Probá de nuevo en unos minutos."
)
_GENERIC_ERROR_MSG = "❌ Tuve un problema interno respondiendo. Probá de nuevo en unos minutos.";


def _pick_model(user_message: str) -> str:
    if any(t in user_message.lower() for t in _ANALYSIS_TRIGGERS):
        return ANTHROPIC_MODEL_ANALYSIS
    return ANTHROPIC_MODEL_DEFAULT


def _run_agent(messages: list, model: str) -> str:
    """Loop de tool-calling: llama a Claude, ejecuta las tools que pida, repite
    hasta que devuelva texto final o se agoten los intentos."""
    response = _client.messages.create(
        model=model, max_tokens=600, system=SYSTEM_PROMPT, tools=TOOLS, messages=messages
    )

    rounds = 0
    while response.stop_reason == "tool_use" and rounds < _MAX_TOOL_ROUNDS:
        rounds += 1
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                logger.info(f"Tool call: {block.name}({block.input})")
                result_text = run_tool(block.name, block.input)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
                )

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = _client.messages.create(
            model=model, max_tokens=600, system=SYSTEM_PROMPT, tools=TOOLS, messages=messages
        )

    final_text = "".join(block.text for block in response.content if block.type == "text").strip()
    return final_text or "No pude generar una respuesta esta vez. Probá de nuevo en un momento."


def handle_message(phone: str, user_message: str) -> str:
    """Punto de entrada único desde el webhook de WhatsApp."""
    if _client is None:
        logger.error("ANTHROPIC_API_KEY no configurada.")
        return _NO_KEY_MSG

    # Memoria: si la base de datos no responde (p. ej. todavía no se
    # provisionó DATABASE_URL), se avisa con claridad en vez de que el
    # webhook rompa silenciosamente.
    try:
        user = get_or_create_user(phone)
        history = get_recent_history(user.id)
    except Exception as e:
        logger.error(f"Error de base de datos accediendo a memoria de {phone}: {e}", exc_info=True)
        return _NO_MEMORY_MSG

    messages = [{"role": role, "content": content} for role, content in history]
    messages.append({"role": "user", "content": user_message})

    model = _pick_model(user_message)

    try:
        final_text = _run_agent(messages, model)
    except Exception as e:
        logger.error(f"Error en el orquestador respondiendo a {phone}: {e}", exc_info=True)
        final_text = _GENERIC_ERROR_MSG

    # Se guarda igual aunque haya habido error de LLM, así el historial
    # refleja lo que el usuario realmente vio en WhatsApp. Si esto falla
    # (DB caída justo ahora) no vale la pena romper la respuesta ya generada.
    try:
        save_turn(user.id, "user", user_message)
        save_turn(user.id, "assistant", final_text)
    except Exception as e:
        logger.error(f"No se pudo guardar el turno de conversación de {phone}: {e}", exc_info=True)

    return final_text
