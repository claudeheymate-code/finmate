"""
Finmate - Mensajería WhatsApp via Twilio
Envía mensajes formateados a los destinatarios configurados.
"""

import logging
from typing import Optional

from twilio.rest import Client as TwilioClient

from config.settings import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_FROM,
    WHATSAPP_RECIPIENTS,
)

logger = logging.getLogger(__name__)

# WhatsApp tiene un límite de ~1600 caracteres por mensaje
MAX_MESSAGE_LENGTH = 1500


class WhatsAppMessenger:
    """Envía mensajes por WhatsApp usando Twilio."""

    def __init__(self):
        if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
            logger.error("Twilio credentials no configuradas")
            self.client = None
        else:
            self.client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        self.from_number = TWILIO_WHATSAPP_FROM

    def _split_message(self, text: str) -> list[str]:
        """
        Divide un mensaje largo en partes que respeten el límite de WhatsApp.
        Intenta cortar en saltos de línea para no romper el formato.
        """
        if len(text) <= MAX_MESSAGE_LENGTH:
            return [text]

        parts = []
        while text:
            if len(text) <= MAX_MESSAGE_LENGTH:
                parts.append(text)
                break

            # Buscar el último salto de línea antes del límite
            cut_point = text.rfind("\n", 0, MAX_MESSAGE_LENGTH)
            if cut_point == -1 or cut_point < MAX_MESSAGE_LENGTH // 2:
                # Si no hay buen punto de corte, cortar en espacio
                cut_point = text.rfind(" ", 0, MAX_MESSAGE_LENGTH)
            if cut_point == -1:
                cut_point = MAX_MESSAGE_LENGTH

            parts.append(text[:cut_point].strip())
            text = text[cut_point:].strip()

        return parts

    def send_message(self, to: str, body: str) -> bool:
        """Envía un mensaje a un número específico."""
        if not self.client:
            logger.error("Twilio client no inicializado")
            return False

        parts = self._split_message(body)
        success = True

        for i, part in enumerate(parts):
            try:
                if len(parts) > 1:
                    part = f"({i + 1}/{len(parts)})\n{part}"

                message = self.client.messages.create(
                    from_=self.from_number,
                    body=part,
                    to=to,
                )
                logger.info(f"Mensaje enviado a {to}: SID {message.sid}")
            except Exception as e:
                logger.error(f"Error enviando mensaje a {to}: {e}")
                success = False

        return success

    def broadcast(self, body: str, recipients: Optional[list[str]] = None) -> dict:
        """
        Envía un mensaje a todos los destinatarios configurados.
        Retorna un dict con el resultado por número.
        """
        targets = recipients or WHATSAPP_RECIPIENTS
        if not targets:
            logger.warning("No hay destinatarios configurados para WhatsApp")
            return {}

        results = {}
        for number in targets:
            results[number] = self.send_message(number, body)

        sent = sum(1 for v in results.values() if v)
        logger.info(f"Broadcast completado: {sent}/{len(targets)} exitosos")
        return results
