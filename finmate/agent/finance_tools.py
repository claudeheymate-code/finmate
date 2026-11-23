"""
Finmate - Tools de finanzas personales.

Registra gastos/ingresos y consulta resúmenes del mes o movimientos
recientes. Claude hace la extracción de lenguaje natural; estas tools
solo persisten y formatean lo que reciben.

Requiere finmate/db/finance_repo.py (Fase 2). Si la DB no está lista,
todas las funciones devuelven un mensaje de "no disponible" en lugar de
lanzar una excepción.
"""
import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)

try:
    from finmate.db.finance_repo import (
        add_transaction,
        get_monthly_summary,
        get_recent_transactions,
        get_categories,
        add_user_category,
        set_category_active,
        category_settings,
    )
    _FINANCE_DB_AVAILABLE = True
except ImportError:
    _FINANCE_DB_AVAILABLE = False

_DB_UNAVAILABLE_MSG = (
    "❌ Finanzas personales no disponible todavía (base de datos no configurada)."
)

# Nombres de mes en español para los mensajes de WhatsApp
_MONTH_NAMES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

# Emojis por categoría para el resumen mensual (claves en minúscula, sin tildes).
# Las categorías propias de cada usuario usan 🏷.
_CATEGORY_EMOJIS = {
    "comidas": "🍽", "carretes": "🎉", "asados": "🍖", "regalos": "🎁",
    "suscripciones": "📺", "polola": "❤️", "copete": "🍻", "bets": "🎲",
    "otros": "📦",
}

# Categorías por defecto (16 nov 2026). Deben coincidir con
# finance_repo.DEFAULT_CATEGORIES + "Otros". Cada usuario puede sacar algunas
# y agregar las suyas; ver _user_categories().
_VALID_CATEGORIES = [
    "Comidas", "Carretes", "Asados", "Regalos", "Suscripciones", "Polola", "Copete", "Bets", "Otros",
]

# Palabras que el usuario (o el modelo) puede usar y a qué categoría van.
# Claves en minúscula y sin tildes. Solo se usan si esa categoría está activa
# para el usuario.
_CATEGORY_ALIASES = {
    "comida": "Comidas", "alimentacion": "Comidas", "almuerzo": "Comidas", "cena": "Comidas",
    "supermercado": "Comidas", "restaurante": "Comidas", "delivery": "Comidas",
    "carrete": "Carretes", "fiesta": "Carretes", "salida": "Carretes", "disco": "Carretes",
    "evento social": "Carretes", "cumpleanos": "Carretes", "matrimonio": "Carretes",
    "asado": "Asados", "parrilla": "Asados", "carne": "Asados",
    "regalo": "Regalos",
    "suscripcion": "Suscripciones", "netflix": "Suscripciones", "spotify": "Suscripciones",
    "streaming": "Suscripciones", "gimnasio": "Suscripciones",
    "pareja": "Polola", "novia": "Polola", "pololo": "Polola", "cita": "Polola",
    "alcohol": "Copete", "bebidas": "Copete", "bar": "Copete", "botilleria": "Copete", "trago": "Copete",
    "bet": "Bets", "apuesta": "Bets", "apuestas": "Bets", "casino": "Bets",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_amount(amount: float) -> str:
    """Formatea un monto con signo y separadores de miles.

    Ejemplos:
        -8000   -> "-$8.000"
        150000  -> "+$150.000"
        1500000 -> "+$1,5M"
    """
    sign = "+" if amount >= 0 else "-"
    abs_val = abs(amount)

    if abs_val >= 1_000_000:
        millions = abs_val / 1_000_000
        # Mostrar hasta un decimal si no es entero
        if millions == int(millions):
            formatted = f"${int(millions)}M"
        else:
            formatted = f"${millions:.1f}M"
    elif abs_val >= 1_000:
        # Separador de miles con punto (convención rioplatense)
        formatted = f"${int(round(abs_val)):,}".replace(",", ".")
    else:
        formatted = f"${int(round(abs_val))}"

    return f"{sign}{formatted}"


def _fmt_date_short(d: date) -> str:
    """Devuelve fecha como '29 oct' para listas de movimientos."""
    return f"{d.day} {_MONTH_NAMES[d.month][:3]}"


def _fmt_date_long(d: date) -> str:
    """Devuelve fecha como '29 oct 2026' para confirmaciones."""
    return f"{d.day} {_MONTH_NAMES[d.month][:3]} {d.year}"


def _user_categories(user_id) -> list:
    """Categorías activas del usuario (por defecto + propias + Otros)."""
    try:
        return get_categories(user_id) if user_id is not None else list(_VALID_CATEGORIES)
    except Exception:
        return list(_VALID_CATEGORIES)


def _normalize_category(raw: str, allowed=None) -> str:
    """Devuelve la categoría del usuario que corresponde a raw, o 'Otros'.
    allowed: categorías activas del usuario (default: las por defecto)."""
    allowed = list(allowed) if allowed else list(_VALID_CATEGORIES)
    raw = raw or ""
    if raw in allowed:
        return raw
    # Intento case-insensitive y sin tildes ("comidas" -> "Comidas"), y alias
    key = _strip_accents(raw).lower().strip()
    for cat in allowed:
        if _strip_accents(cat).lower() == key:
            return cat
    alias = _CATEGORY_ALIASES.get(key)
    return alias if alias in allowed else "Otros"


def _strip_accents(text: str) -> str:
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", text or "") if unicodedata.category(c) != "Mn"
    )


