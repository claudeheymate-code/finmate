"""Páginas del panel web (/panel/*).

Las páginas son livianas: traen la estructura y la marca, y el contenido lo
cargan desde /api/* con JavaScript (finmate/web/static/panel/panel.js).
"""
from flask import Blueprint, redirect, render_template, url_for

from config import settings
from finmate.web.auth import current_user, mask_phone

panel_bp = Blueprint(
    "panel", __name__, template_folder="templates", static_folder="static/panel", static_url_path="/static"
)

_PAGES = {
    "resumen": ("Resumen", "panel/resumen.html"),
    "inversiones": ("Mis inversiones", "panel/inversiones.html"),
    "gastos": ("Mis gastos", "panel/gastos.html"),
    "ajustes": ("Ajustes y personalidad", "panel/ajustes.html"),
}


def _render(page: str):
    user = current_user()
    if user is None:
        return redirect(url_for("panel.acceso"))
    title, template = _PAGES[page]
    return render_template(template, page=page, title=title, phone=mask_phone(user.phone),
                           initial=(user.name or "F")[:1].upper())


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


@panel_bp.get("/acceso")
def acceso():
    if current_user() is not None:
        return redirect(url_for("panel.resumen"))
    return render_template("panel/acceso.html", dev_login=settings.PANEL_DEV_LOGIN)
