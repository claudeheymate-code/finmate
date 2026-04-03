"""
Finmate - Cliente Finnhub
Obtiene: noticias de mercado, calendario de earnings, datos económicos.
API gratuita: https://finnhub.io (60 calls/min free tier)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from config.settings import FINNHUB_API_KEY

logger = logging.getLogger(__name__)

BASE_URL = "https://finnhub.io/api/v1"


class FinnhubClient:
    """Cliente para la API de Finnhub."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or FINNHUB_API_KEY
        if not self.api_key:
            logger.warning("FINNHUB_API_KEY no configurada")

    def _headers(self) -> dict:
        return {"X-Finnhub-Token": self.api_key}

    async def _get(self, endpoint: str, params: dict = None) -> dict | list | None:
        """Realiza un GET a la API de Finnhub."""
        url = f"{BASE_URL}{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, params=params or {}, headers=self._headers())
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Finnhub HTTP error {e.response.status_code}: {e}")
            return None
        except Exception as e:
            logger.error(f"Finnhub request error: {e}")
            return None

    # ----------------------------------------------------------
    # Noticias de mercado
    # ----------------------------------------------------------
    async def get_market_news(self, category: str = "general", min_id: int = 0) -> list[dict]:
        """
        Obtiene noticias generales de mercado.
        Categorías: general, forex, crypto, merger
        """
        data = await self._get("/news", {"category": category, "minId": min_id})
        if not data:
            return []

        # Filtramos solo las últimas 7 días
        cutoff = datetime.utcnow() - timedelta(days=7)
        news = []
        for item in data:
            ts = datetime.utcfromtimestamp(item.get("datetime", 0))
            if ts >= cutoff:
                news.append({
                    "id": item.get("id"),
                    "headline": item.get("headline", ""),
                    "summary": item.get("summary", ""),
                    "source": item.get("source", ""),
                    "url": item.get("url", ""),
                    "datetime": ts.isoformat(),
                    "category": item.get("category", category),
                    "image": item.get("image", ""),
                })
        return news

    async def get_company_news(self, symbol: str, days_back: int = 7) -> list[dict]:
        """Noticias específicas de una empresa."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        data = await self._get(
            "/company-news", {"symbol": symbol, "from": from_date, "to": today}
        )
        if not data:
            return []
        return [
            {
                "headline": item.get("headline", ""),
                "summary": item.get("summary", ""),
                "source": item.get("source", ""),
                "url": item.get("url", ""),
                "datetime": datetime.utcfromtimestamp(item.get("datetime", 0)).isoformat(),
            }
            for item in data[:20]
        ]

    # ----------------------------------------------------------
    # Calendario de Earnings
    # ----------------------------------------------------------
    async def get_earnings_calendar(
        self, from_date: str = None, to_date: str = None
    ) -> list[dict]:
        """
        Calendario de presentación de resultados.
        Fechas en formato YYYY-MM-DD.
        """
        if not from_date:
            from_date = datetime.utcnow().strftime("%Y-%m-%d")
        if not to_date:
            to_date = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")

        data = await self._get(
            "/calendar/earnings", {"from": from_date, "to": to_date}
        )
        if not data or "earningsCalendar" not in data:
            return []

        results = []
        for item in data["earningsCalendar"]:
            results.append({
                "symbol": item.get("symbol", ""),
                "date": item.get("date", ""),
                "hour": item.get("hour", ""),  # bmo = before market open, amc = after market close
                "eps_estimate": item.get("epsEstimate"),
                "eps_actual": item.get("epsActual"),
                "revenue_estimate": item.get("revenueEstimate"),
                "revenue_actual": item.get("revenueActual"),
                "quarter": item.get("quarter"),
                "year": item.get("year"),
            })
        return results

    # ----------------------------------------------------------
    # Calendario Económico (datos macro)
    # ----------------------------------------------------------
    async def get_economic_calendar(
        self, from_date: str = None, to_date: str = None
    ) -> list[dict]:
        """Calendario de eventos macroeconómicos."""
        if not from_date:
            from_date = datetime.utcnow().strftime("%Y-%m-%d")
        if not to_date:
            to_date = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")

        data = await self._get(
            "/calendar/economic", {"from": from_date, "to": to_date}
        )
        if not data or "economicCalendar" not in data:
            return []

        events = []
        for item in data.get("economicCalendar", []):
            impact = item.get("impact", "low")
            # Solo incluimos eventos de impacto medio y alto
            if impact in ("medium", "high"):
                events.append({
                    "country": item.get("country", ""),
                    "event": item.get("event", ""),
                    "date": item.get("date", ""),
                    "time": item.get("time", ""),
                    "impact": impact,
                    "forecast": item.get("estimate"),
                    "previous": item.get("prev"),
                    "actual": item.get("actual"),
                    "unit": item.get("unit", ""),
                })
        return events

    # ----------------------------------------------------------
    # Cotización básica
    # ----------------------------------------------------------
    async def get_quote(self, symbol: str) -> dict | None:
        """Cotización actual de un símbolo."""
        data = await self._get("/quote", {"symbol": symbol})
        if not data:
            return None
        return {
            "symbol": symbol,
            "current": data.get("c"),
            "change": data.get("d"),
            "change_pct": data.get("dp"),
            "high": data.get("h"),
            "low": data.get("l"),
            "open": data.get("o"),
            "previous_close": data.get("pc"),
        }