def _category_emoji(category: str) -> str:
    return _CATEGORY_EMOJIS.get(_strip_accents(category).lower(), "🏷")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def tool_add_expense(user_id: int, tool_input: dict) -> str:
    """Registra un gasto (amount negativo) o ingreso (amount positivo)."""
    if not _FINANCE_DB_AVAILABLE:
        return _DB_UNAVAILABLE_MSG

    try:
        amount: float = float(tool_input["amount"])
        # El signo no depende solo de que el modelo mande negativo: si viene
        # "tipo", manda el tipo ("gasté 8 lucas" con amount=8000 es un gasto).
        tipo = str(tool_input.get("tipo", "")).lower().strip()
        if tipo == "gasto":
            amount = -abs(amount)
        elif tipo == "ingreso":
            amount = abs(amount)
        category: str = _normalize_category(tool_input.get("category", "Otros"), _user_categories(user_id))
        description: str = tool_input.get("description", "")
        raw_text: str = tool_input.get("raw_text", "")
        occasion: str = (tool_input.get("occasion") or "").strip()
        merchant: str = (tool_input.get("merchant") or "").strip()

        date_str = tool_input.get("date_str")
        if date_str:
            transaction_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            transaction_date = date.today()

        # Persistir
        add_transaction(
            user_id=user_id,
            amount=amount,
            category=category,
            description=description,
            date=transaction_date,
            raw_text=raw_text,
            occasion=occasion,
            merchant=merchant,
        )

        # Obtener total de gastos del mes para el mensaje de confirmación
        _, gastos_mes, _ = get_monthly_summary(
            user_id, transaction_date.year, transaction_date.month
        )

        # Formato del mensaje de confirmación
        is_income = amount >= 0
        icon = "➕" if is_income else "✅"
        verb = "Registrado"
        amount_str = _fmt_amount(amount)
        date_display = _fmt_date_long(transaction_date)

        desc_line = f"📋 {description} · {date_display}" if description else f"📋 {date_display}"
        if occasion:
            desc_line += f"\n🗓 Ocasión: {occasion}"

        gastos_str = _fmt_amount(-abs(gastos_mes))  # siempre negativo para gastos

        lines = [
            f"{icon} {verb}: *{amount_str}* en {category}",
            desc_line,
            "",
            f"Llevas *{gastos_str}* en gastos este mes.",
        ]
        return "\n".join(lines)

    except KeyError as exc:
        logger.error("tool_add_expense: falta campo requerido — %s", exc)
        return "❌ No pude registrar el gasto ahora. Prueba en un minuto."
    except Exception:
        logger.exception("tool_add_expense: error inesperado")
        return "❌ No pude registrar el gasto ahora. Prueba en un minuto."


