"""
Panel de administrador (/admin).

Mismo diseño que el panel de usuarios. Se entra solo con Google y solo con
los correos de ADMIN_EMAILS (por defecto claude.heymate@gmail.com).

Pestañas:
- Costos: suscripciones editables + consumo medido de Claude y WhatsApp.
- Usuarios: quién usa Finmate (inicio, último mensaje, mensajes enviados) y su acceso.
- Inbox: solicitudes de acceso de números nuevos (aprobar / rechazar) y feedback.
- Fuentes: de dónde se informa Finmate, con estado, prueba en vivo y notas.
"""
import datetime as dt
import functools
import logging
import secrets
from urllib.parse import urlencode

import httpx
from flask import Blueprint, g, jsonify, redirect, render_template, request, session, url_for

from config import settings

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, template_folder="templates")

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"

_PAGES = {
    "costos": "Costos",
    "usuarios": "Usuarios",
    "inbox": "Inbox",
    "fuentes": "Fuentes",
}


# ── Sesión ──────────────────────────────────────────────────────────────

def _redirect_uri() -> str:
    return f"{settings.PANEL_BASE_URL.rstrip('/')}/admin/oauth/callback"


def _is_admin_email(email: str) -> bool:
    return bool(email) and email.strip().lower() in settings.ADMIN_EMAILS


def current_admin():
    email = session.get("admin_email")
    return email if _is_admin_email(email or "") else None


def admin_page(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        if not current_admin():
            return redirect(url_for("admin.login"))
        return fn(*a, **k)
    return wrapper


def admin_api(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        email = current_admin()
        if not email:
            return jsonify({"error": "no_autenticado"}), 401
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.headers.get("X-Finmate") != "1":
            return jsonify({"error": "falta_encabezado_csrf"}), 403
        g.admin = email
        return fn(*a, **k)
    return wrapper


def _err(msg, code=400):
    return jsonify({"error": msg}), code


def _body() -> dict:
    return request.get_json(silent=True) or {}


@admin_bp.get("/login")
def login():
    if current_admin():
        return redirect(url_for("admin.costos"))
    return render_template("admin/login.html", configured=bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET),
                           dev_login=settings.ADMIN_DEV_LOGIN, error=request.args.get("error", ""),
                           redirect_uri=_redirect_uri(), admin_email=settings.ADMIN_EMAILS[0] if settings.ADMIN_EMAILS else "")


@admin_bp.get("/login/google")
def login_google():
    if not (settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET):
        return redirect(url_for("admin.login"))
    state = secrets.token_urlsafe(24)
    session["admin_oauth_state"] = state
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID, "redirect_uri": _redirect_uri(), "response_type": "code",
        "scope": "openid email profile", "state": state, "prompt": "select_account",
    }
    if settings.ADMIN_EMAILS:
        params["login_hint"] = settings.ADMIN_EMAILS[0]
    return redirect(f"{GOOGLE_AUTH}?{urlencode(params)}")


