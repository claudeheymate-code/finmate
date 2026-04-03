"""
Finmate - Formateador de Mensajes para WhatsApp
Genera mensajes claros, profesionales y concisos.
Usa formato compatible con WhatsApp (bold con *, italic con _).
"""

from datetime import datetime
from typing import Optional


# Mapeo de países a banderas (emoji)
COUNTRY_FLAGS = {
    "US": "🇺🇸", "USA": "🇺🇸", "United States": "🇺🇸",
    "EU": "🇪🇺", "EUR": "🇪🇺", "Eurozone": "🇪🇺",
    "GB": "🇬🇧", "UK": "🇬🇧", "United Kingdom": "🇬🇧",
    "JP": "🇯🇵", "Japan": "🇯🇵",
    "CN": "🇨🇳", "China": "🇨🇳",
    "DE": "🇩🇪", "Germany": "🇩🇪",
    "FR": "🇫🇷", "France": "🇫🇷",
    "CA": "🇨🇦", "Canada": "🇨🇦",
    "AU": "🇦🇺", "Australia": "🇦🇺",
    "CH": "🇨🇭", "Switzerland": "🇨🇭",
    "CL": "🇨🇱", "Chile": "🇨🇱",
    "BR": "🇧🇷", "Brazil": "🇧🇷",
    "MX": "🇲🇽", "Mexico": "🇲🇽",
}

# Mapeo de índices a nombres legibles
INDEX_NAMES = {
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones",
    "^IXIC": "Nasdaq",
    "^FTSE": "FTSE 100",
    "^N225": "Nikkei 225",
    "^STOXX50E": "Euro Stoxx 50",
}


def _flag(country: str) -> str:
    return COUNTRY_FLAGS.get(country, "🌐")


def _format_number(value, prefix: str = "", suffix: str = "") -> str:
    if value is None:
        return "N/D"
    try:
        num = float(value)
        if abs(num) >= 1_000_000_000:
            return f"{prefix}{num / 1_000_000_000:.1f}B{suffix}"
        if abs(num) >= 1_000_000:
            return f"{prefix}{num / 1_000_000:.1f}M{suffix}"
        return f"{prefix}{num:,.2f}{suffix}"
    except (ValueError, TypeError):
        return str(value)


def _change_emoji(change_pct) -> str:
    try:
        pct = float(change_pct)
        if pct > 1:
            return "🟢📈"
        elif pct > 0:
            return "🟢"
        elif pct < -1:
            return "🔴📉"
        elif pct < 0:
            return "🔴"
        return "⚪"
    except (ValueError, TypeError):
        return ""


# ==============================================================
# RESUMEN SEMANAL
# ==============================================================
def format_weekly_summary(data: dict) -> str:
    """
    Formatea el resumen semanal completo para WhatsApp.
    Estructura: Índices → Noticias → Earnings → Macro
    """
    lines = []
    lines.append("📊 *FINMATE — RESUMEN SEMANAL*")
    lines.append(f"📅 {datetime.utcnow().strftime('%d/%m/%Y')}")
    lines.append("")

    # --- Índices principales ---
    indices = data.get("indices", [])
    if indices:
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("📈 *MERCADOS*")
        lines.append("")
        for idx in indices:
            name = INDEX_NAMES.get(idx.get("symbol", ""), idx.get("name", idx.get("symbol", "")))
            emoji = _change_emoji(idx.get("change_pct"))
            price = _format_number(idx.get("price"))
            change = _format_number(idx.get("change_pct"), suffix="%")
            lines.append(f"{emoji} *{name}*: {price} ({change})")
        lines.append("")

    # --- Top Noticias ---
    news = data.get("news", [])
    if news:
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("📰 *NOTICIAS CLAVE*")
        lines.append("")
        for i, item in enumerate(news[:5], 1):
            title = item.get("title", "").strip()
            summary = item.get("summary", "").strip()
            if len(summary) > 200:
                summary = summary[:200] + "..."
            lines.append(f"*{i}. {title}*")
            if summary:
                lines.append(f"   _{summary}_")
            lines.append("")

    # --- Earnings ---
    earnings = data.get("earnings", [])
    if earnings:
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("🏢 *RESULTADOS CORPORATIVOS*")
        lines.append("")
        for e in earnings[:10]:
            symbol = e.get("symbol", "")
            date = e.get("date", "")
            eps_est = _format_number(e.get("eps_estimate"), prefix="$")
            eps_act = e.get("eps_actual")
            line = f"• *{symbol}* — {date}"
            if eps_act is not None:
                eps_act_fmt = _format_number(eps_act, prefix="$")
                beat = "✅ superó" if float(eps_act) > float(e.get("eps_estimate") or 0) else "❌ no alcanzó"
                line += f" | EPS: {eps_act_fmt} ({beat} est. {eps_est})"
            else:
                line += f" | EPS estimado: {eps_est}"
            lines.append(line)
        lines.append("")

    # --- Calendario Económico ---
    economic = data.get("economic_calendar", [])
    if economic:
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("🌍 *DATOS MACROECONÓMICOS*")
        lines.append("")
        for ev in economic[:10]:
            flag = _flag(ev.get("country", ""))
            event = ev.get("event", "")
            date = ev.get("date", "")
            impact = "🔴" if ev.get("impact") == "high" else "🟡"
            line = f"{impact} {flag} *{event}* — {date}"
            if ev.get("actual") is not None:
                line += f" | Actual: {ev['actual']}"
            if ev.get("forecast") is not None:
                line += f" | Esperado: {ev['forecast']}"
            if ev.get("previous") is not None:
                line += f" | Anterior: {ev['previous']}"
            lines.append(line)
        lines.append("")

    # --- Movers ---
    movers = data.get("market_movers", {})
    gainers = movers.get("gainers", [])
    losers = movers.get("losers", [])
    if gainers or losers:
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("🔥 *MOVERS DEL MERCADO*")
        lines.append("")
        if gainers:
            lines.append("📈 _Top Ganadores:_")
            for g in gainers[:3]:
                lines.append(f"  🟢 {g['symbol']} ({_format_number(g.get('change_pct'), suffix='%')})")
        if losers:
            lines.append("📉 _Top Perdedores:_")
            for l in losers[:3]:
                lines.append(f"  🔴 {l['symbol']} ({_format_number(l.get('change_pct'), suffix='%')})")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("_Finmate — Información de mercado, no recomendación de inversión._")

    return "\n".join(lines)


