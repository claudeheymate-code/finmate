"""
Finmate - Cliente Financial Modeling Prep (FMP)
Obtiene: calendarios económicos, earnings, noticias, cotizaciones.
API gratuita: https://financialmodelingprep.com (250 calls/day free tier)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from config.settings import FMP_API_KEY

logger = logging.getLogger(__name__)

BASE_URL = "https://financialmodelingprep.com/api/v3"


class FMPClient:
    """Cliente para Financial Modeling Prep."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or FMP_API_KEY
        if not self.api_key:
            logger.warning("FMP_API_KEY no configurada")

    def _params(self, extra: dict = None) -> dict:
        params = {"apikey": self.api_key}
        if extra:
            params.update(extra)
        return params

    async def _get(self, endpoint: str, params: dict = None) -> dict | list | None:
        url = f"{BASE_URL}{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, params=self._params(params))
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"FMP HTTP error {e.response.status_code}: {e}")
            return None
        except Exception as e:
            logger.error(f"FMP request error: {e}")
            return None

    # ----------------------------------------------------------
    # Calendario de Earnings
    # ----------------------------------------------------------
    async def get_earnings_calendar(
        self, from_date: str = None, to_date: str = None
    ) -> list[dict]:
        """Próximos earnings de empresas."""
        if not from_date:
            from_date = datetime.utcnow().strftime("%Y-%m-%d")
        if not to_date:
            to_date = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")

        data = await self._get(
            "/earning_calendar", {"from": from_date, "to": to_date}
        )
        if not data or not isinstance(data, list):
            return []

        return [
            {
                "symbol": item.get("symbol", ""),
                "date": item.get("date", ""),
                "eps_estimate": item.get("epsEstimated"),
                "eps_actual": item.get("eps"),
                "revenue_estimate": item.get("revenueEstimated"),
                "revenue_actual": item.get("revenue"),
                "fiscal_period": item.get("fiscalDateEnding", ""),
            }
            for item in data
        ]

    # ----------------------------------------------------------
    # Calendario Económico
    # ----------------------------------------------------------
    async def get_economic_calendar(
        self, from_date: str = None, to_date: str = None
    ) -> list[dict]:
        """Eventos macroeconómicos."""
        if not from_date:
            from_date = datetime.utcnow().strftime("%Y-%m-%d")
        if not to_date:
            to_date = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")

        data = await self._get(
            "/economic_calendar", {"from": from_date, "to": to_date}
        )
        if not data or not isinstance(data, list):
            return []

        events = []
        for item in data:
            impact = item.get("impact", "Low")
            if impact in ("Medium", "High"):
                events.append({
                    "country": item.get("country", ""),
                    "event": item.get("event", ""),
                    "date": item.get("date", ""),
                    "impact": impact.lower(),
                    "forecast": item.get("estimate"),
                    "previous": item.get("previous"),
                    "actual": item.get("actual"),
                    "currency": item.get("currency", ""),
                })
        return events

    # ----------------------------------------------------------
    # Noticias
    # ----------------------------------------------------------
    async def get_general_news(self, limit: int = 20) -> list[dict]:
        """Noticias generales del mercado."""
        data = await self._get("/fmp/articles", {"page": 0, "size": limit})
        if not data or "content" not in data:
            # Intentar endpoint alternativo
            data = await self._get("/stock_news", {"limit": limit})
            if not data or not isinstance(data, list):
                return []
            return [
                {
                    "title": item.get("title", ""),
                    "text": item.get("text", ""),
                    "url": item.get("url", ""),
                    "source": item.get("site", ""),
                    "published": item.get("publishedDate", ""),
                    "symbol": item.get("symbol", ""),
                }
                for item in data
            ]

        return [
            {
                "title": item.get("title", ""),
                "text": item.get("content", "")[:300],
                "url": item.get("link", ""),
                "source": "FMP",
                "published": item.get("date", ""),
            }
            for item in data.get("content", [])
        ]

    # ----------------------------------------------------------
    # Top gainers / losers (para contexto de mercado)
    # ----------------------------------------------------------
    async def get_market_movers(self) -> dict:
        """Top gainers y losers del día."""
        gainers = await self._get("/stock_market/gainers") or []
        losers = await self._get("/stock_market/losers") or []

        def _format(items: list) -> list[dict]:
            return [
                {
                    "symbol": i.get("symbol", ""),
                    "name": i.get("name", ""),
                    "price": i.get("price"),
                    "change_pct": i.get("changesPercentage"),
                }
                for i in items[:5]
            ]

        return {"gainers": _format(gainers), "losers": _format(losers)}

    # ----------------------------------------------------------
    # Índices principales
    # ----------------------------------------------------------
    async def get_major_indices(self) -> list[dict]:
        """Cotización de los principales índices."""
        symbols = ["^GSPC", "^DJI", "^IXIC", "^FTSE", "^N225", "^STOXX50E"]
        data = await self._get(f"/quote/{','.join(symbols)}")
        if not data or not isinstance(data, list):
            return []
        return [
            {
                "symbol": item.get("symbol", ""),
                "name": item.get("name", ""),
                "price": item.get("price"),
                "change": item.get("change"),
                "change_pct": item.get("changesPercentage"),
            }
            for item in data
        ]
