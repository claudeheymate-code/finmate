"""
Finmate - Mensajería WhatsApp (Meta Cloud API).

El resto del código siempre llama a send_message / broadcast / send_template;
el envío real lo hace finmate/whatsapp/meta_cloud.py.
"""

import logging
from typing import Optional

from config.settings import WHATSAPP_PROVIDER, WHATSAPP_RECIPIENTS
from finmate.whatsapp import meta_cloud

logger = logging.getLogger(__name__)

# WhatsApp tiene un límite de ~1600 caracteres por mensaje
MAX_MESSAGE_LENGTH = 1500


class WhatsAppMessenger:
    """Envía mensajes por WhatsApp usando la Cloud API de Meta."""

    def __init__(self):
        self.provider = WHATSAPP_PROVIDER
        if not meta_cloud.is_configured():
            logger.error("Faltan META_WHATSAPP_TOKEN o META_PHONE_NUMBER_ID: no se pueden enviar mensajes")

    def _split_message(self, text: str) -> list[str]:
        """Divide un mensaje largo en partes que respeten el límite de WhatsApp,
        cortando en saltos de línea o espacios para no romper el formato."""
        if len(text) <= MAX_MESSAGE_LENGTH:
            return [text]
        parts = []
        while text:
            if len(text) <= MAX_MESSAGE_LENGTH:
                parts.append(text)
                break
            cut_point = text.rfind("\n", 0, MAX_MESSAGE_LENGTH)
            if cut_point == -1 or cut_point < MAX_MESSAGE_LENGTH // 2:
                cut_point = text.rfind(" ", 0, MAX_MESSAGE_LENGTH)
            if cut_point == -1:
                cut_point = MAX_MESSAGE_LENGTH
            parts.append(text[:cut_point].strip())
            text = text[cut_point:].strip()
        return parts

    def send_message(self, to: str, body: str) -> bool:
        """Envía un mensaje a un número específico (con formato de WhatsApp y los emojis
        que eligió el usuario, ver finmate/utils/text.py)."""
        from finmate.utils.text import prepare_for

        body = prepare_for(to, body)
        parts = self._split_message(body)
        ok = True
        for i, part in enumerate(parts):
            if len(parts) > 1:
                part = f"({i + 1}/{len(parts)})\n{part}"
            ok = meta_cloud.send_text(to, part) and ok
        return ok

    def send_buttons(self, to: str, body: str, buttons: list, fallback: Optional[str] = None) -> bool:
        """Mensaje con botones (máx. 3). Si es muy largo o Meta lo rechaza, manda `fallback` como texto."""
        from finmate.utils.text import prepare_for

        body = prepare_for(to, body)
        if len(body) <= 1024:
            try:
                if meta_cloud.send_buttons(to, body, buttons):
                    return True
            except Exception as e:  # noqa: BLE001
                logger.warning(f"No pude mandar botones a {to}: {e}")
        return self.send_message(to, fallback or body)

    def broadcast(self, body: str, recipients: Optional[list[str]] = None) -> dict:
        """Envía un mensaje a todos los destinatarios. Retorna el resultado por número."""
        targets = recipients or WHATSAPP_RECIPIENTS
        if not targets:
            logger.warning("No hay destinatarios configurados para WhatsApp")
            return {}
        results = {number: self.send_message(number, body) for number in targets}
        logger.info(f"Broadcast completado: {sum(results.values())}/{len(targets)} exitosos")
        return results

    def send_template(self, to: str, content_sid: str, content_variables: Optional[dict] = None) -> bool:
        """Envía una plantilla aprobada por Meta. `content_sid` es el NOMBRE de la
        plantilla en WhatsApp Manager (se mantiene el nombre del parámetro)."""
        return meta_cloud.send_template(to, content_sid, content_variables)

    def broadcast_template(self, content_sid: str, content_variables: Optional[dict] = None,
                           recipients: Optional[list[str]] = None) -> dict:
        """Envía una plantilla a todos los destinatarios."""
        targets = recipients or WHATSAPP_RECIPIENTS
        if not targets:
            logger.warning("No hay destinatarios configurados para WhatsApp")
            return {}
        results = {number: self.send_template(number, content_sid, content_variables) for number in targets}
        logger.info(f"Broadcast de plantilla completado: {sum(results.values())}/{len(targets)} exitosos")
        return results
