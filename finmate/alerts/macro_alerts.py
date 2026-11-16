"""
Finmate - Recordatorios de publicaciones macro de EE.UU. (Etapa A).

Una vez al día (job en main.py) mira el calendario oficial de FRED y avisa
a cada usuario que sigue ese indicador (tool follow_indicator) cuando el
dato se publica HOY o MAÑANA. Sin FRED_API_KEY no hace nada.
"""
import datetime as dt
import logging
from typing import Optional

from config.settings import TWILIO_TEMPLATE_MARKET_NOTIFY_SID
from finmate.data_sources import fred

logger = logging.getLogger(__name__)

# release_id de FRED -> código de indicador que usa follow_indicator.
RELEASE_TO_CODE = {10: "CPI_US", 50: "NFP", 53: "GDP_US", 54: "PCE_US", 101: "FED_RATE"}


def check_macro_reminders(messenger=None, today: Optional[dt.date] = None,
                          releases: Optional[list] = None,
                          followers: Optional[dict] = None) -> int:
    today = today or dt.date.today()
    if releases is None:
        releases = fred.get_upcoming_releases(days_ahead=1, today=today)
    if not releases:
        return 0
    if followers is None:
        from finmate.db.news_repo import get_indicator_followers
        followers = get_indicator_followers()

    per_phone: dict = {}
    for rel in releases:
        code = RELEASE_TO_CODE.get(rel["release_id"])
        when = "hoy" if rel["date"] == today.isoformat() else "mañana"
        for _uid, phone in followers.get(code, []):
            per_phone.setdefault(phone, []).append(f"• {rel['name']}: se publica *{when}*")
    if not per_phone:
        return 0

    if messenger is None:
        from finmate.whatsapp.messenger import WhatsAppMessenger
        messenger = WhatsAppMessenger()
    sent = 0
    for phone, lines in per_phone.items():
        msg = "🗓️ *Datos que sigues*\n\n" + "\n".join(lines) + \
              "\n\n_Escribime después de la publicación y te explico cómo salió._"
        try:
            if TWILIO_TEMPLATE_MARKET_NOTIFY_SID:
                from finmate.alerts.pending import queue_pending
                queue_pending(phone, msg)
                ok = messenger.send_template(phone, TWILIO_TEMPLATE_MARKET_NOTIFY_SID,
                                             {"1": "Calendario económico"})
            else:
                ok = messenger.send_message(phone, msg)
        except Exception as e:
            logger.error(f"Error enviando recordatorio macro a {phone}: {e}")
            ok = False
        sent += 1 if ok else 0
    logger.info(f"Recordatorios macro: {sent} enviados")
    return sent
