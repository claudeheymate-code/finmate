"""API JSON del panel web (/api/*).

Cada endpoint reutiliza las mismas funciones de `finmate/db/` y
`finmate/services/` que usan las tools del bot, así que lo que se cambia aquí
lo ve el bot en el próximo mensaje y al revés. Todas las consultas se filtran
por el usuario de la sesión: nadie ve datos de otro.
"""
import datetime as dt
import logging
import re

from flask import Blueprint, g, jsonify, request

from config import settings
from finmate.db import finance_repo, news_repo, personality_repo, repository, settings_repo
from finmate.services import portfolio as portfolio_service
from finmate.services import quotes
from finmate.web.auth import (
    api_login_required,
    login_user,
    logout_user,
    mask_phone,
    normalize_phone,
)

logger = logging.getLogger(__name__)
api_bp = Blueprint("api", __name__)

_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")
_TONOS = {"profesional", "casual", "amigo"}
_PERSONALITY_INT = ("humor", "sarcasmo", "frecuencia_chistes", "nivel_conversador")
_NEWS_TIPOS = ("ticker", "sector", "pais", "keyword")


def _err(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _symbol(raw) -> str:
    s = (raw or "").strip().upper()
    return s if _SYMBOL_RE.match(s) else ""


def _num(raw):
    if raw is None or raw == "":
        return None
    try:
        return float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _year_month():
    today = dt.date.today()
    try:
        year = int(request.args.get("anio") or today.year)
        month = int(request.args.get("mes") or today.month)
    except ValueError:
        year, month = today.year, today.month
    if not (1 <= month <= 12):
        month = today.month
    return year, month


# ------------------------------------------------------------------
# Sesión
# ------------------------------------------------------------------
@api_bp.post("/auth/dev-login")
def dev_login():
    """Acceso de desarrollo sin código. Solo si PANEL_DEV_LOGIN=true."""
    if not settings.PANEL_DEV_LOGIN:
        return _err("deshabilitado", 404)
    phone = normalize_phone(_body().get("phone", ""))
    if not phone:
        return _err("Número inválido. Usa el formato +56 9 1234 5678.")
    user = repository.get_or_create_user(phone)
    login_user(user)
    return jsonify({"ok": True})


@api_bp.post("/auth/request-code")
def request_code():
    """Manda un código de 6 dígitos al WhatsApp del usuario."""
    from finmate.web import login_codes
    from finmate.whatsapp.messenger import WhatsAppMessenger

    phone = normalize_phone(_body().get("phone", ""))
    if not phone:
        return _err("Número inválido. Usa el formato +56 9 1234 5678.")
    user = repository.find_user_by_phone(phone)
    if user is None:
        from finmate.security.guard import note_unknown_number

        note_unknown_number(phone)
        return _err("Ese número todavía no usa Finmate. Escríbele \"hola\" a Finmate por WhatsApp y vuelve a intentar.", 404)
    if not repository.is_approved(user):
        return _err("Tu acceso a Finmate todavía no está aprobado. Te avisaremos por WhatsApp.", 403)
    code = login_codes.create_code(phone)
    if code is None:
        return _err("Ya te mandamos un código. Espera un minuto antes de pedir otro.", 429)
    ok = WhatsAppMessenger().send_message(
        phone, f"Tu código para entrar al panel de Finmate es *{code}*. Vence en 10 minutos. Si no lo pediste, ignora este mensaje.")
    if not ok:
        return _err("No pude mandarte el código. Escríbele \"hola\" a Finmate por WhatsApp (WhatsApp solo deja "
                    "mandarte mensajes si le escribiste en las últimas 24 horas) y vuelve a intentar.", 502)
    return jsonify({"ok": True, "phone": mask_phone(phone)})


@api_bp.post("/auth/verify-code")
def verify_code():
    from finmate.web import login_codes

    b = _body()
    phone = normalize_phone(b.get("phone", ""))
    code = str(b.get("code", "")).strip()
    if not phone or not code.isdigit() or len(code) != 6:
        return _err("Escribe el código de 6 dígitos que te llegó por WhatsApp.")
    if not login_codes.verify_code(phone, code):
        from finmate.security.guard import note_login_failure

        note_login_failure(phone)
        return _err("Código incorrecto o vencido. Pide uno nuevo.", 401)
    user = repository.find_user_by_phone(phone)
    if user is None:
        return _err("No encontré tu cuenta.", 404)
    login_user(user)
    return jsonify({"ok": True})


@api_bp.post("/auth/logout")
def logout():
    logout_user()
    return jsonify({"ok": True})


@api_bp.get("/me")
@api_login_required
def me():
    u = g.user
    return jsonify({"id": u.id, "name": u.name, "phone": mask_phone(u.phone)})


# ------------------------------------------------------------------
# Resumen
# ------------------------------------------------------------------
@api_bp.get("/resumen")
@api_login_required
def resumen():
    uid = g.user.id
    pf = portfolio_service.compute_portfolio(uid)
    year, month = _year_month()
    py, pm = finance_repo.previous_month(year, month)
    cur = finance_repo.month_breakdown(uid, year, month)
    prev = finance_repo.month_breakdown(uid, py, pm)
    top_cat = max(cur["categories"], key=lambda c: c["amount"]) if cur["total_gastos"] else None

    watch = []
    for symbol, note in repository.get_watchlist(uid):
        q = quotes.get_quote(symbol) or {}
        watch.append({"symbol": symbol, "note": note, "price": q.get("price"), "change_pct": q.get("change_pct")})

    history = repository.get_recent_history(uid, limit=4)
    return jsonify({
        "portfolio": {
            "totals": pf["totals"],
            "top_positions": pf["positions"][:3],
            "top_winners": pf["top_winners"],
        },
        "watchlist": watch,
        "finanzas": {
            "year": year, "month": month,
            "total_gastos": cur["total_gastos"], "count": cur["count"],
            "prev_total_gastos": prev["total_gastos"],
            "diff": cur["total_gastos"] - prev["total_gastos"],
            "top_category": top_cat["name"] if top_cat else None,
        },
        "seguimientos": _seguimientos_payload(uid),
        "avisos": settings_repo.get_notification_settings(uid),
        "chat": [{"role": r, "content": c} for r, c in history],
    })


# ------------------------------------------------------------------
# Portafolio y watchlist
# ------------------------------------------------------------------
@api_bp.get("/portafolio")
@api_login_required
def portafolio_get():
    return jsonify(portfolio_service.compute_portfolio(g.user.id))


@api_bp.post("/portafolio")
@api_login_required
def portafolio_add():
    b = _body()
    symbol = _symbol(b.get("symbol"))
    qty = _num(b.get("quantity"))
    avg = _num(b.get("avg_cost"))
    if not symbol:
        return _err("Símbolo inválido (ej: AAPL, BRK.B).")
    if qty is None or qty <= 0:
        return _err("La cantidad tiene que ser mayor a cero.")
    if avg is not None and avg <= 0:
        return _err("El precio promedio tiene que ser mayor a cero.")
    h = repository.add_or_update_holding(g.user.id, symbol, qty, avg)
    if h is None:
        return _err("No se pudo agregar la posición.", 500)
    return jsonify({"ok": True, "symbol": h.symbol, "quantity": h.quantity, "avg_cost": h.avg_cost}), 201


@api_bp.patch("/portafolio/<symbol>")
@api_login_required
def portafolio_classify(symbol):
    b = _body()
    asset_class = b.get("asset_class")
    sector = (b.get("sector") or "").strip()[:60] or None
    if asset_class and asset_class not in portfolio_service.ASSET_CLASSES:
        return _err("Clase de activo inválida (Renta variable o Renta fija).")
    ok = repository.set_holding_classification(g.user.id, _symbol(symbol), asset_class, sector)
    return jsonify({"ok": True}) if ok else _err("No tienes esa posición.", 404)


@api_bp.delete("/portafolio/<symbol>")
@api_login_required
def portafolio_delete(symbol):
    ok = repository.remove_holding(g.user.id, _symbol(symbol))
    return jsonify({"ok": True}) if ok else _err("No tienes esa posición.", 404)


@api_bp.get("/watchlist")
@api_login_required
def watchlist_get():
    out = []
    thr = settings_repo.get_notification_settings(g.user.id)["watchlist_threshold_pct"]
    for symbol, note in repository.get_watchlist(g.user.id):
        q = quotes.get_quote(symbol) or {}
        out.append({"symbol": symbol, "note": note, "price": q.get("price"),
                    "change_pct": q.get("change_pct"), "threshold_pct": thr})
    return jsonify({"items": out})


@api_bp.post("/watchlist")
@api_login_required
def watchlist_add():
    symbol = _symbol(_body().get("symbol"))
    if not symbol:
        return _err("Símbolo inválido (ej: NVDA).")
    repository.add_to_watchlist(g.user.id, symbol, (_body().get("note") or None))
    return jsonify({"ok": True, "symbol": symbol}), 201


@api_bp.delete("/watchlist/<symbol>")
@api_login_required
def watchlist_delete(symbol):
    ok = repository.remove_from_watchlist(g.user.id, _symbol(symbol))
    return jsonify({"ok": True}) if ok else _err("Ese activo no estaba en tu watchlist.", 404)


@api_bp.get("/mercado/explicar/<symbol>")
@api_login_required
def explicar(symbol):
    from finmate.agent.market_tools import _get_news, _get_quote

    symbol = _symbol(symbol)
    if not symbol:
        return _err("Símbolo inválido.")
    q = _get_quote(symbol)
    if not q or q.get("price") is None:
        return _err(f"No hay datos de {symbol} ahora.", 404)
    news = [{"headline": n.get("headline", ""), "source": n.get("source", ""), "url": n.get("url", "")}
            for n in _get_news(symbol)]
    return jsonify({"symbol": symbol, **q, "news": news})


# ------------------------------------------------------------------
# Finanzas personales
# ------------------------------------------------------------------
def _cats_payload(uid):
    return {"categories": finance_repo.get_categories(uid), "all": finance_repo.category_settings(uid)}


@api_bp.get("/finanzas/categorias")
@api_login_required
def finanzas_categorias():
    return jsonify(_cats_payload(g.user.id))


@api_bp.post("/finanzas/categorias")
@api_login_required
def finanzas_categoria_agregar():
    ok, msg = finance_repo.add_user_category(g.user.id, _body().get("name", ""))
    if not ok:
        return _err(msg)
    return jsonify({**_cats_payload(g.user.id), "added": msg}), 201


@api_bp.put("/finanzas/categorias")
@api_login_required
def finanzas_categoria_activar():
    """Saca (active=false) o vuelve a poner (active=true) una categoría.
    Los gastos ya registrados en ella no se tocan."""
    b = _body()
    name = str(b.get("name") or "")
    if finance_repo._same(name, finance_repo.FALLBACK_CATEGORY):
        return _err("Otros siempre queda disponible.")
    if not finance_repo.set_category_active(g.user.id, name, bool(b.get("active"))):
        return _err("Categoría no encontrada.", 404)
    return jsonify(_cats_payload(g.user.id))


@api_bp.get("/finanzas/resumen")
@api_login_required
def finanzas_resumen():
    year, month = _year_month()
    py, pm = finance_repo.previous_month(year, month)
    return jsonify({
        "actual": finance_repo.month_breakdown(g.user.id, year, month),
        "anterior": finance_repo.month_breakdown(g.user.id, py, pm),
        "anio": finance_repo.year_to_date_breakdown(g.user.id, year, month),
    })


@api_bp.get("/finanzas/movimientos")
@api_login_required
def finanzas_movimientos():
    year, month = _year_month()
    cat = request.args.get("categoria") or None
    return jsonify({"items": finance_repo.list_transactions(g.user.id, year, month, cat)})


@api_bp.post("/finanzas/movimientos")
@api_login_required
def finanzas_crear():
    b = _body()
    tipo = (b.get("tipo") or "gasto").lower()
    amount = _num(b.get("amount"))
    category = b.get("category") or ""
    if tipo not in ("gasto", "ingreso"):
        return _err("Tipo inválido (gasto o ingreso).")
    if amount is None or amount <= 0:
        return _err("El monto tiene que ser mayor a cero.")
    resolved = finance_repo.resolve_category(g.user.id, category)
    if tipo == "gasto" and not resolved:
        return _err("Elige una categoría.")
    category = resolved or finance_repo.FALLBACK_CATEGORY
    date = None
    if b.get("date"):
        try:
            date = dt.date.fromisoformat(b["date"])
        except ValueError:
            return _err("Fecha inválida (AAAA-MM-DD).")
    tx = finance_repo.add_transaction(
        user_id=g.user.id,
        amount=-abs(amount) if tipo == "gasto" else abs(amount),
        category=category,
        description=(b.get("description") or "").strip()[:500],
        date=date,
        occasion=(b.get("occasion") or "").strip()[:200],
        merchant=(b.get("merchant") or "").strip()[:200],
    )
    return jsonify(finance_repo.tx_to_dict(tx)), 201


@api_bp.patch("/finanzas/movimientos/<int:tx_id>")
@api_login_required
def finanzas_editar(tx_id):
    b = _body()
    fields = {}
    if "category" in b:
        resolved = finance_repo.resolve_category(g.user.id, b["category"])
        if not resolved:
            return _err("Categoría inválida.")
        fields["category"] = resolved
    for k, limit in (("occasion", 200), ("description", 500), ("merchant", 200)):
        if k in b:
            fields[k] = (b.get(k) or "").strip()[:limit]
    tx = finance_repo.update_transaction(g.user.id, tx_id, **fields)
    return jsonify(tx) if tx else _err("Movimiento no encontrado.", 404)


@api_bp.delete("/finanzas/movimientos/<int:tx_id>")
@api_login_required
def finanzas_borrar(tx_id):
    ok = finance_repo.delete_transaction(g.user.id, tx_id)
    return jsonify({"ok": True}) if ok else _err("Movimiento no encontrado.", 404)


# ------------------------------------------------------------------
# Personalidad, seguimientos y avisos
# ------------------------------------------------------------------
@api_bp.get("/personalidad")
@api_login_required
def personalidad_get():
    return jsonify(personality_repo.get_personality(g.user.id))


@api_bp.put("/personalidad")
@api_login_required
def personalidad_put():
    b = _body()
    changes = {}
    for k in _PERSONALITY_INT:
        if k in b:
            try:
                v = int(b[k])
            except (TypeError, ValueError):
                return _err(f"{k} tiene que ser un número de 1 a 10.")
            if not 1 <= v <= 10:
                return _err(f"{k} tiene que estar entre 1 y 10.")
            changes[k] = v
    if "tono" in b:
        if b["tono"] not in _TONOS:
            return _err("Tono inválido (profesional, casual o amigo).")
        changes["tono"] = b["tono"]
    if not changes:
        return _err("No hay nada para cambiar.")
    return jsonify(personality_repo.set_personality(g.user.id, **changes))


def _seguimientos_payload(uid: int) -> dict:
    from finmate.data_sources.economic_calendar import INDICATOR_CATALOG

    inds = []
    for code in news_repo.get_economic_indicators(uid):
        meta = INDICATOR_CATALOG.get(code, {})
        inds.append({"code": code, "name": meta.get("name", code), "freq": meta.get("freq", ""),
                     "relevance": meta.get("relevance", ""), "country": meta.get("country", "")})
    return {
        "temas": [{"tipo": t, "valor": v} for t, v in news_repo.get_news_topics(uid)],
        "indicadores": inds,
    }


@api_bp.get("/seguimientos")
@api_login_required
def seguimientos_get():
    from finmate.data_sources.economic_calendar import list_all_indicators

    return jsonify({**_seguimientos_payload(g.user.id), "catalogo": list_all_indicators()})


@api_bp.post("/seguimientos")
@api_login_required
def seguimientos_add():
    from finmate.data_sources.economic_calendar import INDICATOR_CATALOG

    b = _body()
    tipo = (b.get("tipo") or "").lower().strip()
    valor = (b.get("valor") or "").strip()[:200]
    if not valor:
        return _err("Falta qué seguir.")
    if tipo == "indicador":
        code = valor.upper()
        if code not in INDICATOR_CATALOG:
            return _err("Indicador desconocido.")
        news_repo.add_economic_indicator(g.user.id, code, INDICATOR_CATALOG[code]["country"])
    else:
        if tipo not in _NEWS_TIPOS:
            tipo = "keyword"
        if tipo == "ticker":
            valor = valor.upper()
        news_repo.add_news_topic(g.user.id, tipo, valor)
    return jsonify(_seguimientos_payload(g.user.id)), 201


@api_bp.delete("/seguimientos")
@api_login_required
def seguimientos_delete():
    b = _body()
    tipo = (b.get("tipo") or "").lower().strip()
    valor = (b.get("valor") or "").strip()
    if tipo == "indicador":
        ok = news_repo.remove_economic_indicator(g.user.id, valor.upper())
    else:
        ok = news_repo.remove_news_topic(g.user.id, tipo, valor)
    return jsonify(_seguimientos_payload(g.user.id)) if ok else _err("No lo estabas siguiendo.", 404)


@api_bp.get("/avisos")
@api_login_required
def avisos_get():
    return jsonify(settings_repo.get_notification_settings(g.user.id))


@api_bp.put("/avisos")
@api_login_required
def avisos_put():
    b = _body()
    thr = _num(b.get("watchlist_threshold_pct")) if "watchlist_threshold_pct" in b else None
    weekly = b.get("weekly_summary_enabled") if "weekly_summary_enabled" in b else None
    if weekly is not None and not isinstance(weekly, bool):
        return _err("weekly_summary_enabled tiene que ser true o false.")
    news = None
    if "news_max_per_day" in b:
        news = b.get("news_max_per_day")
        if isinstance(news, bool) or not isinstance(news, int):
            return _err("news_max_per_day tiene que ser un número entero de 0 a 10.")
    flags = {}
    for k in ("macro_alerts", "market_news_alerts"):
        if k in b:
            if not isinstance(b[k], bool):
                return _err(f"{k} tiene que ser true o false.")
            flags[k] = b[k]
    earnings = b.get("earnings_alerts") if "earnings_alerts" in b else None
    try:
        return jsonify(settings_repo.set_notification_settings(
            g.user.id, thr, weekly, news, earnings_alerts=earnings, **flags))
    except ValueError as e:
        return _err(str(e))


# ------------------------------------------------------------------
# Chat con el mismo agente del bot
# ------------------------------------------------------------------
@api_bp.post("/feedback")
@api_login_required
def feedback_enviar():
    from finmate.services import feedback as fb

    b = _body()
    tipo = (b.get("tipo") or "").strip().lower()
    message = (b.get("message") or "").strip()
    rating = b.get("rating")
    if tipo not in fb.TIPOS:
        return _err("Elige de qué se trata (idea, problema, me gusta u otro).")
    if len(message) < 5:
        return _err("Escribe un poco más para que podamos entenderte.")
    if len(message) > 2000:
        return _err("El mensaje es demasiado largo (máximo 2000 caracteres).")
    if rating is not None:
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return _err("Calificación inválida.")
        if not 1 <= rating <= 5:
            return _err("La calificación va de 1 a 5.")
    if fb.rate_limited(g.user.id):
        return _err("Ya mandaste varios mensajes en la última hora. Intenta un poco más tarde.", 429)
    fb_id = fb.guardar_y_enviar(g.user.id, g.user.phone.replace("whatsapp:", ""), tipo, rating, message,
                                bool(b.get("contact")))
    return jsonify({"ok": True, "id": fb_id}), 201


@api_bp.post("/chat")
@api_login_required
def chat():
    from finmate.agent.orchestrator import handle_message

    msg = (_body().get("message") or "").strip()
    if not msg:
        return _err("Escribe una pregunta.")
    if len(msg) > 1000:
        return _err("La pregunta es demasiado larga (máximo 1000 caracteres).")
    reply = handle_message(g.user.phone, msg)
    return jsonify({"reply": reply})
