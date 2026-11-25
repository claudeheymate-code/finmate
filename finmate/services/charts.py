"""Imágenes simples del portafolio para mandar por WhatsApp (torta, barras y tabla).

Se dibujan en el propio servidor con matplotlib (sin servicios externos ni costo
por imagen) usando los datos reales de `services/portfolio.compute_portfolio`, así
que los números son exactos. Cada imagen es un PNG de ~50-100 KB y tarda menos de
un segundo. matplotlib se importa recién cuando se pide una imagen.
"""

import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)

NAVY, GREEN, RED, LINE, BG, FAINT = "#082449", "#00805F", "#C2410C", "#E3E8EF", "#FFFFFF", "#6B7A90"
PALETTE = ["#0B3D91", "#00805F", "#3B82C4", "#7FB77E", "#F2A541", "#C2410C", "#8E7CC3", "#9AA5B1"]
MAX_SLICES = 7          # más que esto se agrupa en "Otros" (la torta se vuelve ilegible)
MAX_ROWS = 14           # filas de la tabla
KINDS = {
    "torta": "Distribución por activo",
    "torta_clase": "Distribución por tipo de activo",
    "torta_sector": "Distribución por sector",
    "barras": "Rentabilidad por posición",
    "tabla": "Tus posiciones",
}


def _num(v: float, d: int = 2) -> str:
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v: Optional[float], d: int = 1) -> str:
    if v is None:
        return "—"
    return f"{'+' if v >= 0 else '−'}{_num(abs(v), d)}%"


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "text.color": NAVY,
                         "axes.labelcolor": NAVY, "xtick.color": NAVY, "ytick.color": NAVY})
    return plt


def _header(fig, title: str, sub: str) -> None:
    fig.text(0.06, 0.955, title, fontsize=17, fontweight="bold", color=NAVY, va="top")
    fig.text(0.06, 0.9, sub, fontsize=10.5, color=FAINT, va="top")
    fig.text(0.06, 0.03, "Finmate · información, no recomendación", fontsize=8.5, color=FAINT)


def _png(fig, plt) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG, dpi=160)
    plt.close(fig)
    return buf.getvalue()


def _slices(items: list) -> list:
    """[(nombre, valor)] con lo más chico agrupado en 'Otros'."""
    items = [(n, v) for n, v in items if v and v > 0]
    items.sort(key=lambda x: -x[1])
    if len(items) > MAX_SLICES:
        rest = sum(v for _n, v in items[MAX_SLICES - 1:])
        items = items[:MAX_SLICES - 1] + [("Otros", rest)]
    return items


def pie_chart(data: dict, by: str = "activo") -> bytes:
    plt = _plt()
    total = data["totals"]["value"] or 0
    if by == "clase":
        items, sub = [(g["name"], g["value"]) for g in data["by_class"]], "por tipo de activo"
    elif by == "sector":
        items, sub = [(g["name"], g["value"]) for g in data["by_sector"]], "por sector"
    else:
        items, sub = [(p["symbol"], p["value"]) for p in data["positions"]], "por activo"
    items = _slices(items)
    fig = plt.figure(figsize=(6, 6.6), facecolor=BG)
    _header(fig, "Tu portafolio", f"US${_num(total, 0)} · distribución {sub}")
    ax = fig.add_axes([0.08, 0.22, 0.84, 0.62])
    wedges, _ = ax.pie([v for _n, v in items], colors=PALETTE[:len(items)], startangle=90, counterclock=False,
                       wedgeprops={"width": 0.38, "edgecolor": "white", "linewidth": 2})
    big = f"US${_num(total / 1000, 1)}k" if total >= 10_000 else f"US${_num(total, 0)}"
    ax.text(0, 0.06, big, ha="center", fontsize=18, fontweight="bold")
    ax.text(0, -0.14, "valor total", ha="center", fontsize=10, color=FAINT)
    labels = [f"{n}  {_num(v / total * 100, 1)}%" for n, v in items] if total else [n for n, _v in items]
    fig.legend(wedges, labels, loc="lower center", ncol=2 if by != "activo" else 3, frameon=False,
               bbox_to_anchor=(0.5, 0.07), fontsize=10, handlelength=1, columnspacing=1.4)
    return _png(fig, plt)


def bar_chart(data: dict) -> bytes:
    plt = _plt()
    rows = sorted([p for p in data["positions"] if p.get("pnl_pct") is not None], key=lambda p: p["pnl_pct"])
    if not rows:
        raise ValueError("sin_costo")
    h = max(4.6, 2.2 + 0.55 * len(rows))
    fig = plt.figure(figsize=(6, h), facecolor=BG)
    tot = data["totals"]
    _header(fig, "Rentabilidad por posición",
            "Ganancia o pérdida sobre lo invertido" + (f" · total {_pct(tot.get('pnl_pct'))}" if tot.get("pnl_pct") is not None else ""))
    top = 1 - 1.25 / h
    ax = fig.add_axes([0.17, 0.5 / h + 0.04, 0.75, top - 0.5 / h - 0.06])
    vals = [p["pnl_pct"] for p in rows]
    ax.barh([p["symbol"] for p in rows], vals, color=[GREEN if v >= 0 else RED for v in vals], height=0.6)
    span = max(max(vals), 0) - min(min(vals), 0) or 1
    for i, v in enumerate(vals):
        ax.text(v + (span * 0.02 if v >= 0 else -span * 0.02), i, _pct(v), va="center",
                ha="left" if v >= 0 else "right", fontsize=10.5, color=GREEN if v >= 0 else RED, fontweight="bold")
    ax.axvline(0, color=LINE, lw=1.2)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(left=False, bottom=False)
    ax.set_xticks([])
    ax.set_xlim(min(min(vals), 0) - span * 0.3, max(max(vals), 0) + span * 0.3)
    return _png(fig, plt)


