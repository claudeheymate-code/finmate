"""
Finmate - Cliente de FRED (Federal Reserve Bank of St. Louis).

Reemplaza a Alpha Vantage para la macro de EE.UU.: FRED es gratis, permite
120 consultas por minuto y trae el calendario oficial de publicaciones.
Si FRED_API_KEY no está configurada, todas las funciones devuelven vacío y
el bot sigue funcionando sin esta fuente.
"""
import datetime as dt
import logging
from typing import Optional

import httpx

from config.settings import FRED_API_KEY

logger = logging.getLogger(__name__)

BASE_URL = "https://api.stlouisfed.org/fred"

# Series que el bot muestra. `units`: lin = nivel, pc1 = variación % anual.
SERIES = {
    "FED_RATE": {"id": "DFEDTARU", "units": "lin", "label": "Tasa Fed (techo del rango)", "suffix": "%"},
    "CPI_US": {"id": "CPIAUCSL", "units": "pc1", "label": "Inflación EE.UU. (IPC, anual)", "suffix": "%"},
    "CORE_CPI_US": {"id": "CPILFESL", "units": "pc1", "label": "Inflación subyacente (anual)", "suffix": "%"},
    "UNEMPLOYMENT_US": {"id": "UNRATE", "units": "lin", "label": "Desempleo EE.UU.", "suffix": "%"},
    "UST_10Y": {"id": "DGS10", "units": "lin", "label": "Bono del Tesoro 10 años", "suffix": "%"},
    "UST_2Y": {"id": "DGS2", "units": "lin", "label": "Bono del Tesoro 2 años", "suffix": "%"},
}

# Publicaciones importantes (release_id de FRED) para avisar antes del dato.
RELEASES = {
    10: "Inflación EE.UU. (IPC)",
    50: "Informe de empleo (NFP)",
    53: "PIB EE.UU.",
    54: "Ingreso y gasto personal (PCE)",
    101: "Decisión de tasas de la Fed (FOMC)",
}


def is_configured() -> bool:
    return bool(FRED_API_KEY)


def _get(path: str, params: dict, client: Optional[httpx.Client] = None) -> Optional[dict]:
    if not FRED_API_KEY:
        return None
    params = {**params, "api_key": FRED_API_KEY, "file_type": "json"}
    try:
        if client is not None:
            r = client.get(f"{BASE_URL}/{path}", params=params)
        else:
            r = httpx.get(f"{BASE_URL}/{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Error consultando FRED {path}: {e}")
        return None


def get_latest(code: str, client: Optional[httpx.Client] = None) -> Optional[dict]:
    """Último valor disponible de una serie del catálogo SERIES.
    Devuelve {"code","label","value","date","suffix"} o None."""
    meta = SERIES.get(code)
    if not meta:
        return None
    data = _get(
        "series/observations",
        {"series_id": meta["id"], "units": meta["units"], "sort_order": "desc", "limit": 10},
        client,
    )
    for obs in (data or {}).get("observations", []):
        value = obs.get("value")
        if value in (None, "", "."):  # FRED usa "." para días sin dato
            continue
        try:
            return {"code": code, "label": meta["label"], "value": float(value),
                    "date": obs.get("date"), "suffix": meta["suffix"]}
        except ValueError:
            continue
    return None


def get_snapshot() -> list:
    """Últimos valores de todas las series del catálogo (las que respondan)."""
    if not FRED_API_KEY:
        return []
    out = []
    with httpx.Client(timeout=10) as client:
        for code in SERIES:
            item = get_latest(code, client)
            if item:
                out.append(item)
    return out


def get_upcoming_releases(days_ahead: int = 7, today: Optional[dt.date] = None) -> list:
    """Fechas de publicación de RELEASES dentro de los próximos `days_ahead`
    días. Devuelve [{"release_id","name","date"}] ordenado por fecha."""
    if not FRED_API_KEY:
        return []
    today = today or dt.date.today()
    end = today + dt.timedelta(days=days_ahead)
    out = []
    with httpx.Client(timeout=10) as client:
        for release_id, name in RELEASES.items():
            data = _get(
                "release/dates",
                {"release_id": release_id, "realtime_start": today.isoformat(),
                 "realtime_end": "9999-12-31", "include_release_dates_with_no_data": "true",
                 "sort_order": "asc", "limit": 5},
                client,
            )
            for item in (data or {}).get("release_dates", []):
                try:
                    d = dt.date.fromisoformat(item.get("date", ""))
                except ValueError:
                    continue
                if today <= d <= end:
                    out.append({"release_id": release_id, "name": name, "date": d.isoformat()})
    out.sort(key=lambda x: x["date"])
    return out
