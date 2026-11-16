"""
Finmate - Tools de macroeconomía para el agente (Etapa A de fuentes).

- get_us_macro: tasa Fed, inflación, desempleo y bonos del Tesoro (FRED).
- get_chile_indicators: dólar observado, UF, TPM e IPC (Banco Central).
- get_us_release_calendar: próximas publicaciones importantes (FRED).
"""
import datetime as dt

from finmate.data_sources import bcch, fred

_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _fecha(iso: str) -> str:
    try:
        d = dt.date.fromisoformat(iso)
        return f"{d.day} {_MESES[d.month - 1]}"
    except (TypeError, ValueError):
        return iso or ""


def _num(value: float, decimals: int = 2) -> str:
    s = f"{value:,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def tool_get_us_macro(_input: dict = None) -> str:
    if not fred.is_configured():
        return "La fuente de datos de EE.UU. (FRED) todavía no está configurada."
    data = fred.get_snapshot()
    if not data:
        return "No pude obtener los datos de FRED en este momento. Intenta de nuevo en unos minutos."
    lines = ["🇺🇸 *Macro EE.UU.* (fuente: FRED)", ""]
    for it in data:
        lines.append(f"• {it['label']}: *{_num(it['value'])}{it['suffix']}* ({_fecha(it['date'])})")
    return "\n".join(lines)


def tool_get_chile_indicators(_input: dict = None) -> str:
    if not bcch.is_configured():
        return "La fuente del Banco Central de Chile todavía no está configurada."
    data = bcch.get_snapshot()
    if not data:
        return "No pude obtener los datos del Banco Central en este momento."
    lines = ["🇨🇱 *Indicadores Chile* (fuente: Banco Central)", ""]
    for it in data:
        val = f"${_num(it['value'])}" if it["fmt"] == "clp" else f"{_num(it['value'])}%"
        lines.append(f"• {it['label']}: *{val}* ({_fecha(it['date'])})")
    return "\n".join(lines)


def tool_get_us_release_calendar(_input: dict = None) -> str:
    if not fred.is_configured():
        return "El calendario de EE.UU. (FRED) todavía no está configurado."
    rel = fred.get_upcoming_releases(days_ahead=14)
    if not rel:
        return "No hay publicaciones importantes de EE.UU. en las próximas dos semanas (o FRED no respondió)."
    lines = ["🗓️ *Próximos datos de EE.UU.* (14 días)", ""]
    for r in rel:
        lines.append(f"• {_fecha(r['date'])}: {r['name']}")
    lines.append("")
    lines.append("_Dime 'seguime el CPI_US' (o NFP, FED_RATE…) y te aviso el día antes._")
    return "\n".join(lines)
