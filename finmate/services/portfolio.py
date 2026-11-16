"""Valorización del portafolio: ganancia/pérdida, distribución y top 3.

Lo usan el panel web (/api/portafolio, /api/resumen) y puede usarlo el bot.
La clase de activo y el sector se completan solos la primera vez que se ve
una posición y quedan guardados en `portfolio_holdings` (el usuario puede
corregirlos desde el panel).
"""
import logging
from typing import Callable, Optional

from finmate.db.repository import get_portfolio_detailed, set_holding_classification
from finmate.services import quotes

logger = logging.getLogger(__name__)

RENTA_VARIABLE = "Renta variable"
RENTA_FIJA = "Renta fija"
ASSET_CLASSES = (RENTA_VARIABLE, RENTA_FIJA)

# ETFs de bonos más comunes → renta fija
BOND_ETFS = {
    "TLT", "IEF", "SHY", "BND", "AGG", "LQD", "HYG", "JNK", "TIP", "SCHP", "VGIT", "VGLT",
    "VGSH", "BIL", "SGOV", "SHV", "GOVT", "MUB", "EMB", "BSV", "BIV", "BLV", "VCIT", "VCSH",
    "IGSB", "IGIB", "USIG", "SPAB", "SPTL", "SPTS", "VTEB", "BNDX", "IAGG", "FLOT",
}
# ETFs de índice amplio → renta variable, sector propio
BROAD_EQUITY_ETFS = {
    "SPY", "VOO", "IVV", "VTI", "QQQ", "QQQM", "DIA", "IWM", "VT", "VXUS", "VEA", "VWO",
    "EFA", "EEM", "SCHB", "SCHX", "ITOT", "RSP", "SPLG",
}

# finnhubIndustry (inglés) → sector en español
_INDUSTRY_MAP = {
    "technology": "Tecnología", "semiconductors": "Tecnología", "software": "Tecnología",
    "banking": "Financiero", "financial services": "Financiero", "insurance": "Financiero",
    "energy": "Energía", "oil & gas": "Energía", "utilities": "Servicios básicos",
    "beverages": "Consumo", "food products": "Consumo", "retail": "Consumo",
    "consumer products": "Consumo", "automobiles": "Consumo", "hotels, restaurants & leisure": "Consumo",
    "textiles, apparel & luxury goods": "Consumo", "tobacco": "Consumo",
    "pharmaceuticals": "Salud", "health care": "Salud", "biotechnology": "Salud",
    "life sciences tools & services": "Salud",
    "media": "Comunicaciones", "communications": "Comunicaciones",
    "telecommunication": "Comunicaciones", "entertainment": "Comunicaciones",
    "real estate": "Inmobiliario", "industrial conglomerates": "Industrial",
    "machinery": "Industrial", "aerospace & defense": "Industrial", "airlines": "Industrial",
    "logistics & transportation": "Industrial", "building": "Industrial",
    "chemicals": "Materiales", "metals & mining": "Materiales",
}


def classify_symbol(symbol: str, profile_fn: Callable[[str], dict] = None) -> tuple:
    """(clase de activo, sector) para un símbolo."""
    symbol = symbol.upper()
    if symbol in BOND_ETFS:
        return RENTA_FIJA, "Bonos"
    if symbol in BROAD_EQUITY_ETFS:
        return RENTA_VARIABLE, "Índice amplio"
    profile = (profile_fn or quotes.get_profile)(symbol) or {}
    industry = (profile.get("finnhubIndustry") or "").strip()
    sector = _INDUSTRY_MAP.get(industry.lower(), industry or "Otros")
    return RENTA_VARIABLE, sector


def _group(positions: list, key: str) -> list:
    totals: dict = {}
    for p in positions:
        if p["value"] is None:
            continue
        totals[p[key]] = totals.get(p[key], 0.0) + p["value"]
    grand = sum(totals.values())
    return [
        {"name": k, "value": v, "pct": (v / grand * 100) if grand else 0.0}
        for k, v in sorted(totals.items(), key=lambda kv: -kv[1])
    ]


def compute_portfolio(
    user_id: int,
    quote_fn: Optional[Callable[[str], Optional[dict]]] = None,
    profile_fn: Optional[Callable[[str], dict]] = None,
) -> dict:
    """Valoriza todas las posiciones del usuario.

    Devuelve {"positions", "totals", "by_class", "by_sector", "top_winners",
    "top_losers", "missing_prices"}. Las posiciones sin precio aparecen con
    value=None y no cuentan en totales ni distribución.
    """
    quote_fn = quote_fn or quotes.get_quote
    positions = []
    missing = []
    for h in get_portfolio_detailed(user_id):
        symbol = h["symbol"]
        asset_class, sector = h["asset_class"], h["sector"]
        if not asset_class or not sector:
            try:
                asset_class, sector = classify_symbol(symbol, profile_fn)
                set_holding_classification(user_id, symbol, asset_class, sector)
            except Exception as e:
                logger.warning(f"No pude clasificar {symbol}: {e}")
                asset_class, sector = asset_class or RENTA_VARIABLE, sector or "Otros"

        q = quote_fn(symbol) or {}
        price = q.get("price")
        qty = h["quantity"]
        avg = h["avg_cost"]
        value = price * qty if price is not None else None
        cost = avg * qty if avg is not None else None
        pnl = value - cost if (value is not None and cost is not None) else None
        pnl_pct = (pnl / cost * 100) if (pnl is not None and cost) else None
        if price is None:
            missing.append(symbol)
        positions.append({
            "symbol": symbol, "quantity": qty, "avg_cost": avg, "price": price,
            "change_pct": q.get("change_pct"), "is_closed": bool(q.get("is_closed")),
            "value": value, "cost": cost, "pnl": pnl, "pnl_pct": pnl_pct,
            "asset_class": asset_class, "sector": sector,
        })

    total_value = sum(p["value"] for p in positions if p["value"] is not None)
    with_cost = [p for p in positions if p["value"] is not None and p["cost"] is not None]
    total_cost = sum(p["cost"] for p in with_cost)
    total_pnl = sum(p["pnl"] for p in with_cost) if with_cost else None
    day_change = 0.0
    for p in positions:
        if p["value"] is not None and p["change_pct"] is not None:
            day_change += p["value"] - p["value"] / (1 + p["change_pct"] / 100)
    prev_value = total_value - day_change
    for p in positions:
        p["weight_pct"] = (p["value"] / total_value * 100) if (p["value"] is not None and total_value) else None
    positions.sort(key=lambda p: -(p["value"] or 0))

    ranked = sorted([p for p in positions if p["pnl_pct"] is not None], key=lambda p: -p["pnl_pct"])
    winners = [p for p in ranked if p["pnl_pct"] > 0][:3]
    losers = [p for p in reversed(ranked) if p["pnl_pct"] < 0][:3]

    return {
        "positions": positions,
        "totals": {
            "value": total_value,
            "cost": total_cost if with_cost else None,
            "pnl": total_pnl,
            "pnl_pct": (total_pnl / total_cost * 100) if (total_pnl is not None and total_cost) else None,
            "day_change": day_change,
            "day_change_pct": (day_change / prev_value * 100) if prev_value else None,
            "count": len(positions),
        },
        "by_class": _group(positions, "asset_class"),
        "by_sector": _group(positions, "sector"),
        "top_winners": winners,
        "top_losers": losers,
        "missing_prices": missing,
    }
