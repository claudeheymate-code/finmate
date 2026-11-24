"""Preferencias de avisos por usuario (panel web, etapa 1).

Si un usuario no tiene fila en `notification_settings`, se usan los valores
globales de config/settings.py, así nada cambia para quien nunca tocó sus
ajustes.
"""
import logging
from typing import Dict, Optional

from config.settings import NEWS_ALERTS_MAX_PER_USER_PER_DAY, WATCHLIST_ALERT_THRESHOLD_PCT

logger = logging.getLogger(__name__)

MIN_THRESHOLD = 0.5
MAX_THRESHOLD = 50.0
MAX_NEWS_PER_DAY = 10
EARNINGS_OPTIONS = ("off", "mine", "all")
DEFAULT_WORKDAY = ("08:30", "18:30")


def _clean_hhmm(value, label: str) -> str:
    """Acepta "8", "8:30", "08:30", "8.30" o "830" → "08:30"."""
    raw = str(value).strip().lower().replace("h", "").replace(".", ":").replace(" ", "")
    if raw.isdigit() and len(raw) in (3, 4):
        raw = raw[:-2] + ":" + raw[-2:]
    if raw.isdigit():
        raw += ":00"
    try:
        hh, mm = (int(x) for x in raw.split(":", 1))
    except ValueError:
        raise ValueError(f"La hora de {label} no se entiende ('{value}'). Usa el formato 08:30.")
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError(f"La hora de {label} no es válida ('{value}').")
    return f"{hh:02d}:{mm:02d}"


def _defaults() -> dict:
    return {
        "watchlist_threshold_pct": float(WATCHLIST_ALERT_THRESHOLD_PCT),
        "weekly_summary_enabled": True,
        "news_max_per_day": int(NEWS_ALERTS_MAX_PER_USER_PER_DAY),
        "earnings_alerts": "mine",
        "macro_alerts": False,
        "market_news_alerts": False,
        "workday_enabled": True,
        "workday_start": DEFAULT_WORKDAY[0],
        "workday_end": DEFAULT_WORKDAY[1],
        "workday_weekends": False,
    }


def get_notification_settings(user_id: int) -> dict:
    from finmate.db.models import NotificationSettings, get_session

    session = get_session()
    try:
        row = session.query(NotificationSettings).filter_by(user_id=user_id).one_or_none()
        out = _defaults()
        if row is not None:
            if row.watchlist_threshold_pct is not None:
                out["watchlist_threshold_pct"] = float(row.watchlist_threshold_pct)
            out["weekly_summary_enabled"] = bool(row.weekly_summary_enabled)
            if getattr(row, "news_max_per_day", None) is not None:
                out["news_max_per_day"] = int(row.news_max_per_day)
            if getattr(row, "earnings_alerts", None):
                out["earnings_alerts"] = row.earnings_alerts
            if getattr(row, "macro_alerts", None) is not None:
                out["macro_alerts"] = bool(row.macro_alerts)
            if getattr(row, "market_news_alerts", None) is not None:
                out["market_news_alerts"] = bool(row.market_news_alerts)
            if getattr(row, "workday_enabled", None) is not None:
                out["workday_enabled"] = bool(row.workday_enabled)
            if getattr(row, "workday_start", None):
                out["workday_start"] = row.workday_start
            if getattr(row, "workday_end", None):
                out["workday_end"] = row.workday_end
            if getattr(row, "workday_weekends", None) is not None:
                out["workday_weekends"] = bool(row.workday_weekends)
        return out
    finally:
        session.close()