@admin_bp.get("/oauth/callback")
def oauth_callback():
    state = request.args.get("state", "")
    expected = session.pop("admin_oauth_state", None)
    if not expected or not secrets.compare_digest(state, expected):
        return redirect(url_for("admin.login", error="La sesión de Google venció. Intenta de nuevo."))
    code = request.args.get("code")
    if not code:
        return redirect(url_for("admin.login", error="Google no autorizó el ingreso."))
    try:
        tok = httpx.post(GOOGLE_TOKEN, timeout=10, data={
            "code": code, "client_id": settings.GOOGLE_OAUTH_CLIENT_ID, "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "redirect_uri": _redirect_uri(), "grant_type": "authorization_code"}).json()
        info = httpx.get(GOOGLE_USERINFO, timeout=10,
                         headers={"Authorization": f"Bearer {tok.get('access_token', '')}"}).json()
    except Exception as e:  # noqa: BLE001
        logger.error(f"Admin: error con Google OAuth: {e}")
        return redirect(url_for("admin.login", error="No pude verificar tu cuenta de Google."))
    email = (info.get("email") or "").lower()
    if not info.get("email_verified") or not _is_admin_email(email):
        logger.warning(f"Admin: intento de ingreso rechazado ({email or 'sin correo'})")
        return redirect(url_for("admin.login", error=f"La cuenta {email or ''} no tiene acceso al panel de administrador."))
    session["admin_email"] = email
    session["admin_name"] = info.get("name") or email
    session.permanent = True
    logger.info(f"Admin: ingreso de {email}")
    return redirect(url_for("admin.costos"))


@admin_bp.post("/api/dev-login")
def dev_login():
    if not settings.ADMIN_DEV_LOGIN:
        return _err("deshabilitado", 404)
    email = (_body().get("email") or "").lower()
    if not _is_admin_email(email):
        return _err("Correo sin acceso", 403)
    session["admin_email"] = email
    session["admin_name"] = email
    return jsonify({"ok": True})


@admin_bp.post("/api/logout")
def logout():
    session.pop("admin_email", None)
    session.pop("admin_name", None)
    return jsonify({"ok": True})


# ── Páginas ─────────────────────────────────────────────────────────────

def _render(page: str):
    return render_template(f"admin/{page}.html", page=page, title=_PAGES[page],
                           admin_email=current_admin(), admin_name=session.get("admin_name") or current_admin())


@admin_bp.get("/")
@admin_page
def costos():
    return _render("costos")


@admin_bp.get("/usuarios")
@admin_page
def usuarios():
    return _render("usuarios")


@admin_bp.get("/inbox")
@admin_page
def inbox():
    return _render("inbox")


@admin_bp.get("/fuentes")
@admin_page
def fuentes():
    return _render("fuentes")


# ── API: resumen y costos ───────────────────────────────────────────────

PRICES_KEY = "admin:prices"
DEFAULT_PRICES = {
    "claude": {"claude-haiku-5-5": {"in": 0.10, "out": 0.50}},  # USD por millón de tokens
    "whatsapp_template_usd": None,  # USD por mensaje de plantilla (Meta, Chile, categoría Utilidad)
}


def _prices() -> dict:
    from finmate.db.state_store import load_json

    p = load_json(PRICES_KEY, None) or {}
    out = {"claude": dict(DEFAULT_PRICES["claude"]), "whatsapp_template_usd": DEFAULT_PRICES["whatsapp_template_usd"]}
    out["claude"].update(p.get("claude") or {})
    if "whatsapp_template_usd" in p:
        out["whatsapp_template_usd"] = p["whatsapp_template_usd"]
    return out


def _usage_with_costs(month: str = None) -> dict:
    from finmate.services.usage import get_usage

    u = get_usage(month)
    prices = _prices()
    models, total = [], 0.0
    known = True
    for model, d in sorted(u["claude"].items()):
        pr = prices["claude"].get(model)
        cost = None
        if pr and pr.get("in") is not None and pr.get("out") is not None:
            cost = ((d.get("input_tokens", 0) + 1.25 * d.get("cache_write_tokens", 0) + 0.1 * d.get("cache_read_tokens", 0)) * pr["in"]
                    + d.get("output_tokens", 0) * pr["out"]) / 1_000_000
            total += cost
        else:
            known = False
        models.append({"model": model, **d, "cost_usd": None if cost is None else round(cost, 4),
                       "price_in": (pr or {}).get("in"), "price_out": (pr or {}).get("out")})
    wa = u["whatsapp"]
    wa_cost = None
    if prices["whatsapp_template_usd"] is not None:
        wa_cost = round((wa.get("template", 0) or 0) * float(prices["whatsapp_template_usd"]), 4)
    return {"month": u["month"], "claude": models, "claude_cost_usd": round(total, 4), "claude_cost_complete": known,
            "whatsapp": {"text": wa.get("text", 0), "template": wa.get("template", 0), "failed": wa.get("failed", 0),
                         "cost_usd": wa_cost, "template_price_usd": prices["whatsapp_template_usd"]}}


@admin_bp.get("/api/resumen")
@admin_api
def api_resumen():
    from finmate.admin import subscriptions as subs

    data = subs.list_subscriptions()
    counts = _user_counts()
    return jsonify({"subscriptions": data, "monthly_fixed": subs.monthly_totals(data),
                    "usage": _usage_with_costs(request.args.get("mes")), "users": counts,
                    "feedback_new": _feedback_new_count()})


@admin_bp.post("/api/suscripciones")
@admin_api
def api_sub_upsert():
    from finmate.admin import subscriptions as subs

    try:
        data = subs.upsert(_body())
    except ValueError as e:
        return _err(str(e))
    return jsonify({"subscriptions": data, "monthly_fixed": subs.monthly_totals(data)})


@admin_bp.delete("/api/suscripciones/<sid>")
@admin_api
def api_sub_delete(sid):
    from finmate.admin import subscriptions as subs

    data = subs.delete(sid)
    return jsonify({"subscriptions": data, "monthly_fixed": subs.monthly_totals(data)})


@admin_bp.put("/api/precios")
@admin_api
def api_prices():
    from finmate.db.state_store import load_json, save_json

    b = _body()
    p = load_json(PRICES_KEY, {}) or {}
    if "model" in b:
        model = str(b["model"]).strip()[:60]
        try:
            pin, pout = float(b.get("in")), float(b.get("out"))
        except (TypeError, ValueError):
            return _err("Precios inválidos (USD por millón de tokens).")
        if pin < 0 or pout < 0:
            return _err("Los precios no pueden ser negativos.")
        p.setdefault("claude", {})[model] = {"in": pin, "out": pout}
    if "whatsapp_template_usd" in b:
        v = b["whatsapp_template_usd"]
        try:
            p["whatsapp_template_usd"] = None if v in (None, "") else max(0.0, float(v))
        except (TypeError, ValueError):
            return _err("Precio de plantilla inválido.")
    save_json(PRICES_KEY, p)
    return jsonify(_usage_with_costs())


# ── API: usuarios ───────────────────────────────────────────────────────

def _user_rows():
    from sqlalchemy import case, func

    from finmate.db.models import ConversationTurn, User, get_session

    s = get_session()
    try:
        is_user = case((ConversationTurn.role == "user", 1), else_=0)
        q = (s.query(User, func.coalesce(func.sum(is_user), 0),
                     func.max(case((ConversationTurn.role == "user", ConversationTurn.timestamp), else_=None)))
             .outerjoin(ConversationTurn, ConversationTurn.user_id == User.id)
             .group_by(User.id)
             .order_by(User.created_at.desc()))
        rows = []
        for u, n, last in q.all():
            rows.append({"id": u.id, "name": u.name or "", "phone": u.phone.replace("whatsapp:", ""),
                         "created_at": u.created_at.isoformat() if u.created_at else None,
                         "last_message_at": last.isoformat() if last else None, "messages": int(n or 0),
                         "status": u.access_status or "approved"})
        return rows
    finally:
        s.close()


def _user_counts() -> dict:
    try:
        rows = _user_rows()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Admin: no pude contar usuarios: {e}")
        return {}
    week = dt.datetime.utcnow() - dt.timedelta(days=7)
    return {
        "total": len(rows),
        "approved": sum(1 for r in rows if r["status"] == "approved"),
        "pending": sum(1 for r in rows if r["status"] == "pending"),
        "denied": sum(1 for r in rows if r["status"] == "denied"),
        "active_7d": sum(1 for r in rows if r["last_message_at"] and dt.datetime.fromisoformat(r["last_message_at"]) >= week),
        "messages": sum(r["messages"] for r in rows),
    }


@admin_bp.get("/api/usuarios")
@admin_api
def api_users():
    from finmate.db.repository import get_portfolio, get_watchlist

    rows = _user_rows()
    for r in rows:
        try:
            r["watchlist"] = len(get_watchlist(r["id"]))
            r["portfolio"] = len(get_portfolio(r["id"]))
        except Exception:
            r["watchlist"] = r["portfolio"] = None
    return jsonify({"users": rows, "counts": _user_counts()})


@admin_bp.post("/api/usuarios/<int:uid>/acceso")
@admin_api
def api_user_access(uid):
    """Aprobar, rechazar o volver a pendiente. Al aprobar se le avisa por WhatsApp."""
    from finmate.db.repository import set_access_status

    action = (_body().get("action") or "").lower()
    status = {"approve": "approved", "deny": "denied", "pending": "pending"}.get(action)
    if not status:
        return _err("Acción inválida (approve, deny o pending).")
    user = set_access_status(uid, status)
    if user is None:
        return _err("Usuario no encontrado.", 404)
    notified = None
    if status == "approved":
        try:
            from finmate.agent.setup_tools import set_onboarding_status

            set_onboarding_status(uid, "en_curso")
        except Exception:
            pass
        try:
            from finmate.whatsapp.messenger import WhatsAppMessenger

            nombre = f" {user.name.split()[0]}" if user.name else ""
            notified = WhatsAppMessenger().send_message(
                user.phone, f"¡Listo{nombre}! Ya tienes acceso a Finmate 🎉 Escríbeme cuando quieras y te ayudo a dejarlo configurado.")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Admin: no pude avisar a {user.phone}: {e}")
            notified = False
    logger.info(f"Admin {g.admin}: usuario {uid} → {status}")
    return jsonify({"ok": True, "status": status, "notified": notified})


# ── API: inbox (solicitudes + feedback) ─────────────────────────────────

def _feedback_new_count() -> int:
    try:
        from finmate.db.models import Feedback, get_session

        s = get_session()
        try:
            return s.query(Feedback).filter((Feedback.status.is_(None)) | (Feedback.status == "nuevo")).count()
        finally:
            s.close()
    except Exception:
        return 0


@admin_bp.get("/api/inbox")
@admin_api
def api_inbox():
    from finmate.db.models import ConversationTurn, Feedback, User, get_session

    s = get_session()
    try:
        pending = []
        for u in s.query(User).filter(User.access_status.in_(["pending", "denied"])).order_by(User.created_at.desc()).all():
            msgs = (s.query(ConversationTurn).filter_by(user_id=u.id, role="user")
                    .order_by(ConversationTurn.timestamp.desc()).limit(3).all())
            pending.append({"id": u.id, "name": u.name or "", "phone": u.phone.replace("whatsapp:", ""),
                            "status": u.access_status, "created_at": u.created_at.isoformat() if u.created_at else None,
                            "messages": [{"text": m.content[:300], "at": m.timestamp.isoformat()} for m in reversed(msgs)]})
        fbs = []
        for f, u in (s.query(Feedback, User).outerjoin(User, User.id == Feedback.user_id)
                     .order_by(Feedback.created_at.desc()).limit(200).all()):
            fbs.append({"id": f.id, "tipo": f.tipo, "rating": f.rating, "message": f.message,
                        "contact_ok": f.contact_ok, "created_at": f.created_at.isoformat() if f.created_at else None,
                        "status": f.status or "nuevo", "note": f.admin_note or "",
                        "user": {"name": (u.name if u else "") or "", "phone": u.phone.replace("whatsapp:", "") if u else ""}})
        return jsonify({"requests": pending, "feedback": fbs})
    finally:
        s.close()


@admin_bp.put("/api/feedback/<int:fid>")
@admin_api
def api_feedback_update(fid):
    from finmate.db.models import Feedback, get_session

    b = _body()
    s = get_session()
    try:
        f = s.get(Feedback, fid)
        if f is None:
            return _err("Feedback no encontrado.", 404)
        if "status" in b:
            if b["status"] not in ("nuevo", "en_curso", "resuelto", "descartado"):
                return _err("Estado inválido.")
            f.status = b["status"]
        if "note" in b:
            f.admin_note = str(b["note"] or "")[:2000]
        s.commit()
        return jsonify({"ok": True})
    finally:
        s.close()


# ── API: fuentes ────────────────────────────────────────────────────────

@admin_bp.get("/api/fuentes")
@admin_api
def api_sources():
    from finmate.admin import sources

    return jsonify({"sources": sources.catalog(), "ideas": sources.get_ideas()})


@admin_bp.post("/api/fuentes/<sid>/probar")
@admin_api
def api_source_test(sid):
    from finmate.admin import sources

    if not any(s["id"] == sid for s in sources.SOURCES):
        return _err("Fuente desconocida", 404)
    return jsonify(sources.test_source(sid))


@admin_bp.put("/api/fuentes/<sid>/nota")
@admin_api
def api_source_note(sid):
    from finmate.admin import sources

    try:
        sources.save_note(sid, _body().get("note", ""))
    except ValueError as e:
        return _err(str(e))
    return jsonify({"ok": True})
