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

from finmate.agent.document_tools import tool_add_expenses_batch, tool_import_portfolio
from finmate.agent.finance_tools import (
    tool_add_expense,
    tool_get_monthly_summary,
    tool_get_recent_transactions,
    tool_manage_expense_categories,
)
from finmate.agent.macro_tools import (
    tool_get_chile_indicators,
    tool_get_us_macro,
    tool_get_us_release_calendar,
)
from finmate.agent.market_tools import tool_explain_movement
from finmate.agent.podcast_tools import (
    tool_follow_podcast,
    tool_get_podcast_summary,
    tool_unfollow_podcast,
)
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
from finmate.agent.news_content_tools import (
    tool_get_company_filings,
    tool_get_news_detail,
    tool_read_article,
)
from finmate.agent.setup_tools import (
    tool_get_notification_settings,
    tool_get_panel_link,
    tool_onboarding,
    tool_set_notification_settings,
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
            "aviso corto de Finmate (empiezan con 'Aviso de tu cuenta Finmate' o "
            "'Alerta de precio de tu lista de seguimiento') con algo afirmativo "
            "o cualquier respuesta (ej: 'sí', 'dale', 'muéstrame', 'mostrame', "
            "'ver', 'mándalo', 'quiero verlo', 'ok'). Si no hay "
            "nada pendiente, la tool lo informa — no hace falta preguntarle "
            "al usuario antes de llamarla."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    # ── Finanzas personales (Plan Fase 5) ──────────────────────────────────
    {
        "name": "add_expense",
        "description": "Registra un gasto o ingreso personal. Usar cuando el usuario diga algo como 'gasté X en Y', 'pagué X', 'cobré X', 'ingresé X'. Extrae el monto, la categoría, una descripción corta y, si la menciona, la ocasión (ej: 'cumpleaños de la Cata', 'aniversario'). Categorías por defecto: Comidas, Carretes, Asados, Regalos, Suscripciones, Polola, Copete, Bets y Otros; cada usuario puede tener además categorías propias o haber sacado alguna (si dudas, llama antes a manage_expense_categories con action=list). Si no queda clara la categoría, pregunta antes de registrar ofreciendo sus opciones.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo":        {"type": "string",  "enum": ["gasto", "ingreso"], "description": "gasto (gasté, pagué, compré) o ingreso (cobré, me pagaron, ingresé)"},
                "amount":      {"type": "number",  "description": "Monto — negativo para gasto, positivo para ingreso"},
                "category":    {"type": "string",  "description": "Categoría del gasto: una de las del usuario (por defecto Comidas, Carretes, Asados, Regalos, Suscripciones, Polola, Copete, Bets u Otros, más las propias que haya agregado)"},
                "occasion":    {"type": "string",  "description": "Ocasión del gasto si el usuario la dice (ej: cumpleaños de la Cata). Opcional"},
                "merchant":    {"type": "string",  "description": "Comercio o lugar (ej: Café Altura). Opcional"},
                "description": {"type": "string",  "description": "Descripción corta (ej: almuerzo, uber, netflix)"},
                "date_str":    {"type": "string",  "description": "Fecha YYYY-MM-DD (opcional, default hoy)"},
                "raw_text":    {"type": "string",  "description": "Texto original del usuario (opcional)"},
            },
            "required": ["tipo", "amount", "category", "description"],
        },
    },
    {
        "name": "add_expenses_batch",
        "description": "Registra varios gastos o ingresos de una vez, por ejemplo los movimientos leídos de una cartola o boleta que el usuario mandó en foto o PDF. Usar SOLO después de que el usuario confirme. Cada item tiene los mismos campos que add_expense.",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {"type": "array", "description": "Movimientos a registrar", "items": {
                    "type": "object",
                    "properties": {
                        "tipo": {"type": "string", "enum": ["gasto", "ingreso"]},
                        "amount": {"type": "number", "description": "Monto (positivo; el tipo define el signo)"},
                        "category": {"type": "string"},
                        "description": {"type": "string"},
                        "merchant": {"type": "string"},
                        "date_str": {"type": "string", "description": "YYYY-MM-DD"},
                    },
                    "required": ["tipo", "amount", "category", "description"],
                }},
            },
            "required": ["items"],
        },
    },
    {
        "name": "import_portfolio",
        "description": "Carga en el portafolio del usuario las posiciones leídas de un pantallazo o cartola de su corredora. Usar SOLO después de que el usuario confirme. mode='replace' deja exactamente la cantidad (y costo promedio) del documento; mode='add' suma a lo que ya tenía.",
        "input_schema": {
            "type": "object",
            "properties": {
                "positions": {"type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Ticker, ej: AAPL, SPY, NVDA"},
                        "quantity": {"type": "number"},
                        "avg_cost": {"type": "number", "description": "Precio promedio de compra por unidad (opcional)"},
                    },
                    "required": ["symbol", "quantity"],
                }},
                "mode": {"type": "string", "enum": ["replace", "add"]},
            },
            "required": ["positions"],
        },
    },
    {
        "name": "manage_expense_categories",
        "description": "Lista, agrega o saca categorías de gasto del usuario (afecta solo su cuenta). Usar cuando pregunte qué categorías tiene, o pida 'agrega la categoría X' / 'saca la categoría Y'. Sacar una no borra los gastos que ya tenía ahí. 'Otros' no se puede sacar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "add", "remove"], "description": "list (ver), add (agregar o volver a poner) o remove (sacar)"},
                "name":   {"type": "string", "description": "Nombre de la categoría (para add/remove)"},
            },
            "required": ["action"],
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
        "description": "Agrega un tema de noticias para seguir. Usar cuando el usuario diga 'seguime las noticias de X', 'avísame sobre X'. Tipos: ticker (ej: AAPL), sector (ej: tecnología), pais (ej: Chile), keyword (ej: inflación).",
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
        "description": "Agrega un indicador económico macro para seguir. Usar cuando el usuario diga 'seguime el CPI', 'avísame del NFP', etc. Códigos: FED_RATE, CPI_US, NFP, GDP_US, PCE_US, IPC_CL, BCCh_RATE, etc.",
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
    # ── Macro EE.UU. y Chile (Etapa A de fuentes) ──────────────────────────
    {
        "name": "get_us_macro",
        "description": "Datos macro actuales de EE.UU. desde FRED: tasa de la Fed, inflación (IPC general y subyacente), desempleo y bonos del Tesoro a 2 y 10 años. Usar cuando pregunten por la tasa de la Fed, la inflación o el desempleo en EE.UU., o los bonos del Tesoro.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_chile_indicators",
        "description": "Indicadores oficiales de Chile desde el Banco Central: dólar observado, UF, tasa de política monetaria (TPM) e IPC. Usar cuando pregunten por el dólar en Chile, el valor de la UF, la TPM o la inflación en Chile.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_us_release_calendar",
        "description": "Fechas de las próximas publicaciones importantes de EE.UU. (IPC, empleo/NFP, PIB, PCE, decisión de la Fed) en los próximos 14 días, desde el calendario oficial de FRED. Usar cuando pregunten cuándo sale un dato o qué datos vienen esta semana.",
        "input_schema": {"type": "object", "properties": {}},
    },
    # ── Podcasts (Etapa C) ─────────────────────────────────────────────────
    {
        "name": "follow_podcast",
        "description": "Suscribe al usuario al resumen diario por WhatsApp de un podcast. Disponible: Primer Click (Diario Financiero). Usar cuando diga 'mándame el resumen de Primer Click', 'quiero el resumen del podcast del DF'.",
        "input_schema": {"type": "object", "properties": {"podcast": {"type": "string", "description": "Nombre del podcast, ej: Primer Click"}}, "required": ["podcast"]},
    },
    {
        "name": "unfollow_podcast",
        "description": "Deja de enviar al usuario el resumen diario de un podcast.",
        "input_schema": {"type": "object", "properties": {"podcast": {"type": "string"}}, "required": ["podcast"]},
    },
    {
        "name": "get_podcast_summary",
        "description": "Entrega el último resumen generado de un podcast (por defecto Primer Click del Diario Financiero). Usar cuando pregunte 'qué dijo Primer Click hoy', 'resumen del podcast'.",
        "input_schema": {"type": "object", "properties": {"podcast": {"type": "string"}}},
    },
    # ── Noticias con contenido completo ────────────────────────────────────
    {
        "name": "get_news_detail",
        "description": "Busca noticias recientes sobre un tema o empresa y LEE el contenido de los artículos (no solo titulares), juntando Finnhub, Bing News en español e inglés y The Guardian. Usar cuando pregunte qué pasó, por qué se movió algo, 'cuéntame más', qué dice la prensa de X, o un tema económico/político que afecte mercados. symbol: ticker si es una empresa (ej NVDA); query: tema en palabras (ej 'Jensen Huang Nvidia CEO', 'tasa de interés Banco Central Chile').",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "symbol": {"type": "string"}}},
    },
    {
        "name": "read_article",
        "description": "Lee el texto completo de un artículo a partir de su link (por ejemplo uno que mandó el usuario o que apareció en otra búsqueda).",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
    {
        "name": "get_company_filings",
        "description": "Últimos reportes oficiales de una empresa de EE.UU. en la SEC (8-K con hechos esenciales y resultados, 10-Q trimestral, 10-K anual), con un extracto del comunicado más reciente. Usar para resultados trimestrales, anuncios oficiales o cambios en la empresa.",
        "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
    },
    # ── Bienvenida y ajustes de avisos ─────────────────────────────────────
    {
        "name": "get_notification_settings",
        "description": "Muestra cada cuánto le llegan avisos al usuario: umbral de alerta de watchlist (% de movimiento diario), máximo de avisos de noticias por día y si recibe el resumen semanal.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_notification_settings",
        "description": "Cambia la frecuencia de avisos y la jornada del usuario (horas de inicio y término). watchlist_threshold_pct: avisar cuando un activo de la watchlist se mueva más de X% en el día (0.5 a 50; más bajo = más avisos). news_max_per_day: máximo de avisos de noticias de sus activos por día (0 = ninguno, hasta 10). weekly_summary_enabled: resumen semanal del domingo. Pasa solo lo que el usuario quiera cambiar. Guía para traducir lo que diga: 'pocos mensajes' ≈ umbral 7 y 2 noticias/día; 'normal' ≈ umbral 5 y 4 noticias/día; 'todo lo que pase' ≈ umbral 3 y 8 noticias/día.",
        "input_schema": {
            "type": "object",
            "properties": {
                "watchlist_threshold_pct": {"type": "number", "minimum": 0.5, "maximum": 50},
                "news_max_per_day": {"type": "integer", "minimum": 0, "maximum": 10},
                "weekly_summary_enabled": {"type": "boolean"},
                "earnings_alerts": {"type": "string", "enum": ["off", "mine", "all"], "description": "Resultados trimestrales de empresas: off=ninguno, mine=solo de sus activos (portafolio y watchlist), all=todas"},
                "macro_alerts": {"type": "boolean", "description": "Datos macro apenas se publican (inflación, empleo, tasas)"},
                "market_news_alerts": {"type": "boolean", "description": "Noticias generales importantes del mercado, aunque no sean de sus activos"},
                "workday_start": {"type": "string", "description": "Hora de inicio de su jornada, HH:MM (ej. 08:30). Al inicio recibe un resumen del mercado en un párrafo."},
                "workday_end": {"type": "string", "description": "Hora de término de su jornada, HH:MM (ej. 18:30). Al cierre recibe otro resumen. Fuera de la jornada el bot no le escribe por su cuenta: solo responde si pregunta."},
                "workday_weekends": {"type": "boolean", "description": "Si la jornada también corre sábado y domingo (por defecto no)"},
                "workday_enabled": {"type": "boolean", "description": "false = sin jornada: los avisos llegan a cualquier hora y no hay resúmenes de inicio/cierre"},
            },
        },
    },
    {
        "name": "get_panel_link",
        "description": "Genera un link para que el usuario entre a su panel web de Finmate sin contraseña (un solo uso, 15 minutos). Usar cuando pida 'panel', 'la web', 'entrar a la app', 'ver mi portafolio en la web' o quiera cambiar ajustes visualmente.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "onboarding",
        "description": "Marca la bienvenida como terminada ('complete') cuando el usuario ya configuró lo que quería o dijo que lo deja para después; o la reinicia ('restart') si pide configurar todo de nuevo ('empecemos de cero', 'configúrame de nuevo').",
        "input_schema": {
            "type": "object",
            "properties": {"action": {"type": "string", "enum": ["complete", "restart"]}},
            "required": ["action"],
        },
    },
    # ── Imágenes del portafolio ────────────────────────────────────────────
    {
        "name": "send_portfolio_chart",
        "description": "Dibuja una imagen del portafolio REAL del usuario y se la manda por WhatsApp. kind: 'torta' (distribución por activo), 'torta_clase' (renta variable/fija…), 'torta_sector', 'barras' (ganancia o pérdida % de cada posición) o 'tabla' (posiciones con precio, variación del día, valor y resultado). Usar cuando pida ver su portafolio en gráfico, torta, tabla o imagen. Si pide 'muéstrame mi portafolio' sin decir cómo, responde en texto y ofrece estas vistas en una línea. Después de mandarla, responde corto sin repetir las cifras.",
        "input_schema": {
            "type": "object",
            "properties": {"kind": {"type": "string", "enum": ["torta", "torta_clase", "torta_sector", "barras", "tabla"]}},
            "required": ["kind"],
        },
    },
    # ── Perfil de noticias (notas 1-3) ─────────────────────────────────────
    {
        "name": "get_news_profile",
        "description": "Muestra lo que Finmate aprendió de las notas 1-3 que el usuario le pone a las noticias: qué temas, empresas y tipos de noticia le llegan por chat (nivel 3), en el resumen (nivel 2) o solo si pregunta (nivel 1). Usar cuando pregunte qué noticias le mandas, por qué no le llegó algo o cómo está su perfil.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_news_preference",
        "description": "Fija a mano el nivel de un tema, empresa o tipo de noticia cuando el usuario lo pide explícitamente ('no me mandes más noticias de cripto', 'todo lo de NVDA mándamelo al tiro', 'vuelve a aprender solo con tecnología'). level: 3 = por chat, 2 = en el resumen, 1 = solo si pregunta, 0 = volver a automático. topic: ticker (NVDA) o tema (tasas, inflación, empleo, resultados, analistas, fusiones, regulación, aranceles, geopolítica, IA y tecnología, petróleo, cripto, dividendos, productos, Chile). No usarla para notas sueltas 1-2-3 a una noticia: esas se anotan solas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "level": {"type": "integer", "minimum": 0, "maximum": 3},
            },
            "required": ["topic", "level"],
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
        "description": "Cambia uno o más parámetros de personalidad de Finmate para este usuario. Usar cuando diga 'poneme más humor', 'quiero que seas más gracioso', 'cambié el tono a casual', etc. Parámetros: humor (1-10), sarcasmo (1-10), frecuencia_chistes (1-10), nivel_conversador (1-10), tono (profesional|casual|amigo), emojis (1-10: cuántos emojis usa en mensajes y listas; 1-2 = ninguno). Usar emojis cuando pida 'sin emojis', 'más emojis', 'listas sin emojis', etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "humor": {"type": "integer", "minimum": 1, "maximum": 10},
                "sarcasmo": {"type": "integer", "minimum": 1, "maximum": 10},
                "frecuencia_chistes": {"type": "integer", "minimum": 1, "maximum": 10},
                "nivel_conversador": {"type": "integer", "minimum": 1, "maximum": 10},
                "emojis": {"type": "integer", "minimum": 1, "maximum": 10},
                "tono": {"type": "string", "enum": ["profesional", "casual", "amigo"]},
            },
        },
    },
]

