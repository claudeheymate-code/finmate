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
  2. Su jornada: a qué hora empieza y termina su día (por defecto 08:30 a
     18:30, lunes a viernes). Explícale en una línea que al inicio y al cierre
     le mandas un resumen del mercado en un párrafo, que durante la jornada le
     avisas lo importante y que fuera de ella solo respondes si te escribe.
  3. Cómo aprendes qué noticias le importan (díselo siempre, en dos o tres
     líneas): cada noticia que le mandes trae botones 1, 2 y 3 (3 = muy
     relevante). Las de nivel 3 le llegan por el chat durante el día, las de
     nivel 2 van en sus resúmenes de inicio y cierre, y las de nivel 1 solo
     si te pregunta por el tema. No es blanco o negro: si pone 1 a un tipo de
     noticia no desaparece de inmediato, se la muestras cada vez menos hasta
     que sus notas confirman que no le interesa. Mientras más califique, mejor
     queda su perfil, y lo puede revisar y cambiar en Ajustes → Tus noticias.
  4. Frecuencia de avisos: pregunta si prefiere pocos mensajes, lo normal o
     enterarse de todo, y guárdalo; menciona el resumen semanal del domingo
     y pregunta si también quiere resultados de empresas (solo de sus
     activos o de todas), datos macro y noticias generales del mercado.
  5. Portafolio: si quiere cargar lo que tiene (símbolo, cantidad y precio de
     compra) o mandarte un pantallazo de su corredora, o dejarlo para después.
  6. Extras opcionales en una línea: resumen diario del podcast Primer Click,
     indicadores económicos o registrar gastos.
Si en cualquier momento dice que lo deja para después, respétalo. Al
terminar (o si lo posterga), marca la bienvenida como terminada y cierra con
un resumen corto de lo que quedó configurado, un ejemplo de algo que te
puede preguntar y cuéntale que también tiene un panel web (si lo quiere,
mándale su link de acceso).

PERFIL DE NOTICIAS: las notas 1-3 que el usuario da a las noticias se anotan
solas. Si te pregunta por un tema o empresa, muéstrale todas las noticias
que encuentres aunque su perfil diga nivel 1: el nivel solo decide qué le
mandas por iniciativa propia. Si pide cambiar algo de forma explícita ("no
me mandes más de cripto"), usa set_news_preference; para ver el perfil,
get_news_profile.

Fuera de la bienvenida, si notas que le falta algo útil (p. ej. no tiene
watchlist), puedes sugerirlo una vez, sin insistir.

Mantente bien informado: cuando te pregunten qué pasó, por qué se movió
algo o qué dicen las noticias, busca y lee los artículos (no te quedes en el
titular) y responde con lo que dicen, citando el medio. Para resultados o
anuncios oficiales de empresas de EE.UU., revisa sus reportes en la SEC.
Resume con tus palabras; no copies párrafos de los artículos.

FOTOS Y DOCUMENTOS (cartolas, boletas, pantallazos de tu corredora):
Cuando el usuario mande una foto o un PDF, léelo con atención y dile en
pocas líneas qué encontraste. Según lo que sea:
  - Cartola o estado de cuenta bancaria / boleta: lista los movimientos que
    son gastos o ingresos (fecha, comercio, monto, categoría que propones) y
    pregunta si los registras. Al confirmar, regístralos todos juntos con
    add_expenses_batch. Ignora pagos de la tarjeta, traspasos entre sus
    cuentas y cargos repetidos. Si son más de 25, muestra un resumen por
    categoría y registra igual el detalle.
  - Pantallazo o cartola de inversiones: lista las posiciones (ticker,
    cantidad, precio promedio si aparece) y pregunta si actualizas su
    portafolio con eso. Al confirmar, usa import_portfolio (modo "replace"
    para dejar las cantidades exactas que muestra el documento).
  - Otra cosa (un gráfico, una noticia, un informe): explícalo o resúmelo.
Si algo no se lee bien (montos cortados, foto borrosa), dilo y pide otra
foto en vez de adivinar. Nunca registres nada sin que el usuario confirme.

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

_MAX_TOOL_ROUNDS = 8  # corta el loop si el modelo pidiera tools indefinidamente
_MAX_TOKENS = 1500    # 600 cortaba respuestas largas (resúmenes, análisis de cartolas)

_NO_KEY_MSG = (
    "⚠️ Finmate todavía no tiene configurada su inteligencia (falta ANTHROPIC_API_KEY). "
    "Avísale al administrador."
)
_NO_MEMORY_MSG = (
    "❌ No pude acceder a mi memoria en este momento (problema de base de datos). "
    "Prueba de nuevo en unos minutos."
)
_TOO_MANY_MSG = "Me llegaron muchos mensajes seguidos 😅 Dame unos minutos y vuelve a escribirme."
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
        max_tokens=_MAX_TOKENS,
        system=system,
        tools=TOOLS,
        messages=messages,
    )
    _record_usage(model, response)

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
            max_tokens=_MAX_TOKENS,
            system=system,
            tools=TOOLS,
            messages=messages,
        )
        _record_usage(model, response)

    final_text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not final_text:
        # Se acabaron las rondas de tools (o el modelo no escribió nada): antes se respondía
        # "No pude generar una respuesta". Ahora se le pide que conteste con lo que ya tiene.
        logger.warning(f"Respuesta sin texto (stop_reason={response.stop_reason}, rondas={rounds}); se fuerza el cierre.")
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": b.id, "content": "Sin más consultas: responde ya con lo que tienes."}
                for b in response.content if b.type == "tool_use"]})
        else:
            messages.append({"role": "user", "content": "Responde ahora al usuario con lo que ya sabes, en pocas líneas."})
        response = _client.messages.create(
            model=model, max_tokens=_MAX_TOKENS, system=system, tools=TOOLS,
            tool_choice={"type": "none"}, messages=messages)
        _record_usage(model, response)
        final_text = "".join(block.text for block in response.content if block.type == "text").strip()
    return final_text or "No pude generar una respuesta esta vez. Prueba de nuevo en un momento."


