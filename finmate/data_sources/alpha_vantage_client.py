"""
Finmate - Cliente Alpha Vantage
Complementa con: cotizaciones, datos macro (GDP, CPI, tasas de interés).
API gratuita: https://www.alphavantage.co (25 calls/day free tier)
Se usa como respaldo y para datos macro de EE.UU.
"""

import logging
from typing import Optional

import httpx

from config.settings import ALPHA_VANTAGE_API_KEY

logger = logging.getLogger(__name__)

BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageClient:
    """Cliente para Alpha Vantage - enfocado en datos macroeconómicos."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or ALPHA_VANTAGE_API_KEY
        if not self.api_key:
            logger.warning("ALPHA_VANTAGE_API_KEY no configurada")

    async def _get(self, params: dict) -> dict | None:
        params["apikey"] = self.api_key
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                if "Error Message" in data or "Note" in data:
                    logger.warning(f"Alpha Vantage warning: {data}")
                    return None
                return data
        except Exception as e:
            logger.error(f"Alpha Vantage error: {e}")
            return None

    # ----------------------------------------------------------
    # Datos Macroeconómicos de EE.UU.
    # ----------------------------------------------------------
    async def get_real_gdp(self, interval: str = "quarterly") -> list[dict]:
        """PIB real de EE.UU."""
        data = await self._get({"function": "REAL_GDP", "interval": interval})
        if not data or "data" not in data:
            return []
        return [
            {"date": item["date"], "value": item["value"]}
            for item in data["data"][:8]  # Últimos 8 períodos
        ]

    async def get_cpi(self, interval: str = "monthly") -> list[dict]:
        """Índice de Precios al Consumidor (CPI) de EE.UU."""
        data = await self._get({"function": "CPI", "interval": interval})
        if not data or "data" not in data:
            return []
        return [
            {"date": item["date"], "value": item["value"]}
            for item in data["data"][:12]
        ]

    async def get_federal_funds_rate(self, interval: str = "monthly") -> list[dict]:
        """Tasa de fondos federales."""
        data = await self._get(
            {"function": "FEDERAL_FUNDS_RATE", "interval": interval}
        )
        if not data or "data" not in data:
            return []
        return [
            {"date": item["date"], "value": item["value"]}
            for item in data["data"][:12]
        ]

    async def get_unemployment(self) -> list[dict]:
        """Tasa de desempleo de EE.UU."""
        data = await self._get({"function": "UNEMPLOYMENT"})
        if not data or "data" not in data:
            return []
        return [
            {"date": item["date"], "value": item["value"]}
            for item in data["data"][:12]
        ]

    async def get_treasury_yield(self, interval: str = "monthly", maturity: str = "10year") -> list[dict]:
        """Rendimiento de bonos del Tesoro."""
        data = await self._get(
            {"function": "TREASURY_YIELD", "interval": interval, "maturity": maturity}
        )
        if not data or "data" not in data:
            return []
        return [
            {"date": item["date"], "value": item["value"]}
            for item in data["data"][:12]
        ]

    # ----------------------------------------------------------
    # Cotización (respaldo)
    # ----------------------------------------------------------
    async def get_quote(self, symbol: str) -> dict | None:
        """Cotización de un símbolo (usar como respaldo de Finnhub)."""
        data = await self._get(
            {"function": "GLOBAL_QUOTE", "symbol": symbol}
        )
        if not data or "Global Quote" not in data:
            return None
        q = data["Global Quote"]
        return {
            "symbol": q.get("01. symbol", symbol),
            "price": q.get("05. price"),
            "change": q.get("09. change"),
            "change_pct": q.get("10. change percent", "").replace("%", ""),
            "volume": q.get("06. volume"),
        }