# Cache corto: si dos usuarios (o el mismo, dos veces) preguntan "mercados"
# con segundos de diferencia, no hace falta pegarle de nuevo a Finnhub/Alpha
# Vantage. 30s es prudente para no mostrar datos desactualizados.
_MARKET_DATA_CACHE_TTL = 30

def _charts():
    from finmate.services import charts

    return charts


def _news_profile():
    from finmate.services import news_profile

    return news_profile


# Tools que operan sobre datos del usuario (necesitan user_id).
_USER_SCOPED_TOOLS = {
    "get_portfolio": lambda user_id, _input: tool_get_portfolio(user_id),
    "add_to_portfolio": tool_add_to_portfolio,
    "remove_from_portfolio": tool_remove_from_portfolio,
    "get_watchlist": lambda user_id, _input: tool_get_watchlist(user_id),
    "add_to_watchlist": tool_add_to_watchlist,
    "remove_from_watchlist": tool_remove_from_watchlist,
    "send_portfolio_chart":      lambda user_id, _input: _charts().tool_send_portfolio_chart(user_id, _input),
    "get_news_profile":          lambda user_id, _input: _news_profile().tool_get_news_profile(user_id),
    "set_news_preference":       lambda user_id, _input: _news_profile().tool_set_news_preference(user_id, _input),
    "get_personality":           lambda user_id, _input: tool_get_personality(user_id),
    "set_personality":           tool_set_personality,
    # Finanzas personales
    "add_expense":               tool_add_expense,
    "add_expenses_batch":        tool_add_expenses_batch,
    "import_portfolio":          tool_import_portfolio,
    "get_monthly_summary":       tool_get_monthly_summary,
    "get_recent_transactions":   lambda user_id, _input: tool_get_recent_transactions(user_id),
    "manage_expense_categories": tool_manage_expense_categories,
    # Noticias e indicadores
    "get_my_news_topics":        lambda user_id, _input: tool_get_my_news_topics(user_id),
    "follow_news_topic":         tool_follow_news_topic,
    "unfollow_news_topic":       tool_unfollow_news_topic,
    "get_economic_calendar":     lambda user_id, _input: tool_get_economic_calendar(user_id),
    "follow_indicator":          tool_follow_indicator,
    "unfollow_indicator":        tool_unfollow_indicator,
    # Bienvenida y ajustes de avisos
    "get_notification_settings": lambda user_id, _input: tool_get_notification_settings(user_id),
    "set_notification_settings": tool_set_notification_settings,
    "onboarding":                tool_onboarding,
    "get_panel_link":            tool_get_panel_link,
    # Podcasts (Etapa C)
    "follow_podcast":            tool_follow_podcast,
    "unfollow_podcast":          tool_unfollow_podcast,
}