def _report_claude_problem(e: Exception) -> None:
    """Si Claude rechaza la clave o no hay créditos, se avisa en el admin (Inbox → Seguridad):
    así se sabe por qué el bot contestó "Tuve un problema interno"."""
    text = str(e).lower()
    if "authentication" in text or "x-api-key" in text or "401" in text:
        detail = ("Claude rechazó la clave (ANTHROPIC_API_KEY): el bot no puede responder. "
                  "Crea una clave nueva en platform.claude.com y pégala en Railway.")
    elif "credit" in text or "balance" in text or "billing" in text:
        detail = "La cuenta de Claude se quedó sin créditos: el bot no puede responder. Carga saldo en platform.claude.com."
    elif "overloaded" in text or "529" in text or "rate" in text:
        return  # pasajero; no vale la pena alertar
    else:
        detail = f"Claude respondió con un error inesperado ({type(e).__name__}). Si se repite, revisa los logs."
    try:
        from finmate.security.monitor import record_event

        record_event("claude_error", "high", detail, ip=None, path=None)
    except Exception:
        pass


def _record_usage(model: str, response) -> None:
    try:
        from finmate.services.usage import record_claude

        record_claude(model, getattr(response, "usage", None))
    except Exception:
        pass


def _attachment_note(attachments: list) -> str:
    """Texto que queda en el historial en vez del archivo (no se guardan las fotos)."""
    n_img = sum(1 for a in attachments if a.get("kind") == "image")
    names = [a.get("name") for a in attachments if a.get("kind") != "image" and a.get("name")]
    parts = []
    if n_img:
        parts.append(f"{n_img} foto{'s' if n_img > 1 else ''}")
    if names:
        parts.append("archivo(s): " + ", ".join(names[:5]))
    return f"[Mandó {' y '.join(parts)}]"


def _content_blocks(user_message: str, attachments: list) -> list:
    blocks = []
    for a in attachments:
        if a.get("kind") == "image":
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": a["media_type"], "data": a["data"]}})
        elif a.get("kind") == "pdf":
            blocks.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                          "data": a["data"]}, "title": a.get("name") or "documento"})
        elif a.get("kind") == "text":
            blocks.append({"type": "document", "source": {"type": "text", "media_type": "text/plain",
                                                          "data": a.get("text", "")}, "title": a.get("name") or "archivo"})
    blocks.append({"type": "text", "text": user_message or "Revisa lo que te acabo de mandar."})
    return blocks


