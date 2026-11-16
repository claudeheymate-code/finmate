"""Finmate - Tools de podcasts para el agente (Etapa C)."""
from finmate.podcasts.catalog import PODCASTS, resolve

_LISTA = ", ".join(m["name"] for m in PODCASTS.values())


def tool_follow_podcast(user_id: int, tool_input: dict) -> str:
    pid = resolve(tool_input.get("podcast", ""))
    if not pid:
        return f"Todavía no sé resumir ese podcast. Los disponibles son: {_LISTA}."
    from finmate.db.news_repo import add_news_topic
    added = add_news_topic(user_id, "podcast", pid)
    name = PODCASTS[pid]["name"]
    if not added:
        return f"Ya recibes el resumen diario de {name}."
    return f"✅ Listo. Cada mañana, cuando salga el episodio, te mando el resumen de {name}."


def tool_unfollow_podcast(user_id: int, tool_input: dict) -> str:
    pid = resolve(tool_input.get("podcast", ""))
    if not pid:
        return "No encontré ese podcast entre los que sigues."
    from finmate.db.news_repo import remove_news_topic
    removed = remove_news_topic(user_id, "podcast", pid)
    name = PODCASTS[pid]["name"]
    return f"Listo, ya no te mando el resumen de {name}." if removed else f"No estabas siguiendo {name}."


def tool_get_podcast_summary(tool_input: dict) -> str:
    pid = resolve(tool_input.get("podcast", "")) or next(iter(PODCASTS))
    from finmate.podcasts.digest import get_last_digest
    msg = get_last_digest(pid)
    return msg or f"Todavía no tengo resumen de {PODCASTS[pid]['name']}: se genera cuando sale el episodio (días hábiles, ~7:15)."