# Tools que operan sobre el teléfono crudo, no sobre el user_id de la DB
# (Fase 1.6: la cola de notificaciones pendientes vive por número de
# WhatsApp — ver finmate/alerts/pending.py).
_PHONE_SCOPED_TOOLS = {
    "get_pending_notifications": lambda phone, _input: (
        pop_pending(phone) or "No tienes avisos pendientes en este momento."
    ),
}


def run_tool(
    name: str, tool_input: dict, user_id: Optional[int] = None, phone: Optional[str] = None
) -> str:
    if name == "get_market_data":
        return cached("finmate:market_data", _MARKET_DATA_CACHE_TTL, _get_market_data)

    if name == "explain_movement":
        return tool_explain_movement(tool_input)

    if name == "get_news_detail":
        return tool_get_news_detail(tool_input)

    if name == "read_article":
        return tool_read_article(tool_input)

    if name == "get_company_filings":
        return tool_get_company_filings(tool_input)

    if name == "get_podcast_summary":
        return tool_get_podcast_summary(tool_input)

    if name == "get_us_macro":
        return cached("finmate:us_macro", 1800, tool_get_us_macro)

    if name == "get_chile_indicators":
        return cached("finmate:cl_indicators", 1800, tool_get_chile_indicators)

    if name == "get_us_release_calendar":
        return cached("finmate:us_releases", 3600, tool_get_us_release_calendar)

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