def table_chart(data: dict) -> bytes:
    plt = _plt()
    rows = [p for p in data["positions"] if p.get("value") is not None][:MAX_ROWS]
    if not rows:
        raise ValueError("sin_precios")
    h = 2.4 + 0.42 * (len(rows) + 2)
    fig = plt.figure(figsize=(6.6, h), facecolor=BG)
    _header(fig, "Tus posiciones", "Último precio y resultado acumulado")
    ax = fig.add_axes([0.04, 0.6 / h + 0.02, 0.92, 1 - 1.35 / h - 0.6 / h])
    ax.axis("off")
    cols = ["Activo", "Cant.", "Precio", "Hoy", "Valor", "Resultado"]
    cell = [[p["symbol"], _num(p["quantity"], 0 if float(p["quantity"]).is_integer() else 2), f"${_num(p['price'])}",
             _pct(p.get("change_pct")), f"${_num(p['value'], 0)}", _pct(p.get("pnl_pct"))] for p in rows]
    tot = data["totals"]
    cell.append(["Total", "", "", _pct(tot.get("day_change_pct")), f"${_num(tot['value'] or 0, 0)}", _pct(tot.get("pnl_pct"))])
    t = ax.table(cellText=cell, colLabels=cols, loc="upper center", cellLoc="right", colLoc="right")
    t.auto_set_font_size(False)
    t.set_fontsize(10.5)
    t.scale(1, 1.7)
    for (i, j), c in t.get_celld().items():
        c.set_edgecolor(LINE)
        c.visible_edges = "B"
        if j == 0:
            c._loc = "left"
            c.get_text().set_ha("left")
        if i == 0:
            c.get_text().set_color(FAINT)
            c.get_text().set_fontsize(9.5)
            continue
        txt = c.get_text().get_text()
        if i == len(cell):
            c.get_text().set_fontweight("bold")
        if j in (3, 5) and txt not in ("", "—"):
            c.get_text().set_color(GREEN if txt.startswith("+") else RED)
    return _png(fig, plt)


def render(user_id: int, kind: str) -> tuple:
    """(png_bytes, pie de foto) para el portafolio del usuario. ValueError con un motivo legible si no se puede."""
    from finmate.services.portfolio import compute_portfolio

    if kind not in KINDS:
        raise ValueError(f"Tipo de imagen desconocido. Opciones: {', '.join(KINDS)}.")
    data = compute_portfolio(user_id)
    if not data["positions"]:
        raise ValueError("No tienes posiciones cargadas todavía.")
    if not data["totals"]["value"]:
        raise ValueError("No pude obtener precios de tus posiciones en este momento.")
    try:
        if kind == "barras":
            png = bar_chart(data)
        elif kind == "tabla":
            png = table_chart(data)
        else:
            png = pie_chart(data, {"torta_clase": "clase", "torta_sector": "sector"}.get(kind, "activo"))
    except ValueError as e:
        if str(e) == "sin_costo":
            raise ValueError("Para ver la rentabilidad necesito el precio de compra de tus posiciones.")
        raise ValueError("No pude armar la imagen con los datos que hay.")
    tot = data["totals"]
    caption = f"{KINDS[kind]} · US${_num(tot['value'], 0)}"
    if tot.get("pnl_pct") is not None and kind in ("barras", "tabla"):
        caption += f" · resultado {_pct(tot['pnl_pct'])}"
    if data.get("missing_prices"):
        caption += f" (sin precio: {', '.join(data['missing_prices'])})"
    return png, caption


def tool_send_portfolio_chart(user_id: int, tool_input: dict) -> str:
    """Tool del agente: dibuja la imagen y la manda por WhatsApp al usuario."""
    kind = (tool_input.get("kind") or "torta").strip().lower()
    try:
        png, caption = render(user_id, kind)
    except ValueError as e:
        return f"No mandé la imagen: {e}"
    except Exception as e:  # noqa: BLE001
        logger.error(f"No pude dibujar la imagen {kind} del usuario {user_id}: {e}", exc_info=True)
        return "No mandé la imagen: hubo un problema al dibujarla."
    try:
        from finmate.db.models import User, get_session
        from finmate.whatsapp.messenger import WhatsAppMessenger

        s = get_session()
        try:
            user = s.get(User, user_id)
            phone = user.phone if user else None
        finally:
            s.close()
        if not phone:
            return "No mandé la imagen: no encontré tu número."
        ok = WhatsAppMessenger().send_image(phone, png, caption)
    except Exception as e:  # noqa: BLE001
        logger.error(f"No pude mandar la imagen al usuario {user_id}: {e}", exc_info=True)
        ok = False
    if not ok:
        return "No mandé la imagen: WhatsApp no la aceptó. Ofrécele el resumen en texto."
    return (f"Imagen enviada ({KINDS[kind]}). Ya la está viendo: responde en una línea, sin repetir las cifras "
            "de la imagen; puedes ofrecer otra vista (torta por activo, por tipo o por sector, barras de "
            "rentabilidad o tabla).")
