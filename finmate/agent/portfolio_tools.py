"""
Finmate - Tools de portafolio y watchlist para el orquestador (Fase 1)

Reutiliza la misma lógica de cotización que ya corre en producción
(finmate.whatsapp.webhook._get_finnhub_quote / _format_number / _change_emoji)
para no duplicar el manejo de "mercado cerrado" ni el formato de números,
igual que ya hace get_market_data en tools.py.
"""
import logging
import re
from typing import Optional

import httpx

from finmate.db.repository import (
    add_or_update_holding,
    add_to_watchlist as repo_add_to_watchlist,
    get_portfolio,
    get_watchlist as repo_get_watchlist,
    remove_from_watchlist as repo_remove_from_watchlist,
    remove_holding,
)
from finmate.whatsapp.webhook import _change_emoji, _format_number, _get_finnhub_quote

logger = logging.getLogger(__name__)

# Tickers en mayúsculas, letras/números/punto/guión, hasta 10 caracteres
# (alcanza para BRK.B, por ejemplo).
_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


def _clean_symbol(raw: str) -> Optional[str]:
    if not raw:
        return None
    symbol = raw.strip().upper()
    if not _SYMBOL_RE.match(symbol):
        return None
    return symbol


def _quote_for(symbol: str) -> Optional[dict]:
    try:
        with httpx.Client(timeout=10) as client:
            return _get_finnhub_quote(client, symbol)
    except Exception as e:
        logger.error(f"Error cotizando {symbol}: {e}")
        return None


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------
# Portafolio
# ------------------------------------------------------------------
def tool_get_portfolio(user_id: int) -> str:
    holdings = get_portfolio(user_id)
    if not holdings:
        return (
            "Todavía no tenés nada cargado en tu portafolio. Decime algo como "
            "'agregá 10 AAPL a 150' para empezar."
        )

    lines = ["*TU PORTAFOLIO*", ""]
    total_value = 0.0
    total_cost = 0.0
    has_cost_data = False
    any_price_missing = False

    for symbol, quantity, avg_cost in holdings:
        quote = _quote_for(symbol)
        if quote and quote.get("price"):
            price = quote["price"]
            value = price * quantity
            total_value += value
            line = (
                f"*{symbol}*: {quantity:g} u. x {_format_number(price, prefix='$')} "
                f"= {_format_number(value, prefix='$')}"
            )
            if avg_cost:
                has_cost_data = True
                cost = avg_cost * quantity
                total_cost += cost
                pnl = value - cost
                pnl_pct = (pnl / cost * 100) if cost else 0
                emoji = "🟢" if pnl >= 0 else "🔴"
                line += (
                    f"\n   {emoji} P&L: {_format_number(pnl, prefix='$')} "
                    f"({_format_number(pnl_pct, suffix='%')})"
                )
            lines.append(line)
        else:
            any_price_missing = True
            lines.append(f"*{symbol}*: {quantity:g} u. (sin cotización disponible ahora)")

    lines.append("")
    lines.append(f"*Valor total estimado*: {_format_number(total_value, prefix='$')}")
    if has_cost_data and total_cost:
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0
        emoji = "🟢" if total_pnl >= 0 else "🔴"
        lines.append(
            f"{emoji} *P&L total*: {_format_number(total_pnl, prefix='$')} "
            f"({_format_number(total_pnl_pct, suffix='%')})"
        )
    if any_price_missing:
        lines.append("")
        lines.append("_Algunos símbolos no tienen cotización disponible en este momento._")

    return "\n".join(lines)


def tool_add_to_portfolio(user_id: int, tool_input: dict) -> str:
    symbol = _clean_symbol(tool_input.get("symbol", ""))
    if not symbol:
        return "No reconocí el símbolo. Decime el ticker tal cual se opera, por ejemplo AAPL o NVDA."

    quantity = _to_float(tool_input.get("quantity"))
    if quantity is None or quantity <= 0:
        return "Necesito una cantidad de unidades mayor a cero para agregarlo al portafolio."

    avg_cost = _to_float(tool_input.get("avg_cost"))

    holding = add_or_update_holding(user_id, symbol, quantity, avg_cost)
    if holding is None:
        return f"No pude agregar {symbol} al portafolio."

    msg = f"✅ Agregado: {quantity:g} u. de *{symbol}*"
    if avg_cost:
        msg += f" a costo promedio {_format_number(avg_cost, prefix='$')}"
    msg += f". Ahora tenés {holding.quantity:g} u. en total."
    return msg


def tool_remove_from_portfolio(user_id: int, tool_input: dict) -> str:
    symbol = _clean_symbol(tool_input.get("symbol", ""))
    if not symbol:
        return "No reconocí el símbolo. Decime el ticker tal cual se opera, por ejemplo AAPL o NVDA."

    quantity = _to_float(tool_input.get("quantity"))

    if quantity is None:
        ok = remove_holding(user_id, symbol)
        return (
            f"✅ Quité *{symbol}* por completo de tu portafolio."
            if ok
            else f"No tenías *{symbol}* en tu portafolio."
        )

    if quantity <= 0:
        return "La cantidad a quitar tiene que ser mayor a cero."

    holding = add_or_update_holding(user_id, symbol, -abs(quantity))
    if holding is None:
        return f"✅ Quité *{symbol}* de tu portafolio (ya no te quedan unidades)."
    return f"✅ Vendiste {quantity:g} u. de *{symbol}*. Te quedan {holding.quantity:g} u."


# ------------------------------------------------------------------
# Watchlist
# ------------------------------------------------------------------
def tool_get_watchlist(user_id: int) -> str:
    items = repo_get_watchlist(user_id)
    if not items:
        return "No estás siguiendo ningún activo todavía. Decime 'seguí a NVDA' para agregarlo."

    lines = ["*TU WATCHLIST*", ""]
    for symbol, note in items:
        quote = _quote_for(symbol)
        if quote and quote.get("price"):
            emoji = _change_emoji(quote.get("change_pct"))
            price_txt = (
                f"{_format_number(quote['price'], prefix='$')} "
                f"({_format_number(quote.get('change_pct'), suffix='%')})"
            )
            line = f"{emoji} *{symbol}*: {price_txt}"
        else:
            line = f"⚪ *{symbol}*: _sin cotización disponible_"
        if note:
            line += f" — {note}"
        lines.append(line)

    return "\n".join(lines)


def tool_add_to_watchlist(user_id: int, tool_input: dict) -> str:
    symbol = _clean_symbol(tool_input.get("symbol", ""))
    if not symbol:
        return "No reconocí el símbolo. Decime el ticker tal cual se opera, por ejemplo AAPL o NVDA."

    note = tool_input.get("note") or None
    add_to_watchlist_result = None
    try:
        add_to_watchlist_result = repo_add_to_watchlist(user_id, symbol, note)
    except Exception as e:
        logger.error(f"Error agregando {symbol} a watchlist de user {user_id}: {e}")
        return f"No pude agregar {symbol} a tu watchlist."

    if add_to_watchlist_result is None:
        return f"No pude agregar {symbol} a tu watchlist."
    return f"✅ Agregué *{symbol}* a tu watchlist."


def tool_remove_from_watchlist(user_id: int, tool_input: dict) -> str:
    symbol = _clean_symbol(tool_input.get("symbol", ""))
    if not symbol:
        return "No reconocí el símbolo."

    ok = repo_remove_from_watchlist(user_id, symbol)
    return f"✅ Quité *{symbol}* de tu watchlist." if ok else f"*{symbol}* no estaba en tu watchlist."
