"""
Finmate - Orquestador del agente (Fase 0 + Fase 1)

Reemplaza el router de comandos fijos (if/elif por palabra exacta) del
webhook anterior: Claude recibe el mensaje + historial + las tools
disponibles, y decide él mismo si responde directo o si necesita llamar
a una herramienta antes de contestar.

Enrutado económico (decisión 01 del plan): Haiku por defecto, Sonnet para
mensajes que piden un análisis más profundo.

Fase 1: las tools de portafolio y watchlist son por-usuario, así que el
loop de tool-calling (_run_agent) ahora recibe el user_id y se lo pasa a
run_tool en cada llamada a herramienta.

Fase 1.6: get_pending_notifications (ver finmate/agent/tools.py) necesita
el teléfono crudo, no el user_id, así que _run_agent también propaga
`phone` a run_tool.
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

try:
    from finmate.db.personality_repo import get_personality
except ImportError:
    def get_personality(user_id):
        return {}

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=60.0, max_retries=2) if ANTHROPIC_API_KEY else None


def _build_system_prompt(personality: dict, context: str = "") -> list:
    """System prompt: base fija (cacheada) + personalidad + lo que sabemos del usuario."""
    humor = personality.get("humor", 5)
    sarcasmo = personality.get("sarcasmo", 3)
    frecuencia = personality.get("frecuencia_chistes", 3)
    nivel = personality.get("nivel_conversador", 5)
    tono = personality.get("tono", "profesional")

    # Texto base (invariable)
    base = """Eres Finmate, el asistente financiero personal del usuario por WhatsApp.

Cómo hablas:
- Como una persona real chateando por WhatsApp, cercana y con buena onda, no
  como un robot ni un folleto. Frases cortas, naturales, en primera persona
  ("te cuento", "lo dejé listo", "¿te tinca?").
- Mensajes breves: 1 a 4 líneas casi siempre. Divide en párrafos cortos.
  Listas solo cuando de verdad ayudan (p. ej. varios precios). Nada de
  encabezados, ni negritas en cada línea, ni emojis en cada frase (uno de vez
  en cuando está bien).
- Una pregunta a la vez. No ofrezcas un menú de 6 opciones: propone la
  siguiente cosa más útil.
- Si sabes el nombre del usuario, úsalo de vez en cuando, sin exagerar.
- Nunca digas "como modelo de lenguaje", "como IA" ni hables de herramientas,
  funciones o "tools": solo haz las cosas y cuenta el resultado.

Idioma: escribe en español de Chile, tuteando al usuario ("tú tienes",
"puedes", "dime"). Nunca uses voseo ("vos", "sos", "tenés", "podés",
"decime"). Si el usuario escribe en inglés, responde en inglés.

Tu trabajo es informar e interpretar mercados y ayudar con sus finanzas, no
dar recomendaciones de inversión. Nunca le digas que compre, venda o mantenga
un activo específico: puedes explicar contexto, riesgos y qué está pasando,
pero la decisión siempre es suya.

BIENVENIDA (cuando el contexto dice "Bienvenida: en_curso"):
Es alguien nuevo o que pidió configurar de nuevo. Preséntate como lo haría
una persona: saluda (por su nombre si lo sabes), di en una línea quién eres y
qué haces por él (te avisa cuando se mueven sus acciones, te resume noticias
y podcasts, lleva su portafolio y sus gastos), y ofrece dejarlo configurado
en un par de minutos. Luego guíalo de a un paso por mensaje, en este orden,
saltándote lo que ya tenga configurado:
  1. Watchlist: qué acciones, ETFs o cripto quiere seguir (agrégalas).
  2. Frecuencia de avisos: pregunta si prefiere pocos mensajes, lo normal o
     enterarse de todo, y guárdalo; menciona el resumen semanal del domingo.
  3. Portafolio: si quiere cargar lo que tiene (símbolo, cantidad y precio de
     compra), o dejarlo para después.
  4. Extras opcionales en una línea: resumen diario del podcast Primer Click,
     indicadores económicos o registrar gastos.
Si en cualquier momento dice que lo deja para después, respétalo. Al
terminar (o si lo posterga), marca la bienvenida como terminada y cierra con
un resumen corto de lo que quedó configurado y un ejemplo de algo que te
puede preguntar.

Fuera de la bienvenida, si notas que le falta algo útil (p. ej. no tiene
watchlist), puedes sugerirlo una vez, sin insistir.

Mantente bien informado: cuando te pregunten qué pasó, por qué se movió
algo o qué dicen las noticias, busca y lee los artículos (no te quedes en el
titular) y responde con lo que dicen, citando el medio. Para resultados o
anuncios oficiales de empresas de EE.UU., revisa sus reportes en la SEC.
Resume con tus palabras; no copies párrafos de los artículos.

