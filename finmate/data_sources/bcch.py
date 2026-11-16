"""
Finmate - Cliente de la API BDE del Banco Central de Chile.

Usa el endpoint REST con API Key Token (gratis, se obtiene en "Mi Cuenta" de
la Base de Datos Estadísticos). Sin BCCH_API_TOKEN, devuelve vacío y el bot
sigue funcionando sin esta fuente.
"""
import datetime as dt
import json
import logging
from typing import Optional

import httpx

from config.settings import BCCH_API_TOKEN

logger = logging.getLogger(__name__)

BASE_URL = "https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx"

# days_back: ventana hacia atrás para encontrar el último dato publicado
# (las series mensuales necesitan más de un mes de margen).
SERIES = {
    "USD_CLP": {"id": "F073.TCO.PRE.Z.D", "label": "Dólar observado", "fmt": "clp", "days_back": 15},
    "UF": {"id": "F073.UFF.PRE.Z.D", "label": "UF", "fmt": "clp", "days_back": 15},
    "TPM": {"id": "F022.TPM.TIN.D001.NO.Z.D", "label": "Tasa de política monetaria", "fmt": "pct", "days_back": 60},
    "IPC_CL": {"id": "F074.IPC.VAR.Z.Z.C.M", "label": "IPC Chile (variación mensual)", "fmt": "pct", "days_back": 100},
}


def is_configured() -> bool:
    return bool(BCCH_API_TOKEN)


def get_latest(code: str, client: Optional[httpx.Client] = None,
               today: Optional[dt.date] = None) -> Optional[dict]:
    """Último valor publicado de una serie de SERIES.
    Devuelve {"code","label","value","date","fmt"} o None."""
    meta = SERIES.get(code)
    if not meta or not BCCH_API_TOKEN:
        return None
    today = today or dt.date.today()
    params = {
        "token": BCCH_API_TOKEN,
        "function": "GetSeries",
        "timeseries": meta["id"],
        "firstdate": (today - dt.timedelta(days=meta["days_back"])).isoformat(),
        "lastdate": today.isoformat(),
    }
    try:
        if client is not None:
            r = client.get(BASE_URL, params=params)
        else:
            r = httpx.get(BASE_URL, params=params, timeout=10)
        r.raise_for_status()
        # La API responde en ISO-8859-1 (los títulos traen tildes): decodificar
        # con el charset que declara, no con UTF-8.
        data = json.loads(r.content.decode(r.encoding or "latin-1", errors="replace"))
    except Exception as e:
        logger.error(f"Error consultando Banco Central ({code}): {e}")
        return None
    if data.get("Codigo") not in (0, "0"):
        logger.error(f"Banco Central respondió error para {code}: {data.get('Descripcion')}")
        return None
    obs = (data.get("Series") or {}).get("Obs") or []
    for o in reversed(obs):
        if o.get("statusCode") != "OK":
            continue
        try:
            value = float(str(o.get("value")).replace(",", "."))
        except (TypeError, ValueError):
            continue
        # La API responde fechas como DD-MM-YYYY.
        raw = o.get("indexDateString", "")
        try:
            date = dt.datetime.strptime(raw, "%d-%m-%Y").date().isoformat()
        except ValueError:
            date = raw
        return {"code": code, "label": meta["label"], "value": value, "date": date, "fmt": meta["fmt"]}
    return None


def get_snapshot() -> list:
    if not BCCH_API_TOKEN:
        return []
    out = []
    with httpx.Client(timeout=10) as client:
        for code in SERIES:
            item = get_latest(code, client)
            if item:
                out.append(item)
    return out
