"""Tools del bot para fondos mutuos chilenos (datos públicos de la CMF).

Sirven para cualquier usuario y cualquier banco: buscar un fondo, ver sus
series con valor cuota y rentabilidad, comparar, ver un ranking y seguir los
fondos propios (con cuántas cuotas tiene, opcional).
"""
from __future__ import annotations

from finmate.data_sources.cmf_fondos import TIPOS
from finmate.services import funds

NO_DATA = ("Todavía no tengo los valores cuota de la CMF cargados (se bajan una vez al día). "
           "Prueba de nuevo en un rato.")
PERIODS = {"1d": "1 día", "1m": "1 mes", "ytd": "en el año", "12m": "12 meses"}


def _clp(n, dec=2):
    if n is None:
        return "—"
    s = f"{n:,.{dec}f}"
    return "$" + s.replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(n):
    if n is None:
        return "—"
    return ("+" if n > 0 else "") + f"{n:.2f}".replace(".", ",") + "%"


def _fecha(iso):
    if not iso:
        return ""
    y, m, d = iso.split("-")
    return f"{int(d)}-{int(m)}-{y}"


def _series_line(s: dict) -> str:
    return (f"• Serie *{s['serie']}*: {_clp(s['valor_cuota'], 4)} · 1d {_pct(s.get('r_1d'))} · "
            f"1m {_pct(s.get('r_1m'))} · año {_pct(s.get('r_ytd'))} · 12m {_pct(s.get('r_12m'))}")


def tool_search_funds(tool_input: dict) -> str:
    if not funds.has_data():
        return NO_DATA
    q = (tool_input.get("query") or "").strip()
    admin = (tool_input.get("administradora") or "").strip() or None
    tipo = tool_input.get("tipo")
    found = funds.search(q, admin=admin, tipo=tipo, limit=10)
    if not found:
        return f"No encontré fondos mutuos que coincidan con «{q or admin}». Prueba con otra palabra del nombre o solo la administradora."
    if len(found) == 1:
        return tool_get_fund({"run": found[0]["run"]})
    lines = [f"Fondos encontrados (CMF, {_fecha(found[0]['date'])}):"]
    for f in found:
        lines.append(f"• *{f['name']}* — {f['admin']} · {f['tipo_nombre']} · RUN {f['run']} · "
                     f"series: {', '.join(f['series'][:8])}{'…' if len(f['series']) > 8 else ''}")
    lines.append("Para ver valor cuota y rentabilidad de uno, usa get_fund con su RUN.")
    return "\n".join(lines)


def tool_get_fund(tool_input: dict) -> str:
    if not funds.has_data():
        return NO_DATA
    run = (tool_input.get("run") or "").strip().upper()
    serie = (tool_input.get("serie") or "").strip().upper()
    rows = funds.fund_series(run)
    if not rows:
        return f"No encontré el fondo con RUN {run}. Búscalo primero por nombre con search_funds."
    if serie:
        sel = [r for r in rows if r["serie"] == serie]
        if not sel:
            return f"El fondo {rows[0]['name']} no tiene la serie {serie}. Series: {', '.join(r['serie'] for r in rows)}."
        rows = sel
    f = rows[0]
    head = (f"*{f['name']}* — {f['admin']} (RUN {f['run']}) · {f['tipo_nombre']} · en {f['moneda'] or 'pesos'}\n"
            f"Valor cuota al {_fecha(f['date'])} (CMF):")
    body = [_series_line(r) for r in rows[:14]]
    if len(rows) > 14:
        body.append(f"…y {len(rows) - 14} series más.")
    notes = []
    if any(r.get("r_12m") is None for r in rows):
        notes.append("Algunas rentabilidades aún no están: se completan a medida que se guarda historia.")
    notes.append("Rentabilidad nominal según el valor cuota (no descuenta repartos de dividendos de algunas series). "
                 "Las series se diferencian por costos y por a quién van dirigidas (ej. APV).")
    return "\n".join([head, *body, *notes])


def tool_rank_funds(tool_input: dict) -> str:
    if not funds.has_data():
        return NO_DATA
    period = tool_input.get("periodo") or "12m"
    if period not in PERIODS:
        period = "12m"
    tipo = tool_input.get("tipo")
    worst = bool(tool_input.get("peores"))
    rows = funds.ranking(period, tipo=tipo, moneda=tool_input.get("moneda"),
                         admin=tool_input.get("administradora"), limit=int(tool_input.get("cantidad") or 8), worst=worst)
    if not rows:
        return f"Todavía no tengo historia suficiente para el ranking de {PERIODS[period]}. Prueba con un plazo más corto."
    title = f"{'Peores' if worst else 'Mejores'} fondos en {PERIODS[period]}"
    if tipo:
        title += f" · {TIPOS.get(tipo, '')}"
    lines = [f"{title} (CMF, al {_fecha(rows[0]['date'])}; sin series muy chicas):"]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. *{r['name']}* {r['serie']} — {r['admin']} · {_pct(r.get('r_' + period))} "
                     f"(RUN {r['run']})")
    lines.append("Rentabilidad pasada no asegura rentabilidad futura; compara también costos y riesgo.")
    return "\n".join(lines)


def tool_follow_fund(user_id: int, tool_input: dict) -> str:
    run = (tool_input.get("run") or "").strip().upper()
    serie = (tool_input.get("serie") or "").strip().upper()
    if tool_input.get("quitar"):
        n = funds.unfollow(user_id, run, serie or None)
        return "Listo, ya no lo sigo." if n else "Ese fondo no estaba en tus fondos."
    if not run or not serie:
        return "Necesito el RUN del fondo y la serie (búscalo con search_funds)."
    cuotas = tool_input.get("cuotas")
    try:
        row = funds.follow(user_id, run, serie, float(cuotas) if cuotas not in (None, "") else None)
    except ValueError as e:
        return str(e)
    extra = f" con {cuotas} cuotas" if cuotas else ""
    return f"Listo, sigo {row.get('name', run)} serie {serie}{extra}. Lo verás en tus fondos y en el panel."


def tool_get_my_funds(user_id: int) -> str:
    items = funds.my_funds(user_id)
    if not items:
        return ("No sigues ningún fondo mutuo todavía. Dime cuál tienes (nombre y banco) y la serie, "
                "y opcionalmente cuántas cuotas.")
    lines = [f"Tus fondos (CMF, {_fecha(items[0].get('date'))}):" if items[0].get("date") else "Tus fondos:"]
    total = 0.0
    for f in items:
        val = f" · tu saldo ≈ {_clp(f['valor'], 0)}" if f.get("valor") else ""
        total += f.get("valor") or 0
        lines.append(f"• *{f.get('name')}* {f['serie']} ({f.get('admin')}): {_clp(f.get('valor_cuota'), 4)} · "
                     f"1d {_pct(f.get('r_1d'))} · 1m {_pct(f.get('r_1m'))} · año {_pct(f.get('r_ytd'))}{val}")
    if total:
        lines.append(f"Total aproximado en fondos: {_clp(total, 0)}")
    return "\n".join(lines)
