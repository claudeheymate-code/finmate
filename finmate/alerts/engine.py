"""
Finmate - Motor de Alertas
Detecta eventos relevantes y genera alertas en tiempo real.
Mantiene estado de lo ya notificado para evitar duplicados.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from finmate.data_sources.aggregator import FinancialDataAggregator
from finmate.whatsapp.messenger import WhatsAppMessenger
from finmate.whatsapp.formatter import (
    format_earnings_alert,
    format_economic_alert,
    format_breaking_news_alert,
    format_weekly_summary,
)
try:
    from finmate.calendar.gcal_client import GoogleCalendarClient
except ImportError:
    GoogleCalendarClient = None

logger = logging.getLogger(__name__)

# Archivo para persistir estado de alertas enviadas
STATE_FILE = "alert_state.json"


class AlertEngine:
    """
    Motor principal de alertas de Finmate.
    - Detecta earnings publicados
    - Detecta datos macro publicados
    - Detecta noticias de alto impacto
    - Genera y envía el resumen semanal
    - Actualiza Google Calendar
    """

    def __init__(self):
        self.aggregator = FinancialDataAggregator()
        self.messenger = WhatsAppMessenger()
        # Google Calendar es opcional — no debe romper el bot si falla
        self.calendar = None
        if GoogleCalendarClient is not None:
            try:
                self.calendar = GoogleCalendarClient()
            except Exception as e:
                logger.warning(f"Google Calendar no disponible: {e}")
        self.state = self._load_state()

    def _load_state(self) -> dict:
        """Carga el estado de alertas ya enviadas."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "sent_earnings": [],      # IDs de earnings ya notificados
            "sent_economic": [],      # IDs de eventos macro ya notificados
            "sent_news": [],          # IDs de noticias ya notificadas
            "last_weekly_summary": "",  # Fecha del último resumen semanal
            "last_calendar_update": "",  # Fecha última actualización de Calendar
        }

    def _save_state(self):
        """Persiste el estado."""
        try:
            # Limpiar listas antiguas (mantener solo últimos 200 IDs)
            for key in ["sent_earnings", "sent_economic", "sent_news"]:
                if len(self.state.get(key, [])) > 200:
                    self.state[key] = self.state[key][-200:]
            with open(STATE_FILE, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Error guardando estado: {e}")

    # ----------------------------------------------------------
    # Chequeo de alertas en tiempo real
    # ----------------------------------------------------------
    async def check_and_send_alerts(self):
        """
        Chequea todas las fuentes y envía alertas si hay novedades.
        Diseñado para correr cada 30 minutos.
        """
        logger.info("Iniciando chequeo de alertas...")

        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

            # Obtener datos del día
            earnings, economic, news = await asyncio.gather(
                self.aggregator.get_earnings_calendar(today, tomorrow),
                self.aggregator.get_economic_calendar(today, tomorrow),
                self.aggregator.get_top_news(limit=15),
                return_exceptions=True,
            )

            alerts_sent = 0

            # --- Alertas de Earnings ---
            if isinstance(earnings, list):
                for e in earnings:
                    earning_id = f"{e.get('symbol')}_{e.get('date')}"
                    # Solo alertar si tiene resultado actual (ya publicado)
                    if (
                        e.get("eps_actual") is not None
                        and earning_id not in self.state["sent_earnings"]
                    ):
                        msg = format_earnings_alert(e)
                        self.messenger.broadcast(msg)
                        self.state["sent_earnings"].append(earning_id)
                        alerts_sent += 1
                        logger.info(f"Alerta earnings enviada: {e.get('symbol')}")

            # --- Alertas de datos macro ---
            if isinstance(economic, list):
                for ev in economic:
                    event_id = f"{ev.get('country')}_{ev.get('event')}_{ev.get('date')}"
                    # Solo alertar si tiene dato actual publicado
                    if (
                        ev.get("actual") is not None
                        and event_id not in self.state["sent_economic"]
                    ):
                        msg = format_economic_alert(ev)
                        self.messenger.broadcast(msg)
                        self.state["sent_economic"].append(event_id)
                        alerts_sent += 1
                        logger.info(f"Alerta macro enviada: {ev.get('event')}")

            # --- Alertas de noticias relevantes ---
            # Solo las primeras 3 noticias más recientes no enviadas
            if isinstance(news, list):
                news_alerts = 0
                for item in news:
                    news_id = item.get("title", "")[:80]
                    if (
                        news_id
                        and news_id not in self.state["sent_news"]
                        and news_alerts < 3
                    ):
                        msg = format_breaking_news_alert(item)
                        self.messenger.broadcast(msg)
                        self.state["sent_news"].append(news_id)
                        alerts_sent += 1
                        news_alerts += 1

            self._save_state()
            logger.info(f"Chequeo completado: {alerts_sent} alertas enviadas")

        except Exception as e:
            logger.error(f"Error en chequeo de alertas: {e}")

    # ----------------------------------------------------------
    # Resumen Semanal
    # ----------------------------------------------------------
    async def send_weekly_summary(self):
        """
        Genera y envía el resumen semanal completo.
        También actualiza Google Calendar con los eventos de la próxima semana.
        """
        logger.info("Generando resumen semanal...")

        try:
            # Obtener todos los datos
            data = await self.aggregator.get_weekly_data()

            # Formatear y enviar por WhatsApp
            message = format_weekly_summary(data)
            self.messenger.broadcast(message)

            # Actualizar Google Calendar (si está disponible)
            if self.calendar:
                earnings = data.get("earnings", [])
                economic = data.get("economic_calendar", [])
                if earnings or economic:
                    events_created = self.calendar.populate_weekly_calendar(earnings, economic)
                    logger.info(f"Calendar actualizado: {events_created} eventos")

                # Limpiar eventos viejos
                self.calendar.clear_old_events()

            # Registrar
            self.state["last_weekly_summary"] = datetime.utcnow().isoformat()
            self.state["last_calendar_update"] = datetime.utcnow().isoformat()
            self._save_state()

            logger.info("Resumen semanal enviado exitosamente")

        except Exception as e:
            logger.error(f"Error en resumen semanal: {e}")

    # ----------------------------------------------------------
    # Resumen bajo demanda (cuando el usuario lo pide por WhatsApp)
    # ----------------------------------------------------------
    async def send_on_demand_summary(self, to: str):
        """Envía un resumen rápido cuando el usuario lo solicita."""
        logger.info(f"Resumen bajo demanda para {to}")

        try:
            data = await self.aggregator.get_weekly_data()
            message = format_weekly_summary(data)
            self.messenger.send_message(to, message)
        except Exception as e:
            logger.error(f"Error en resumen on-demand: {e}")
