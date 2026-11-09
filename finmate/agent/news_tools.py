"""
Finmate — Tools de noticias e indicadores económicos (Plan Fase 4)

Permiten al usuario configurar qué temas de noticias e indicadores macro
quiere seguir. Las alertas proactivas sobre esos temas quedan para fases
posteriores; acá solo se gestiona el seguimiento.
"""
import logging

logger = logging.getLogger(__name__)

try:
    from finmate.db.news_repo import (
        get_news_topics,
        add_news_topic,
        remove_news_topic,
        get_economic_indicators,
        add_economic_indicator,
        remove_economic_indicator,
    )
    from finmate.data_sources.economic_calendar import get_indicator_info, format_catalog_for_whatsapp
    _NEWS_DB_AVAILABLE = True
except ImportError:
    _NEWS_DB_AVAILABLE = False

_DB_UNAVAILABLE_MSG = "❌ Seguimiento de noticias no disponible todavía (base de datos no configurada)."

_TIPO_EMOJIS = {
    "ticker": "📈",
    "sector": "🏭",
    "pais": "🌎",
    "keyword": "🔍",
}


def tool_get_my_news_topics(user_id: int) -> str:
    if not _NEWS_DB_AVAILABLE:
        return _DB_UNAVAILABLE_MSG

    topics = get_news_topics(user_id)
    indicators = get_economic_indicators(user_id)

    if not topics and not indicators:
        return (
            "No estás siguiendo ningún tema todavía.\n\n"
            "Ejemplos de lo que podés pedirme:\n"
            "• 'Seguime las noticias de AAPL'\n"
            "• 'Seguime el sector tecnología'\n"
            "• 'Seguime el CPI_US' (inflación EE.UU.)\n"
            "• 'Mostrame el calendario económico'"
        )

    lines = ["*TUS SEGUIMIENTOS*", ""]

    if topics:
        lines.append("📰 *Temas de noticias:*")
        for tipo, valor in topics:
            emoji = _TIPO_EMOJIS.get(tipo, "•")
            lines.append(f"  {emoji} {tipo}: {valor}")
        lines.append("")

    if indicators:
        lines.append("📊 *Indicadores económicos:*")
        for code in indicators:
            info = get_indicator_info(code)
            name = info["name"] if info else code
            lines.append(f"  • `{code}` — {name}")
        lines.append("")

    lines.append("Decime qué querés agregar o quitar.")
    return "\n".join(lines)


def tool_follow_news_topic(user_id: int, tool_input: dict) -> str:
    if not _NEWS_DB_AVAILABLE:
        return _DB_UNAVAILABLE_MSG

    tipo = tool_input.get("tipo", "").lower().strip()
    valor = tool_input.get("valor", "").strip()

    if not tipo or not valor:
        return "❌ Necesito el tipo (ticker/sector/pais/keyword) y el valor."

    if tipo not in ("ticker", "sector", "pais", "keyword"):
        tipo = "keyword"

    if tipo == "ticker":
        valor = valor.upper()

    added = add_news_topic(user_id, tipo, valor)
    emoji = _TIPO_EMOJIS.get(tipo, "✅")

    if added:
        return f"{emoji} Listo, te aviso sobre noticias de *{valor}* ({tipo})."
    else:
        return f"Ya estabas siguiendo *{valor}* ({tipo})."


def tool_unfollow_news_topic(user_id: int, tool_input: dict) -> str:
    if not _NEWS_DB_AVAILABLE:
        return _DB_UNAVAILABLE_MSG

    tipo = tool_input.get("tipo", "").lower().strip()
    valor = tool_input.get("valor", "").strip()

    if not tipo or not valor:
        return "❌ Necesito el tipo y el valor para saber qué quitar."

    if tipo == "ticker":
        valor = valor.upper()

    removed = remove_news_topic(user_id, tipo, valor)
    if removed:
        return f"✅ Listo, ya no vas a recibir noticias de *{valor}*."
    else:
        return f"No encontré *{valor}* ({tipo}) en tu lista de seguimientos."


def tool_get_economic_calendar(user_id: int) -> str:
    if not _NEWS_DB_AVAILABLE:
        return _DB_UNAVAILABLE_MSG

    indicators = get_economic_indicators(user_id)

    if not indicators:
        return format_catalog_for_whatsapp()

    lines = ["*TUS INDICADORES ECONÓMICOS*", ""]
    for code in indicators:
        info = get_indicator_info(code)
        if info:
            lines.append(f"• `{code}` — {info['name']} ({info['freq']}) {'🇺🇸' if info['country'] == 'US' else '🇨🇱'}")
        else:
            lines.append(f"• `{code}`")
    lines.append("")
    lines.append("Decime 'seguime el NFP' para agregar más, o 'mostrame el calendario completo'.")
    return "\n".join(lines)


def tool_follow_indicator(user_id: int, tool_input: dict) -> str:
    if not _NEWS_DB_AVAILABLE:
        return _DB_UNAVAILABLE_MSG

    code = tool_input.get("indicator_code", "").upper().strip()
    if not code:
        return "❌ Necesito el código del indicador (ej: CPI_US, NFP, FED_RATE)."

    info = get_indicator_info(code)
    if not info:
        available = ", ".join(f"`{c}`" for c in list(
            __import__("finmate.data_sources.economic_calendar", fromlist=["INDICATOR_CATALOG"]).INDICATOR_CATALOG.keys()
        )[:6])
        return (
            f"❌ No conozco el indicador `{code}`.\n"
            f"Algunos disponibles: {available}...\n"
            "Pedime 'mostrame el calendario económico' para ver todos."
        )

    country = info.get("country", "US")
    added = add_economic_indicator(user_id, code, country)

    flag = "🇺🇸" if country == "US" else "🇨🇱"
    if added:
        return f"{flag} Listo, te aviso sobre *{info['name']}* (`{code}`)."
    else:
        return f"Ya estabas siguiendo `{code}` — {info['name']}."


def tool_unfollow_indicator(user_id: int, tool_input: dict) -> str:
    if not _NEWS_DB_AVAILABLE:
        return _DB_UNAVAILABLE_MSG

    code = tool_input.get("indicator_code", "").upper().strip()
    if not code:
        return "❌ Necesito el código del indicador a quitar."

    removed = remove_economic_indicator(user_id, code)
    if removed:
        info = get_indicator_info(code)
        name = info["name"] if info else code
        return f"✅ Listo, ya no vas a recibir avisos de *{name}* (`{code}`)."
    else:
        return f"No encontré `{code}` en tus indicadores seguidos."