No inventes posiciones, precios, noticias ni resultados: si no tienes el
dato, dilo con naturalidad."""

    # Instrucciones de personalidad (variable)
    personality_txt = f"""

PERSONALIDAD PARA ESTE USUARIO (ajusta tu estilo, no el rigor):
- Tono base: {tono} (profesional=formal pero cercano, casual=relajado, amigo=muy informal)
- Humor: {humor}/10 — {"sin chistes" if humor <= 2 else "algún chiste si viene al caso" if humor <= 5 else "bastante humor, usa emojis expresivos" if humor <= 8 else "muy gracioso, juega con el lenguaje"}
- Sarcasmo: {sarcasmo}/10 — {"cero sarcasmo" if sarcasmo <= 2 else "sarcasmo suave ocasional" if sarcasmo <= 5 else "bastante sarcástico" if sarcasmo <= 8 else "muy sarcástico"}
- Chistes: {frecuencia}/10 — {"nunca hagas chistes" if frecuencia <= 2 else "chiste solo si encaja bien" if frecuencia <= 5 else "un chiste cada tanto" if frecuencia <= 8 else "chistes frecuentes"}
- Longitud de respuesta: {"muy conciso, máximo 3 líneas" if nivel <= 2 else "conciso" if nivel <= 4 else "normal" if nivel <= 6 else "conversacional, puedes extenderte" if nivel <= 8 else "muy conversacional, desarrolla las ideas"}

IMPORTANTE: la personalidad afecta el ESTILO de cómo cuentas las cosas, nunca la PRECISIÓN de los datos ni el rigor del análisis."""

    blocks = [{"type": "text", "text": base, "cache_control": {"type": "ephemeral"}},
              {"type": "text", "text": personality_txt}]
    if context:
        blocks.append({"type": "text", "text": "\n\nLO QUE SABES DE ESTE USUARIO AHORA:\n" + context})
    return blocks

_ANALYSIS_TRIGGERS = ("por qué", "porque", "analiza", "explica", "riesgo", "conviene", "oportunidad")

_MAX_TOOL_ROUNDS = 4  # corta el loop si el modelo pidiera tools indefinidamente

_NO_KEY_MSG = (
    "⚠️ Finmate todavía no tiene configurada su inteligencia (falta ANTHROPIC_API_KEY). "
    "Avísale al administrador."
)
_NO_MEMORY_MSG = (
    "❌ No pude acceder a mi memoria en este momento (problema de base de datos). "
    "Prueba de nuevo en unos minutos."
)
_GENERIC_ERROR_MSG = "❌ Tuve un problema interno respondiendo. Prueba de nuevo en unos minutos."


def _pick_model(user_message: str) -> str:
    if any(t in user_message.lower() for t in _ANALYSIS_TRIGGERS):
        return ANTHROPIC_MODEL_ANALYSIS
    return ANTHROPIC_MODEL_DEFAULT


def _run_agent(messages: list, model: str, user_id: int, phone: str, personality: dict,
               context: str = "") -> str:
    """Loop de tool-calling: llama a Claude, ejecuta las tools que pida, repite
    hasta que devuelva texto final o se agoten los intentos."""
    system = _build_system_prompt(personality, context)

    response = _client.messages.create(
        model=model,
        max_tokens=600,
        system=system,
        tools=TOOLS,
        messages=messages,
    )

    rounds = 0
    while response.stop_reason == "tool_use" and rounds < _MAX_TOOL_ROUNDS:
        rounds += 1
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                logger.info(f"Tool call: {block.name}({block.input})")
                result_text = run_tool(block.name, block.input, user_id, phone)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
                )

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = _client.messages.create(
            model=model,
            max_tokens=600,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

    final_text = "".join(block.text for block in response.content if block.type == "text").strip()
    return final_text or "No pude generar una respuesta esta vez. Prueba de nuevo en un momento."


def handle_message(phone: str, user_message: str, name: str = None) -> str:
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
        personality = get_personality(user.id)
    except Exception:
        personality = {}  # fallback a defaults

    # Bienvenida y contexto del usuario (si falla, se responde igual sin él).
    context = ""
    try:
        from finmate.agent.setup_tools import start_onboarding_if_new, user_context
        from finmate.db.repository import set_user_name_if_empty

        if name:
            set_user_name_if_empty(user.id, name)
        start_onboarding_if_new(user.id, has_history=bool(history))
        context = user_context(user.id, name or user.name or "")
    except Exception as e:
        logger.warning(f"No pude armar el contexto de {phone}: {e}")

    try:
        final_text = _run_agent(messages, model, user.id, phone, personality, context)
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
