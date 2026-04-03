"""
Finmate - Agregador de Datos Financieros
Combina información de Finnhub, FMP y Alpha Vantage en una sola interfaz.
Deduplica, prioriza y normaliza los datos.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from .finnhub_client import FinnhubClient
from .fmp_client import FMPClient
from .alpha_vantage_client import AlphaVantageClient

logger = logging.getLogger(__name__)

# Empresas más relevantes para seguimiento (top por capitalización)
TOP_COMPANIES = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B",
    "JPM", "V", "JNJ", "WMT", "PG", "MA", "UNH", "HD", "DIS", "BAC",
    "XOM", "PFE", "KO", "PEP", "NFLX", "CRM", "AMD", "INTC",
]


class FinancialDataAggregator:
    """Agrega datos de múltiples fuentes financieras."""

    def __init__(self):
        self.finnhub = FinnhubClient()
        self.fmp = FMPClient()
        self.alpha_vantage = AlphaVantageClient()

    # ----------------------------------------------------------
    # Noticias consolidadas
    # ----------------------------------------------------------
    async def get_top_news(self, limit: int = 10) -> list[dict]:
        """
        Obtiene las noticias más relevantes combinando Finnhub y FMP.
        Deduplica por similitud de título.
        """
        finnhub_news, fmp_news = await asyncio.gather(
            self.finnhub.get_market_news(),
            self.fmp.get_general_news(limit=30),
            return_exceptions=True,
        )

        all_news = []

        if isinstance(finnhub_news, list):
            for n in finnhub_news:
                all_news.append({
                    "title": n.get("headline", ""),
                    "summary": n.get("summary", ""),
                    "source": n.get("source", "Finnhub"),
                    "url": n.get("url", ""),
                    "datetime": n.get("datetime", ""),
                    "type": "market_news",
                })

        if isinstance(fmp_news, list):
            for n in fmp_news:
                all_news.append({
                    "title": n.get("title", ""),
                    "summary": n.get("text", ""),
                    "source": n.get("source", "FMP"),
                    "url": n.get("url", ""),
                    "datetime": n.get("published", ""),
                    "type": "market_news",
                })

        # Deduplicar por similitud de título (simple)
        seen_titles = set()
        unique_news = []
        for item in all_news:
            key = item["title"].lower()[:60]
            if key not in seen_titles and item["title"]:
                seen_titles.add(key)
                unique_news.append(item)

        # Ordenar por fecha (más reciente primero)
        unique_news.sort(key=lambda x: x.get("datetime", ""), reverse=True)
        return unique_news[:limit]

    # ----------------------------------------------------------
    # Calendario de Earnings consolidado
    # ----------------------------------------------------------
    async def get_earnings_calendar(
        self, from_date: str = None, to_date: str = None
    ) -> list[dict]:
        """
        Calendario de earnings combinando Finnhub y FMP.
        Filtra para mostrar solo empresas relevantes.
        """
        finnhub_earnings, fmp_earnings = await asyncio.gather(
            self.finnhub.get_earnings_calendar(from_date, to_date),
            self.fmp.get_earnings_calendar(from_date, to_date),
            return_exceptions=True,
        )

        earnings_map = {}  # symbol -> datos

        # Finnhub como fuente primaria
        if isinstance(finnhub_earnings, list):
            for e in finnhub_earnings:
                symbol = e.get("symbol", "")
                if symbol:
                    earnings_map[symbol] = {
                        "symbol": symbol,
                        "date": e.get("date", ""),
                        "hour": e.get("hour", ""),
                        "eps_estimate": e.get("eps_estimate"),
                        "eps_actual": e.get("eps_actual"),
                        "revenue_estimate": e.get("revenue_estimate"),
                        "revenue_actual": e.get("revenue_actual"),
                        "source": "finnhub",
                    }

        # FMP complementa
        if isinstance(fmp_earnings, list):
            for e in fmp_earnings:
                symbol = e.get("symbol", "")
                if symbol and symbol not in earnings_map:
                    earnings_map[symbol] = {
                        "symbol": symbol,
                        "date": e.get("date", ""),
                        "hour": "",
                        "eps_estimate": e.get("eps_estimate"),
                        "eps_actual": e.get("eps_actual"),
                        "revenue_estimate": e.get("revenue_estimate"),
                        "revenue_actual": e.get("revenue_actual"),
                        "source": "fmp",
                    }

        # Priorizar empresas top
        all_earnings = list(earnings_map.values())
        top_earnings = [e for e in all_earnings if e["symbol"] in TOP_COMPANIES]
        other_earnings = [e for e in all_earnings if e["symbol"] not in TOP_COMPANIES]

        # Ordenar por fecha
        top_earnings.sort(key=lambda x: x.get("date", ""))
        other_earnings.sort(key=lambda x: x.get("date", ""))

        return top_earnings + other_earnings[:20]

    # ----------------------------------------------------------
    # Calendario Económico consolidado
    # ----------------------------------------------------------
    async def get_economic_calendar(
        self, from_date: str = None, to_date: str = None
    ) -> list[dict]:
        """
        Calendario macroeconómico combinando Finnhub y FMP.
        Solo eventos de impacto medio y alto.
        """
        finnhub_econ, fmp_econ = await asyncio.gather(
            self.finnhub.get_economic_calendar(from_date, to_date),
            self.fmp.get_economic_calendar(from_date, to_date),
            return_exceptions=True,
        )

        events_map = {}

        if isinstance(finnhub_econ, list):
            for e in finnhub_econ:
                key = f"{e.get('country', '')}_{e.get('event', '')}_{e.get('date', '')}"
                events_map[key] = {
                    "country": e.get("country", ""),
                    "event": e.get("event", ""),
                    "date": e.get("date", ""),
                    "time": e.get("time", ""),
                    "impact": e.get("impact", "medium"),
                    "forecast": e.get("forecast"),
                    "previous": e.get("previous"),
                    "actual": e.get("actual"),
                    "source": "finnhub",
                }

        if isinstance(fmp_econ, list):
            for e in fmp_econ:
                key = f"{e.get('country', '')}_{e.get('event', '')}_{e.get('date', '')}"
                if key not in events_map:
                    events_map[key] = {
                        "country": e.get("country", ""),
                        "event": e.get("event", ""),
                        "date": e.get("date", ""),
                        "time": "",
                        "impact": e.get("impact", "medium"),
                        "forecast": e.get("forecast"),
                        "previous": e.get("previous"),
                        "actual": e.get("actual"),
                        "source": "fmp",
                    }

        events = list(events_map.values())
        # Priorizar por impacto y fecha
        impact_order = {"high": 0, "medium": 1, "low": 2}
        events.sort(key=lambda x: (x.get("date", ""), impact_order.get(x.get("impact", "low"), 2)))

        return events

    # ----------------------------------------------------------
    # Datos macro de EE.UU. (Alpha Vantage)
    # ----------------------------------------------------------
    async def get_us_macro_snapshot(self) -> dict:
        """Snapshot de datos macro de EE.UU."""
        gdp, cpi, fed_rate, unemployment, treasury = await asyncio.gather(
            self.alpha_vantage.get_real_gdp(),
            self.alpha_vantage.get_cpi(),
            self.alpha_vantage.get_federal_funds_rate(),
            self.alpha_vantage.get_unemployment(),
            self.alpha_vantage.get_treasury_yield(),
            return_exceptions=True,
        )

        def _safe_latest(data, label: str) -> dict:
            if isinstance(data, list) and len(data) > 0:
                return {"label": label, "latest": data[0], "previous": data[1] if len(data) > 1 else None}
            return {"label": label, "latest": None, "previous": None}

        return {
            "gdp": _safe_latest(gdp, "PIB Real (trimestral)"),
            "cpi": _safe_latest(cpi, "CPI (mensual)"),
            "fed_rate": _safe_latest(fed_rate, "Tasa Fed Funds"),
            "unemployment": _safe_latest(unemployment, "Desempleo"),
            "treasury_10y": _safe_latest(treasury, "Bono 10 años"),
        }

    # ----------------------------------------------------------
    # Resumen completo semanal
    # ----------------------------------------------------------
    async def get_weekly_data(self) -> dict:
        """
        Recopila todos los datos necesarios para el resumen semanal.
        Retorna un dict con noticias, earnings, datos macro e índices.
        """
        today = datetime.utcnow().strftime("%Y-%m-%d")
        next_week = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")

        news, earnings, economic, macro, indices, movers = await asyncio.gather(
            self.get_top_news(limit=10),
            self.get_earnings_calendar(today, next_week),
            self.get_economic_calendar(today, next_week),
            self.get_us_macro_snapshot(),
            self.fmp.get_major_indices(),
            self.fmp.get_market_movers(),
            return_exceptions=True,
        )

        return {
            "date_generated": datetime.utcnow().isoformat(),
            "news": news if isinstance(news, list) else [],
            "earnings": earnings if isinstance(earnings, list) else [],
            "economic_calendar": economic if isinstance(economic, list) else [],
            "us_macro": macro if isinstance(macro, dict) else {},
            "indices": indices if isinstance(indices, list) else [],
            "market_movers": movers if isinstance(movers, dict) else {},
        }