# ==============================================================
# ALERTAS EN TIEMPO REAL
# ==============================================================
def format_earnings_alert(earning: dict) -> str:
    """Formatea una alerta de resultado corporativo."""
    symbol = earning.get("symbol", "")
    eps_actual = earning.get("eps_actual")
    eps_estimate = earning.get("eps_estimate")
    revenue_actual = earning.get("revenue_actual")

    lines = [
        "🏢 *ALERTA — RESULTADO CORPORATIVO*",
        "",
        f"*{symbol}* acaba de reportar resultados:",
        "",
    ]

    if eps_actual is not None and eps_estimate is not None:
        try:
            diff = float(eps_actual) - float(eps_estimate)
            if diff > 0:
                lines.append(f"✅ *EPS: ${eps_actual}* (superó estimación de ${eps_estimate})")
                lines.append(f"📊 _Esto indica que la empresa tuvo mejor desempeño al esperado, lo que suele ser positivo para la acción._")
            else:
                lines.append(f"❌ *EPS: ${eps_actual}* (no alcanzó estimación de ${eps_estimate})")
                lines.append(f"📊 _Resultados por debajo de expectativas, lo que podría generar presión bajista en la acción._")
        except (ValueError, TypeError):
            lines.append(f"EPS: {eps_actual} (est: {eps_estimate})")

    if revenue_actual is not None:
        lines.append(f"💰 Ingresos: {_format_number(revenue_actual, prefix='$')}")

    lines.append("")
    lines.append("_Finmate — Información, no recomendación._")
    return "\n".join(lines)


def format_economic_alert(event: dict) -> str:
    """Formatea una alerta de dato macroeconómico."""
    country = event.get("country", "")
    flag = _flag(country)
    event_name = event.get("event", "")
    actual = event.get("actual")
    forecast = event.get("forecast")
    previous = event.get("previous")

    lines = [
        f"🌍 *ALERTA — DATO MACROECONÓMICO*",
        "",
        f"{flag} *{event_name}* ({country})",
        "",
    ]

    if actual is not None:
        lines.append(f"📊 *Dato publicado:* {actual}")
        if forecast is not None:
            try:
                diff = float(actual) - float(forecast)
                if diff > 0:
                    lines.append(f"⬆️ _Superior al esperado ({forecast}). Esto puede indicar mayor fortaleza económica._")
                elif diff < 0:
                    lines.append(f"⬇️ _Inferior al esperado ({forecast}). Esto puede indicar debilidad económica._")
                else:
                    lines.append(f"➡️ _En línea con lo esperado ({forecast})._")
            except (ValueError, TypeError):
                lines.append(f"Esperado: {forecast}")
        if previous is not None:
            lines.append(f"📋 Dato anterior: {previous}")

    lines.append("")
    lines.append("_Finmate — Información, no recomendación._")
    return "\n".join(lines)


def format_breaking_news_alert(news_item: dict) -> str:
    """Formatea una alerta de noticia importante."""
    title = news_item.get("title", "")
    summary = news_item.get("summary", "")
    source = news_item.get("source", "")

    if len(summary) > 300:
        summary = summary[:300] + "..."

    lines = [
        "🚨 *ALERTA — NOTICIA DE MERCADO*",
        "",
        f"*{title}*",
        "",
    ]

    if summary:
        lines.append(f"_{summary}_")
        lines.append("")
    if source:
        lines.append(f"📎 Fuente: {source}")

    lines.append("")
    lines.append("_Finmate — Información, no recomendación._")
    return "\n".join(lines)
