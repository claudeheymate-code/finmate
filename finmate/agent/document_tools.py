"""Tools para registrar en bloque lo que el usuario manda en fotos o PDFs
(cartolas bancarias, boletas, pantallazos de su corredora)."""

import logging

from finmate.agent.finance_tools import tool_add_expense
from finmate.agent.portfolio_tools import _clean_symbol, _to_float

logger = logging.getLogger(__name__)

MAX_ITEMS = 80


def tool_add_expenses_batch(user_id: int, tool_input: dict) -> str:
    """Registra varios gastos/ingresos de una vez (p. ej. leídos de una cartola)."""
    items = (tool_input or {}).get("items") or []
    if not isinstance(items, list) or not items:
        return "No recibí movimientos para registrar."
    items = items[:MAX_ITEMS]
    ok, failed, total = 0, [], 0.0
    for it in items:
        if not isinstance(it, dict):
            continue
        res = tool_add_expense(user_id, it)
        if not res.startswith("❌") and "Registrado" in res:
            ok += 1
            try:
                amt = abs(float(it.get("amount") or 0))
                total += -amt if str(it.get("tipo", "gasto")).lower() == "gasto" else amt
            except (TypeError, ValueError):
                pass
        else:
            failed.append(f"{it.get('description') or it.get('merchant') or '?'}: {res[:80]}")
    msg = f"✅ Registré {ok} de {len(items)} movimientos (neto {total:,.0f})."
    if failed:
        msg += " No pude registrar: " + "; ".join(failed[:5])
    return msg


def tool_import_portfolio(user_id: int, tool_input: dict) -> str:
    """Carga posiciones leídas de un documento. mode=replace deja la cantidad exacta
    (y el costo promedio si viene); mode=add suma a lo que ya tenía."""
    from finmate.db.repository import add_or_update_holding, get_portfolio, remove_holding

    positions = (tool_input or {}).get("positions") or []
    mode = str((tool_input or {}).get("mode") or "replace").lower()
    if not isinstance(positions, list) or not positions:
        return "No recibí posiciones para cargar."
    current = {}
    try:
        for sym, qty, _cost in get_portfolio(user_id) or []:   # [(symbol, quantity, avg_cost)]
            current[sym.upper()] = float(qty or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"No pude leer el portafolio actual: {e}")
    done, skipped = [], []
    for p in positions[:MAX_ITEMS]:
        if not isinstance(p, dict):
            continue
        sym = _clean_symbol(p.get("symbol", ""))
        qty = _to_float(p.get("quantity"))
        cost = _to_float(p.get("avg_cost"))
        if not sym or qty is None or qty < 0:
            skipped.append(str(p.get("symbol") or "?"))
            continue
        try:
            if mode == "add":
                if qty > 0:
                    add_or_update_holding(user_id, sym, qty, cost)
            else:
                if sym in current:
                    remove_holding(user_id, sym)
                if qty > 0:
                    add_or_update_holding(user_id, sym, qty, cost)
            done.append(f"{sym} {qty:g}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"No pude cargar {sym}: {e}")
            skipped.append(sym)
    msg = f"✅ Portafolio actualizado ({len(done)} posiciones): " + ", ".join(done[:15])
    others = sorted(set(current) - {_clean_symbol(p.get('symbol', '')) for p in positions if isinstance(p, dict)})
    if mode != "add" and others:
        msg += f". Siguen en tu portafolio (no venían en el documento): {', '.join(others[:10])}"
    if skipped:
        msg += f". No pude leer: {', '.join(skipped[:8])}"
    return msg
