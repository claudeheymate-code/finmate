"""
Finmate - Motor de Alertas
Detecta eventos relevantes y genera alertas en tiempo real.
Mantiene estado de lo ya notificado para evitar duplicados.

Fase 1.6: el resumen semanal y las alertas de earnings/macro/noticias son
mensajes largos y dinámicos (listas de longitud variable) — no entran en
un Content Template de WhatsApp Business aprobado por Meta. Si hay
templates de aviso configurados (TEMPLATE_MARKET_NOTIFY /
TEMPLATE_WEEKLY_SUMMARY_NOTIFY), se manda ese template corto y
el contenido real se encola (finmate/alerts/pending.py) para cuando el
usuario responda. Si no están configurados, se sigue mandando todo como
texto libre, igual que hasta ahora (sandbox/desarrollo).
"""

import asyncio
import logging
from datetime import datetime, timedelta

from config.settings import (
    TEMPLATE_MARKET_NOTIFY,
    TEMPLATE_WEEKLY_SUMMARY_NOTIFY,
)
from finmate.alerts.pending import queue_pending
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
        from finmate.db.state_store import load_json

        saved = load_json(STATE_FILE, None)
        if saved is not None:
            return saved
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
            from finmate.db.state_store import save_json

            save_json(STATE_FILE, self.state)
        except Exception as e:
            logger.error(f"Error guardando estado: {e}")

    # ----------------------------------------------------------
    # Envío (Fase 1.6: template de aviso + cola si está configurado)
    # ----------------------------------------------------------
    @staticmethod
    def _recipients(kind: str, symbol: str = None) -> list:
        """Quién recibe cada aviso general: lo elige cada usuario en su panel
        (Ajustes → Avisos) o por chat. Ya no se usa la lista fija."""
        from finmate.db.settings_repo import recipients_for

        return recipients_for(kind, symbol)

    def _broadcast_or_queue(self, msg: str, category_label: str, phones: list = None) -> None:
        """Envía `msg` a todos los destinatarios. Si hay un template de aviso
        de mercado configurado (requerido para producción real de WhatsApp
        Business), manda el template corto y encola el contenido completo
        para cuando el usuario responda (ver finmate/alerts/pending.py). Si
        no, cae a mensaje de texto libre directo, como hasta ahora."""
        from finmate.services.workday import filter_recipients

        phones = filter_recipients(list(phones or []), msg, category_label)   # fuera de la jornada: al próximo resumen
        if not phones:
            return
        if TEMPLATE_MARKET_NOTIFY:
            for phone in phones:
                queue_pending(phone, msg)
                self.messenger.send_template(
                    phone, TEMPLATE_MARKET_NOTIFY, {"1": category_label}
                )
        else:
            self.messenger.broadcast(msg, recipients=phones)

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
                        self._broadcast_or_queue(msg, "Resultados corporativos",
                                                 self._recipients("earnings", e.get("symbol")))
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
                        self._broadcast_or_queue(msg, "Dato macroeconómico", self._recipients("macro"))
                        self.state["sent_economic"].append(event_id)
                        alerts_sent += 1
                        logger.info(f"Alerta macro enviada: {ev.get('event')}")

            # --- Alertas de noticias relevantes ---
            # Solo las primeras 3 noticias más recientes no enviadas
            if isinstance(news, list):
                news_alerts = 0
                news_phones = self._recipients("market_news")
                for item in news:
                    news_id = item.get("title", "")[:80]
                    if (
                        news_id
                        and news_id not in self.state["sent_news"]
                        and news_alerts < 3
                    ):
                        msg = format_breaking_news_alert(item)
                        self._broadcast_or_queue(msg, "Noticia de mercado", news_phones)
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

            # Formatear y enviar por WhatsApp (Fase 1.6: template de aviso +
            # cola si está configurado; si no, texto libre como hasta ahora)
            message = format_weekly_summary(data)
            # Panel web → Ajustes: quien apagó el resumen semanal no lo recibe.
            from finmate.services.workday import filter_recipients

            recipients = filter_recipients(self._recipients("weekly"), message, "Resumen semanal")
            if TEMPLATE_WEEKLY_SUMMARY_NOTIFY:
                for phone in recipients:
                    queue_pending(phone, message)
                    self.messenger.send_template(phone, TEMPLATE_WEEKLY_SUMMARY_NOTIFY)
            elif recipients:
                self.messenger.broadcast(message, recipients=recipients)

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