def tool_get_monthly_summary(user_id: int, tool_input: dict) -> str:
    """Devuelve el resumen financiero de un mes (default: mes actual)."""
    if not _FINANCE_DB_AVAILABLE:
        return _DB_UNAVAILABLE_MSG

    try:
        today = date.today()
        year: int = int(tool_input.get("year") or today.year)
        month: int = int(tool_input.get("month") or today.month)

        ingresos, gastos, por_categoria = get_monthly_summary(user_id, year, month)

        month_label = f"{_MONTH_NAMES[month].upper()} {year}"

        # Sin transacciones
        if ingresos == 0 and gastos == 0 and not por_categoria:
            return f"No tienes transacciones registradas en {_MONTH_NAMES[month]} {year}."

        ingresos_str = _fmt_amount(abs(ingresos))
        gastos_str = _fmt_amount(-abs(gastos))
        balance = ingresos - abs(gastos)
        balance_str = _fmt_amount(balance)

        lines = [
            f"*FINANZAS — {month_label}*",
            "",
            f"💰 Ingresos: {ingresos_str}",
            f"💸 Gastos totales: {gastos_str}",
        ]

        if por_categoria:
            lines.append("")
            lines.append("*Por categoría:*")
            # Ordenar de mayor a menor gasto
            sorted_cats = sorted(por_categoria.items(), key=lambda x: abs(x[1]), reverse=True)
            for cat, cat_amount in sorted_cats:
                emoji = _category_emoji(cat)
                cat_str = _fmt_amount(-abs(cat_amount))
                lines.append(f"{emoji} {cat}: {cat_str}")

        lines.append("")
        lines.append(f"Balance del mes: {balance_str}")

        return "\n".join(lines)

    except Exception:
        logger.exception("tool_get_monthly_summary: error inesperado")
        return "❌ No pude obtener el resumen ahora. Prueba en un minuto."


def tool_get_recent_transactions(user_id: int) -> str:
    """Devuelve las últimas 5 transacciones del usuario."""
    if not _FINANCE_DB_AVAILABLE:
        return _DB_UNAVAILABLE_MSG

    try:
        transactions = get_recent_transactions(user_id, limit=5)

        if not transactions:
            return "No tienes movimientos registrados todavía."

        lines = ["*ÚLTIMOS MOVIMIENTOS*", ""]
        for i, tx in enumerate(transactions, start=1):
            amount_str = _fmt_amount(tx.amount)
            date_str = _fmt_date_short(tx.date)
            desc = tx.description or ""
            if desc:
                lines.append(f"{i}. {amount_str} · {tx.category} · {desc} · {date_str}")
            else:
                lines.append(f"{i}. {amount_str} · {tx.category} · {date_str}")

        return "\n".join(lines)

    except Exception:
        logger.exception("tool_get_recent_transactions: error inesperado")
        return "❌ No pude obtener los movimientos ahora. Prueba en un minuto."


def tool_manage_expense_categories(user_id: int, tool_input: dict) -> str:
    """Lista, agrega o saca categorías de gasto del usuario (solo su cuenta)."""
    if not _FINANCE_DB_AVAILABLE:
        return _DB_UNAVAILABLE_MSG
    action = str(tool_input.get("action", "list")).lower().strip()
    name = str(tool_input.get("name") or "").strip()
    try:
        if action == "add":
            ok, msg = add_user_category(user_id, name)
            if not ok:
                return f"⚠️ {msg}"
            return f"✅ Agregué *{msg}* a tus categorías. Ya puedes registrar gastos ahí."
        if action == "remove":
            if not set_category_active(user_id, name, False):
                return f"⚠️ No encontré la categoría {name} en tu lista (Otros no se puede sacar)."
            return f"✅ Saqué *{name}* de tus categorías. Los gastos que ya tenías ahí no se tocan."
        cats = category_settings(user_id)
        on = [c["name"] for c in cats if c["active"]]
        off = [c["name"] for c in cats if not c["active"]]
        lines = ["🏷 *Tus categorías de gasto*", "", " · ".join(_category_emoji(c) + " " + c for c in on)]
        if off:
            lines += ["", "Sacaste: " + ", ".join(off) + " (puedo volver a ponerlas)."]
        lines += ["", "Puedes pedirme agregar una nueva, ej: _agregá la categoría Bencina_."]
        return "\n".join(lines)
    except Exception:
        logger.exception("tool_manage_expense_categories: error inesperado")
        return "❌ No pude revisar tus categorías ahora. Prueba en un minuto."