def set_notification_settings(
    user_id: int,
    watchlist_threshold_pct: Optional[float] = None,
    weekly_summary_enabled: Optional[bool] = None,
    news_max_per_day: Optional[int] = None,
    earnings_alerts: Optional[str] = None,
    macro_alerts: Optional[bool] = None,
    market_news_alerts: Optional[bool] = None,
    workday_enabled: Optional[bool] = None,
    workday_start: Optional[str] = None,
    workday_end: Optional[str] = None,
    workday_weekends: Optional[bool] = None,
) -> dict:
    """Actualiza solo lo que se pasa. Valida el umbral (0,5% a 50%) y las horas de la jornada."""
    from finmate.db.models import NotificationSettings, get_session

    if watchlist_threshold_pct is not None:
        pct = float(watchlist_threshold_pct)
        if not (MIN_THRESHOLD <= pct <= MAX_THRESHOLD):
            raise ValueError(
                f"El umbral tiene que estar entre {MIN_THRESHOLD:g}% y {MAX_THRESHOLD:g}%."
            )
        watchlist_threshold_pct = pct
    if news_max_per_day is not None:
        n = int(news_max_per_day)
        if not (0 <= n <= MAX_NEWS_PER_DAY):
            raise ValueError(f"Los avisos de noticias por día van de 0 a {MAX_NEWS_PER_DAY}.")
        news_max_per_day = n
    if earnings_alerts is not None and earnings_alerts not in EARNINGS_OPTIONS:
        raise ValueError("Resultados de empresas: elige 'off' (ninguno), 'mine' (solo mis activos) o 'all' (todas).")
    if workday_start is not None:
        workday_start = _clean_hhmm(workday_start, "inicio")
    if workday_end is not None:
        workday_end = _clean_hhmm(workday_end, "término")
    if workday_start is not None or workday_end is not None:
        cur = get_notification_settings(user_id)
        st, en = workday_start or cur["workday_start"], workday_end or cur["workday_end"]
        if st == en:
            raise ValueError("La jornada tiene que empezar y terminar a horas distintas.")

    session = get_session()
    try:
        row = session.query(NotificationSettings).filter_by(user_id=user_id).one_or_none()
        if row is None:
            row = NotificationSettings(user_id=user_id, weekly_summary_enabled=True)
            session.add(row)
        if watchlist_threshold_pct is not None:
            row.watchlist_threshold_pct = watchlist_threshold_pct
        if weekly_summary_enabled is not None:
            row.weekly_summary_enabled = bool(weekly_summary_enabled)
        if news_max_per_day is not None:
            row.news_max_per_day = news_max_per_day
        if earnings_alerts is not None:
            row.earnings_alerts = earnings_alerts
        if macro_alerts is not None:
            row.macro_alerts = bool(macro_alerts)
        if market_news_alerts is not None:
            row.market_news_alerts = bool(market_news_alerts)
        if workday_enabled is not None:
            row.workday_enabled = bool(workday_enabled)
        if workday_start is not None:
            row.workday_start = workday_start
        if workday_end is not None:
            row.workday_end = workday_end
        if workday_weekends is not None:
            row.workday_weekends = bool(workday_weekends)
        session.commit()
    finally:
        session.close()
    return get_notification_settings(user_id)


def get_thresholds_by_user() -> Dict[int, float]:
    """{user_id: umbral} solo de quienes lo personalizaron (para watchlist_alerts)."""
    from finmate.db.models import NotificationSettings, get_session

    session = get_session()
    try:
        rows = (
            session.query(NotificationSettings)
            .filter(NotificationSettings.watchlist_threshold_pct.isnot(None))
            .all()
        )
        return {r.user_id: float(r.watchlist_threshold_pct) for r in rows}
    finally:
        session.close()


def weekly_summary_enabled_for_phone(phone: str) -> bool:
    """True salvo que el usuario de ese teléfono lo haya desactivado.
    Ante cualquier error (p. ej. sin base de datos) devuelve True, para no
    dejar de mandar el resumen que ya funciona en producción."""
    try:
        from finmate.db.models import NotificationSettings, User, get_session

        session = get_session()
        try:
            row = (
                session.query(NotificationSettings)
                .join(User, User.id == NotificationSettings.user_id)
                .filter(User.phone == phone)
                .one_or_none()
            )
            return True if row is None else bool(row.weekly_summary_enabled)
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"No pude leer preferencias de resumen semanal ({phone}): {e}")
        return True