def _clean_history(history: list) -> list:
    """Historial listo para Claude: empieza con el usuario y no repite el mismo rol seguido
    (los avisos y resúmenes que manda el bot quedan como turnos del asistente sin pregunta)."""
    out = []
    for role, content in history:
        if not content or role not in ("user", "assistant"):
            continue
        if not out and role != "user":
            continue
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n\n" + content
        else:
            out.append({"role": role, "content": content})
    if out and out[-1]["role"] == "user":       # el mensaje nuevo también es del usuario: no se repite el rol
        out.pop()
    return out


def handle_message(phone: str, user_message: str, name: str = None, attachments: list = None) -> str:
    """Punto de entrada único desde el webhook de WhatsApp (y el chat del panel).
    `attachments`: fotos o documentos ya descargados (ver webhook._process_media)."""
    attachments = attachments or []
    history_text = (f"{_attachment_note(attachments)} {user_message}".strip() if attachments else user_message)
    try:
        from finmate.security.guard import note_message

        if not note_message(phone):
            return _TOO_MANY_MSG
    except Exception:  # noqa: BLE001
        pass
    # Memoria: si la base de datos no responde (p. ej. todavía no se
    # provisionó DATABASE_URL), se avisa con claridad en vez de que el
    # webhook rompa silenciosamente.
    try:
        from config.settings import ACCESS_APPROVAL_REQUIRED, WHATSAPP_RECIPIENTS

        if ACCESS_APPROVAL_REQUIRED and phone not in WHATSAPP_RECIPIENTS:
            user = get_or_create_user(phone, new_status="pending")
        else:
            user = get_or_create_user(phone, new_status="approved")
        history = get_recent_history(user.id)
    except Exception as e:
        logger.error(f"Error de base de datos accediendo a memoria de {phone}: {e}", exc_info=True)
        return _NO_MEMORY_MSG

    # Acceso: números nuevos esperan aprobación en el panel admin (Inbox).
    status = getattr(user, "access_status", None) or "approved"
    if status != "approved":
        return _handle_without_access(user, phone, history_text, name, status, first=not history)

    # Nota 1-3 a una noticia ("3", "a3 b1"): se anota sin pasar por Claude.
    if not attachments:
        try:
            from finmate.services.news_profile import try_handle_rating

            last_bot = next((c for r, c in reversed(history) if r == "assistant"), "")
            rated = try_handle_rating(user.id, user_message, last_assistant=last_bot)
            if rated:
                save_turn(user.id, "user", user_message)
                save_turn(user.id, "assistant", rated)
                return rated
        except Exception as e:  # noqa: BLE001
            logger.warning(f"No pude revisar si {phone} calificó una noticia: {e}")

    # El registro de números nuevos no usa Claude; desde aquí sí hace falta la clave.
    if _client is None:
        logger.error("ANTHROPIC_API_KEY no configurada.")
        return _NO_KEY_MSG

    messages = _clean_history(history)
    messages.append({"role": "user", "content": _content_blocks(user_message, attachments) if attachments else user_message})

    # Con fotos o documentos se usa el modelo de análisis (lee mejor cartolas y tablas).
    model = ANTHROPIC_MODEL_ANALYSIS if attachments else _pick_model(user_message)

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
        _report_claude_problem(e)

    # Se guarda igual aunque haya habido error de LLM, así el historial
    # refleja lo que el usuario realmente vio en WhatsApp. Si esto falla
    # (DB caída justo ahora) no vale la pena romper la respuesta ya generada.
    try:
        save_turn(user.id, "user", history_text)
        save_turn(user.id, "assistant", final_text)
    except Exception as e:
        logger.error(f"No se pudo guardar el turno de conversación de {phone}: {e}", exc_info=True)

    return final_text


def handle_rating_button(phone: str, button_id: str, title: str = "") -> str:
    """Botones 1-2-3 que van con cada noticia. Devuelve la respuesta o "" si no aplica."""
    try:
        from finmate.db.repository import find_user_by_phone
        from finmate.services.news_profile import rate_from_button

        user = find_user_by_phone(phone)
        if user is None or (getattr(user, "access_status", None) or "approved") != "approved":
            return ""
        reply = rate_from_button(user.id, button_id) or ""
        if reply:
            save_turn(user.id, "user", title or button_id)
            save_turn(user.id, "assistant", reply)
        return reply
    except Exception as e:  # noqa: BLE001
        logger.warning(f"No pude registrar el botón {button_id!r} de {phone}: {e}")
        return ""


