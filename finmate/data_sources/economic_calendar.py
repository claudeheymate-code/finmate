"""
Finmate — Calendario económico curado (Plan Fase 4)

Sin API externa — lista curada de ~15 indicadores clave para inversores
con exposición a mercados de EE.UU. y Chile.
"""

INDICATOR_CATALOG = {
    "FED_RATE":        {"name": "Decisión de tasa Fed",          "country": "US", "freq": "~8 veces/año",  "relevance": "alta"},
    "CPI_US":          {"name": "Inflación EE.UU. (CPI)",        "country": "US", "freq": "mensual",       "relevance": "alta"},
    "NFP":             {"name": "Nóminas no agrícolas (NFP)",     "country": "US", "freq": "mensual",       "relevance": "alta"},
    "GDP_US":          {"name": "PIB EE.UU.",                     "country": "US", "freq": "trimestral",    "relevance": "alta"},
    "PCE_US":          {"name": "Inflación PCE EE.UU.",           "country": "US", "freq": "mensual",       "relevance": "alta"},
    "UNEMPLOYMENT_US": {"name": "Desempleo EE.UU.",               "country": "US", "freq": "mensual",       "relevance": "media"},
    "RETAIL_SALES_US": {"name": "Ventas minoristas EE.UU.",       "country": "US", "freq": "mensual",       "relevance": "media"},
    "ISM_MFG":         {"name": "ISM Manufacturero",              "country": "US", "freq": "mensual",       "relevance": "media"},
    "FOMC_MINUTES":    {"name": "Minutas FOMC",                   "country": "US", "freq": "~8 veces/año",  "relevance": "media"},
    "IPC_CL":          {"name": "IPC Chile",                      "country": "CL", "freq": "mensual",       "relevance": "alta"},
    "GDP_CL":          {"name": "PIB Chile (Imacec)",             "country": "CL", "freq": "mensual",       "relevance": "alta"},
    "BCCh_RATE":       {"name": "Tasa Banco Central de Chile",    "country": "CL", "freq": "~8 veces/año",  "relevance": "alta"},
    "UNEMPLOYMENT_CL": {"name": "Desempleo Chile",                "country": "CL", "freq": "mensual",       "relevance": "media"},
    "COPPER":          {"name": "Precio del cobre",               "country": "CL", "freq": "diario",        "relevance": "alta"},
    "USD_CLP":         {"name": "Dólar / Peso chileno",           "country": "CL", "freq": "diario",        "relevance": "alta"},
}


def get_indicator_info(code: str) -> dict:
    """Devuelve los metadatos de un indicador por su code, o None si no existe."""
    return INDICATOR_CATALOG.get(code.upper())


def list_all_indicators() -> list:
    """Devuelve lista de dicts con code + metadatos, ordenada por country y relevance."""
    result = []
    for code, meta in INDICATOR_CATALOG.items():
        result.append({"code": code, **meta})
    return sorted(result, key=lambda x: (x["country"], x["relevance"] != "alta", x["name"]))


def format_catalog_for_whatsapp() -> str:
    """Texto formateado para WhatsApp con todos los indicadores disponibles."""
    lines = ["*INDICADORES ECONÓMICOS DISPONIBLES*", ""]
    us_items = [x for x in list_all_indicators() if x["country"] == "US"]
    cl_items = [x for x in list_all_indicators() if x["country"] == "CL"]

    lines.append("🇺🇸 *EE.UU.:*")
    for item in us_items:
        lines.append(f"  • `{item['code']}` — {item['name']} ({item['freq']})")
    lines.append("")
    lines.append("🇨🇱 *Chile:*")
    for item in cl_items:
        lines.append(f"  • `{item['code']}` — {item['name']} ({item['freq']})")
    lines.append("")
    lines.append("Decime 'seguime el CPI_US' para recibir avisos cuando se publique.")
    return "\n".join(lines)
