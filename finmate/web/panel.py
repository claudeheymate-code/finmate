"""Páginas del panel web (/panel/*).

Las páginas son livianas: traen la estructura y la marca, y el contenido lo
cargan desde /api/* con JavaScript (finmate/web/static/panel/panel.js).
"""
from flask import Blueprint, redirect, render_template, request, url_for

from config import settings
from finmate.web.auth import current_user, login_user, mask_phone

panel_bp = Blueprint(
    "panel", __name__, template_folder="templates", static_folder="static/panel", static_url_path="/static"
)

_PAGES = {
    "resumen": ("Resumen", "panel/resumen.html"),
    "inversiones": ("Mis inversiones", "panel/inversiones.html"),
    "gastos": ("Mis gastos", "panel/gastos.html"),
    "ajustes": ("Ajustes y personalidad", "panel/ajustes.html"),
    "feedback": ("Feedback", "panel/feedback.html"),
}


def _render(page: str):
    user = current_user()
    if user is None:
        return redirect(url_for("panel.acceso"))
    title, template = _PAGES[page]
    return render_template(template, page=page, title=title, phone=mask_phone(user.phone),
                           initial=(user.name or "F")[:1].upper(), panes=list(_PAGES))


@panel_bp.get("/")
def resumen():
    return _render("resumen")


@panel_bp.get("/inversiones")
def inversiones():
    return _render("inversiones")


@panel_bp.get("/gastos")
def gastos():
    return _render("gastos")


@panel_bp.get("/ajustes")
def ajustes():
    return _render("ajustes")


@panel_bp.get("/feedback")
def feedback():
    return _render("feedback")


@panel_bp.get("/acceso")
def acceso():
    if current_user() is not None:
        return redirect(url_for("panel.resumen"))
    return render_template("panel/acceso.html", dev_login=settings.PANEL_DEV_LOGIN)


@panel_bp.get("/entrar")
def entrar():
    """Link de acceso que manda el bot por WhatsApp (un solo uso, 15 min)."""
    from finmate.db.models import User, get_session
    from finmate.web.login_codes import consume_link_token

    uid = consume_link_token(request.args.get("t", ""))
    if uid is None:
        return render_template("panel/acceso.html", dev_login=settings.PANEL_DEV_LOGIN,
                               link_error="Ese link ya se usó o venció. Pídele uno nuevo a Finmate o entra con tu número.")
    s = get_session()
    try:
        user = s.get(User, uid)
    finally:
        s.close()
    from finmate.db.repository import is_approved

    if user is None or not is_approved(user):
        return redirect(url_for("panel.acceso"))
    login_user(user)
    return redirect(url_for("panel.resumen"))
