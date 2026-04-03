"""
Finmate - Integración con Google Calendar
Crea eventos financieros automáticamente en el calendario del usuario.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

import os
import json

from config.settings import GOOGLE_CREDENTIALS_FILE, GOOGLE_CALENDAR_ID

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_FILE = "token.json"


class GoogleCalendarClient:
    """Gestiona eventos financieros en Google Calendar."""

    def __init__(self):
        self.service = None
        self.calendar_id = GOOGLE_CALENDAR_ID
        self._authenticate()

    def _authenticate(self):
        """Autenticación OAuth2 con Google Calendar."""
        creds = None

        if os.path.exists(TOKEN_FILE):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            except Exception as e:
                logger.warning(f"Error leyendo token: {e}")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Error refrescando token: {e}")
                    creds = None

            if not creds:
                if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
                    logger.error(
                        f"Archivo de credenciales '{GOOGLE_CREDENTIALS_FILE}' no encontrado. "
                        "Descárgalo desde Google Cloud Console."
                    )
                    return

                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        GOOGLE_CREDENTIALS_FILE, SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    logger.error(f"Error en flujo OAuth: {e}")
                    return

            # Guardar token para futuros usos
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())

        try:
            self.service = build("calendar", "v3", credentials=creds)
            logger.info("Google Calendar autenticado correctamente")
        except Exception as e:
            logger.error(f"Error construyendo servicio Calendar: {e}")

    def _is_ready(self) -> bool:
        if not self.service:
            logger.warning("Google Calendar no está autenticado")
            return False
        return True

    # ----------------------------------------------------------
    # Crear eventos financieros
    # ----------------------------------------------------------
    def create_event(
        self,
        title: str,
        description: str,
        start_date: str,
        start_time: str = "09:00",
        duration_hours: float = 1,
        timezone: str = "America/Santiago",
        color_id: str = None,
    ) -> Optional[str]:
        """
        Crea un evento en Google Calendar.
        Retorna el ID del evento o None si falla.
        """
        if not self._is_ready():
            return None

        try:
            start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
            end_dt = start_dt + timedelta(hours=duration_hours)

            event = {
                "summary": title,
                "description": description,
                "start": {
                    "dateTime": start_dt.isoformat(),
                    "timeZone": timezone,
                },
                "end": {
                    "dateTime": end_dt.isoformat(),
                    "timeZone": timezone,
                },
                "reminders": {
                    "useDefault": False,
                    "overrides": [
                        {"method": "popup", "minutes": 30},
                        {"method": "email", "minutes": 60},
                    ],
                },
            }

            if color_id:
                event["colorId"] = color_id

            result = self.service.events().insert(
                calendarId=self.calendar_id, body=event
            ).execute()

            logger.info(f"Evento creado: {result.get('htmlLink')}")
            return result.get("id")

        except Exception as e:
            logger.error(f"Error creando evento: {e}")
            return None

    def create_all_day_event(
        self, title: str, description: str, date: str, color_id: str = None
    ) -> Optional[str]:
        """Crea un evento de todo el día."""
        if not self._is_ready():
            return None

        try:
            event = {
                "summary": title,
                "description": description,
                "start": {"date": date},
                "end": {"date": date},
                "reminders": {
                    "useDefault": False,
                    "overrides": [{"method": "email", "minutes": 480}],  # 8h antes
                },
            }
            if color_id:
                event["colorId"] = color_id

            result = self.service.events().insert(
                calendarId=self.calendar_id, body=event
            ).execute()
            return result.get("id")
        except Exception as e:
            logger.error(f"Error creando evento all-day: {e}")
            return None

    # ----------------------------------------------------------
    # Poblar calendario con eventos financieros de la semana
    # ----------------------------------------------------------
    def populate_weekly_calendar(self, earnings: list[dict], economic_events: list[dict]) -> int:
        """
        Crea eventos en Calendar para los earnings y datos macro de la semana.
        Retorna el número de eventos creados.
        """
        count = 0

        # Colores: 9 = azul (earnings), 11 = rojo (macro), 10 = verde (otro)
        for e in earnings:
            title = f"📊 Earnings: {e.get('symbol', 'N/A')}"
            desc = (
                f"Presentación de resultados de {e['symbol']}\n"
                f"EPS estimado: {e.get('eps_estimate', 'N/D')}\n"
                f"Revenue estimado: {e.get('revenue_estimate', 'N/D')}\n\n"
                "— Finmate (informativo, no recomendación)"
            )
            date = e.get("date", "")
            if date:
                event_id = self.create_all_day_event(title, desc, date, color_id="9")
                if event_id:
                    count += 1

        for ev in economic_events:
            title = f"🌍 {ev.get('country', '')}: {ev.get('event', '')}"
            impact_label = "ALTO" if ev.get("impact") == "high" else "MEDIO"
            desc = (
                f"Dato macroeconómico — Impacto: {impact_label}\n"
                f"Esperado: {ev.get('forecast', 'N/D')}\n"
                f"Anterior: {ev.get('previous', 'N/D')}\n\n"
                "— Finmate (informativo, no recomendación)"
            )
            date = ev.get("date", "")
            time = ev.get("time", "")
            if date:
                if time:
                    event_id = self.create_event(
                        title, desc, date, start_time=time,
                        duration_hours=0.5, color_id="11"
                    )
                else:
                    event_id = self.create_all_day_event(title, desc, date, color_id="11")
                if event_id:
                    count += 1

        logger.info(f"Calendario semanal poblado: {count} eventos creados")
        return count

    # ----------------------------------------------------------
    # Limpiar eventos antiguos de Finmate
    # ----------------------------------------------------------
    def clear_old_events(self, days_old: int = 14):
        """Elimina eventos de Finmate más antiguos que X días."""
        if not self._is_ready():
            return

        try:
            cutoff = (datetime.utcnow() - timedelta(days=days_old)).isoformat() + "Z"
            now = datetime.utcnow().isoformat() + "Z"

            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=cutoff,
                timeMax=now,
                maxResults=100,
                q="Finmate",
            ).execute()

            events = events_result.get("items", [])
            deleted = 0
            for event in events:
                if "Finmate" in event.get("description", ""):
                    self.service.events().delete(
                        calendarId=self.calendar_id, eventId=event["id"]
                    ).execute()
                    deleted += 1

            logger.info(f"Limpieza: {deleted} eventos antiguos eliminados")
        except Exception as e:
            logger.error(f"Error limpiando eventos: {e}")