def get_news_limits_by_user() -> Dict[int, int]:
    """{user_id: avisos de noticias por día} de quienes lo personalizaron."""
    try:
        from finmate.db.models import NotificationSettings, get_session

        session = get_session()
    except Exception:
        return {}
    try:
        rows = (
            session.query(NotificationSettings)
            .filter(NotificationSettings.news_max_per_day.isnot(None))
            .all()
        )
        return {r.user_id: int(r.news_max_per_day) for r in rows}
    except Exception as e:
        logger.warning(f"No pude leer los límites de noticias por usuario: {e}")
        return {}
    finally:
        session.close()


# ── Destinatarios de los avisos generales ──────────────────────────────

def _all_users_with_settings():
    """[(user_id, phone, settings_dict)] de todos los usuarios."""
    from finmate.db.models import NotificationSettings, User, get_session

    session = get_session()
    try:
        rows = (
            session.query(User, NotificationSettings)
            .outerjoin(NotificationSettings, NotificationSettings.user_id == User.id)
            .all()
        )
        out = []
        for user, ns in rows:
            if (getattr(user, "access_status", None) or "approved") != "approved":
                continue  # sin acceso aprobado no recibe avisos
            d = _defaults()
            if ns is not None:
                d["weekly_summary_enabled"] = bool(ns.weekly_summary_enabled)
                if ns.earnings_alerts:
                    d["earnings_alerts"] = ns.earnings_alerts
                if ns.macro_alerts is not None:
                    d["macro_alerts"] = bool(ns.macro_alerts)
                if ns.market_news_alerts is not None:
                    d["market_news_alerts"] = bool(ns.market_news_alerts)
            out.append((user.id, user.phone, d))
        return out
    finally:
        session.close()


def recipients_for(kind: str, symbol: Optional[str] = None) -> list:
    """Teléfonos que quieren un aviso general, según lo que eligió cada uno.

    kind: "weekly" (resumen semanal), "macro" (datos macro publicados),
    "market_news" (noticias generales del mercado) o "earnings" (resultados
    de una empresa: "all" los recibe todos; "mine" solo si `symbol` está en
    su portafolio o watchlist).
    """
    try:
        users = _all_users_with_settings()
    except Exception as e:
        logger.warning(f"No pude leer destinatarios de avisos ({kind}): {e}")
        return []
    if kind == "weekly":
        return [p for _u, p, d in users if d["weekly_summary_enabled"]]
    if kind == "macro":
        return [p for _u, p, d in users if d["macro_alerts"]]
    if kind == "market_news":
        return [p for _u, p, d in users if d["market_news_alerts"]]
    if kind == "earnings":
        sym = (symbol or "").upper()
        out = []
        for uid, phone, d in users:
            mode = d["earnings_alerts"]
            if mode == "all":
                out.append(phone)
            elif mode == "mine" and sym and sym in _user_symbols(uid):
                out.append(phone)
        return out
    return []


def _user_symbols(user_id: int) -> set:
    from finmate.db.repository import get_portfolio, get_watchlist

    try:
        syms = {s.upper() for s, _ in get_watchlist(user_id)}
        syms |= {s.upper() for s, _q, _p in get_portfolio(user_id)}
        return syms
    except Exception:
        return set()


def migrate_legacy_recipients(phones) -> int:
    """Una sola vez: quienes estaban en la lista fija WHATSAPP_RECIPIENTS
    quedan con todos los avisos generales activados y siguiendo Primer Click,
    para que no pierdan lo que ya recibían. Después lo maneja cada uno."""
    from finmate.db.state_store import load_json, save_json

    flag = "migration:legacy_recipients"
    if (load_json(flag, {}) or {}).get("done"):
        return 0
    from finmate.db.news_repo import add_news_topic
    from finmate.db.repository import find_user_by_phone

    n = 0
    for phone in phones or []:
        user = find_user_by_phone(phone)
        if user is None:
            continue
        try:
            set_notification_settings(user.id, earnings_alerts="all", macro_alerts=True,
                                      market_news_alerts=True, weekly_summary_enabled=True)
            add_news_topic(user.id, "podcast", "primer_click")
            n += 1
        except Exception as e:
            logger.warning(f"No pude migrar avisos de {phone}: {e}")
    save_json(flag, {"done": True, "migrated": n})
    logger.info(f"Avisos generales: {n} usuario(s) de la lista fija migrados a preferencias propias.")
    return n