_ASK_DATA = ("¡Hola{nombre}! Soy Finmate, un asistente financiero por WhatsApp. "
             "Para pedir tu acceso necesito dos datos: tu *nombre y apellido* y tu *correo*. "
             "Puedes mandarlos en un solo mensaje.")
_ASK_AGAIN = "Para pedir tu acceso necesito tu *nombre y apellido* y tu *correo*. ¿Me los mandas?"
_ASK_EMAIL = "Gracias, {nombre}. ¿Me das tu *correo*?"
_ASK_NAME = "Gracias. ¿Y tu *nombre y apellido*?"
_REGISTERED = ("¡Listo, {nombre}! Ya registré tus datos. Tu acceso está pendiente de aprobación; "
               "te aviso por aquí apenas esté listo.")
_PENDING_AGAIN = "Tu acceso a Finmate sigue pendiente de aprobación. Te escribo apenas esté listo."
_DENIED = "Por ahora este número no tiene acceso a Finmate. Si crees que es un error, avísale a quien te invitó."


def _handle_without_access(user, phone: str, user_message: str, name, status: str, first: bool) -> str:
    """Responde sin usar el agente: pide nombre y correo y deja la solicitud en el Inbox del admin."""
    if status == "denied":
        reply = _DENIED
    elif getattr(user, "registered_at", None):
        reply = _PENDING_AGAIN
    else:
        reply = _collect_signup(user, phone, user_message, name, first)
    try:
        save_turn(user.id, "user", user_message)
        save_turn(user.id, "assistant", reply)
    except Exception as e:
        logger.error(f"No se pudo guardar el mensaje de {phone} (sin acceso): {e}")
    return reply


def _collect_signup(user, phone: str, user_message: str, profile_name, first: bool) -> str:
    """Junta nombre y correo (pueden llegar en mensajes distintos). Al tenerlos, avisa al admin."""
    from finmate.agent.signup import parse_signup
    from finmate.db.state_store import load_json, save_json

    key = f"signup:{user.id}"
    draft = load_json(key, {}) or {}
    got_name, got_email = parse_signup(user_message)
    if got_email:
        draft["email"] = got_email
    # El primer "hola" no trae datos; un nombre suelto solo se toma si ya se pidió.
    if got_name and (not first or got_email):
        draft["name"] = got_name
    save_json(key, draft)

    first_name = (draft.get("name") or "").split(" ")[0]
    if draft.get("name") and draft.get("email"):
        try:
            from finmate.db.repository import save_registration

            save_registration(user.id, draft["name"], draft["email"])
        except Exception as e:
            logger.error(f"No se pudo guardar el registro de {phone}: {e}")
        _notify_admin_new_request(phone, draft["name"], draft["email"])
        return _REGISTERED.format(nombre=first_name)
    if first:
        hi = (profile_name or "").split(" ")[0]
        return _ASK_DATA.format(nombre=f" {hi}" if hi else "")
    if draft.get("name"):
        return _ASK_EMAIL.format(nombre=first_name)
    if draft.get("email"):
        return _ASK_NAME
    return _ASK_AGAIN


def _notify_admin_new_request(phone: str, name, email=None) -> None:
    """Avisa a los administradores por WhatsApp y por correo del nuevo registro."""
    from config.settings import PANEL_BASE_URL

    number = phone.replace("whatsapp:", "")
    link = f"{PANEL_BASE_URL.rstrip('/')}/admin/inbox"
    lines = ["Nueva solicitud de acceso a Finmate", f"Nombre: {name or '—'}", f"Correo: {email or '—'}",
             f"WhatsApp: {number}"]
    try:
        from config.settings import WHATSAPP_RECIPIENTS
        from finmate.whatsapp.messenger import WhatsAppMessenger

        msg = "*" + lines[0] + "*\n" + "\n".join(lines[1:]) + f"\n\nApruébala o recházala en {link}"
        m = WhatsAppMessenger()
        for admin in WHATSAPP_RECIPIENTS:
            m.send_message(admin, msg)
    except Exception as e:
        logger.info(f"No pude avisar al admin por WhatsApp de la nueva solicitud: {e}")
    try:
        from finmate.services.feedback import send_email

        send_email(f"Finmate: nuevo registro — {name or number}", "\n".join(lines[1:]) + f"\n\nInbox: {link}",
                   {"nombre": name or "", "correo": email or "", "whatsapp": number})
    except Exception as e:
        logger.info(f"No pude avisar al admin por correo de la nueva solicitud: {e}")
