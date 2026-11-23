"""
Bienvenida y configuración por chat.

Cuando alguien escribe por primera vez, Finmate se presenta y lo ayuda a
dejar el bot a su gusto: qué activos seguir (watchlist), su portafolio y
cada cuánto quiere recibir avisos. El estado de la bienvenida vive en la
tabla `kv_state` (clave `onboarding:<user_id>`).

`user_context()` arma un bloque corto con lo que el usuario ya tiene
configurado, para que el agente no pregunte lo que ya sabe.
"""
import datetime as dt
import logging

from finmate.db.state_store import load_json, save_json

logger = logging.getLogger(__name__)


def _key(user_id: int) -> str:
    return f"onboarding:{user_id}"


def onboarding_status(user_id: int) -> str:
    """'nuevo', 'en_curso' o 'listo'."""
    return (load_json(_key(user_id), {}) or {}).get("status", "nuevo")


def set_onboarding_status(user_id: int, status: str) -> None:
    data = load_json(_key(user_id), {}) or {}
    data["status"] = status
    data[f"{status}_at"] = dt.datetime.utcnow().isoformat(timespec="seconds")
    save_json(_key(user_id), data)


def start_onboarding_if_new(user_id: int, has_history: bool) -> str:
    """Marca la bienvenida como en curso si es el primer mensaje del usuario."""
    status = onboarding_status(user_id)
    if status == "nuevo":
        if has_history:
            # Usuarios de antes de que existiera la bienvenida: no se les repite.
            set_onboarding_status(user_id, "listo")
            return "listo"
        set_onboarding_status(user_id, "en_curso")
        return "en_curso"
    return status


def _safe(fn, default):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Contexto de usuario incompleto: {e}")
        return default


def user_context(user_id: int, name: str = "") -> str:
    """Resumen de la configuración actual del usuario (para el system prompt)."""
    from finmate.db.news_repo import get_economic_indicators, get_news_topics
    from finmate.db.repository import get_portfolio, get_watchlist
    from finmate.db.settings_repo import get_notification_settings

    watch = _safe(lambda: [s for s, _ in get_watchlist(user_id)], [])
    port = _safe(lambda: [s for s, _q, _p in get_portfolio(user_id)], [])
    topics = _safe(lambda: get_news_topics(user_id), [])
    podcasts = [v for t, v in topics if t == "podcast"]
    other_topics = [f"{t}:{v}" for t, v in topics if t != "podcast"]
    indicators = _safe(lambda: get_economic_indicators(user_id), [])
    notif = _safe(lambda: get_notification_settings(user_id), {})
    status = _safe(lambda: onboarding_status(user_id), "listo")

    def lst(xs):
        return ", ".join(xs) if xs else "nada todavía"

    lines = [
        f"- Nombre (perfil de WhatsApp): {name or 'desconocido'}",
        f"- Bienvenida: {status}",
        f"- Watchlist: {lst(watch)}",
        f"- Portafolio: {lst(port)}",
        f"- Podcasts que sigue: {lst(podcasts)}",
        f"- Temas de noticias: {lst(other_topics)}",
        f"- Indicadores económicos: {lst(indicators)}",
    ]
    if notif:
        lines.append(
            f"- Avisos: alerta de watchlist si un activo se mueve ±{notif.get('watchlist_threshold_pct')}% "
            f"en el día; hasta {notif.get('news_max_per_day')} avisos de noticias por día; resumen "
            f"semanal {'activado' if notif.get('weekly_summary_enabled') else 'desactivado'}; "
            f"resultados de empresas: {_EARN.get(notif.get('earnings_alerts'), '?')}; datos macro: "
            f"{'sí' if notif.get('macro_alerts') else 'no'}; noticias generales: "
            f"{'sí' if notif.get('market_news_alerts') else 'no'}."
        )
    return "\n".join(lines)


# ── Tools ───────────────────────────────────────────────────────────────

def tool_get_notification_settings(user_id: int) -> str:
    from finmate.db.settings_repo import get_notification_settings

    n = get_notification_settings(user_id)
    return (
        f"Alerta de watchlist: cuando un activo se mueve ±{n['watchlist_threshold_pct']:g}% en el día.\n"
        f"Avisos de noticias de tus activos: hasta {n['news_max_per_day']} por día "
        f"({'apagados' if n['news_max_per_day'] == 0 else 'activos'}).\n"
        f"Resumen semanal (domingo): {'activado' if n['weekly_summary_enabled'] else 'desactivado'}.\n"
        f"Resultados de empresas: {_EARN[n['earnings_alerts']]}.\n"
        f"Datos macro: {'sí' if n['macro_alerts'] else 'no'}. "
        f"Noticias generales del mercado: {'sí' if n['market_news_alerts'] else 'no'}."
    )


_EARN = {"off": "ninguno", "mine": "solo de tus activos", "all": "de todas las empresas"}


def tool_set_notification_settings(user_id: int, tool_input: dict) -> str:
    from finmate.db.settings_repo import set_notification_settings

    try:
        set_notification_settings(
            user_id,
            watchlist_threshold_pct=tool_input.get("watchlist_threshold_pct"),
            weekly_summary_enabled=tool_input.get("weekly_summary_enabled"),
            news_max_per_day=tool_input.get("news_max_per_day"),
            earnings_alerts=tool_input.get("earnings_alerts"),
            macro_alerts=tool_input.get("macro_alerts"),
            market_news_alerts=tool_input.get("market_news_alerts"),
        )
    except ValueError as e:
        return f"No pude guardar ese ajuste: {e}"
    return "Listo, guardado.\n" + tool_get_notification_settings(user_id)


def tool_onboarding(user_id: int, tool_input: dict) -> str:
    action = (tool_input.get("action") or "").lower()
    if action == "complete":
        set_onboarding_status(user_id, "listo")
        return "Bienvenida marcada como terminada."
    if action == "restart":
        set_onboarding_status(user_id, "en_curso")
        return "Bienvenida reiniciada: vuelve a guiar la configuración desde el principio."
    return "Acción no válida (usa 'complete' o 'restart')."


def tool_get_panel_link(user_id: int, _input: dict) -> str:
    from finmate.web.login_codes import LINK_TTL_MIN, panel_link

    return (f"Link de acceso al panel web (un solo uso, vence en {LINK_TTL_MIN} minutos): "
            f"{panel_link(user_id)}\nCompártelo tal cual con el usuario.")
