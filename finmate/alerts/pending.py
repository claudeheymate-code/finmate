"""
Finmate - Cola de notificaciones pendientes (Fase 1.6)

Los mensajes que el bot manda por iniciativa propia (resumen semanal,
alertas de earnings/macro/noticias) son demasiado largos y dinámicos
(listas de longitud variable, texto condicional) para ser un Content
Template de WhatsApp Business aprobado por Meta — un template necesita
texto mayormente fijo con pocas variables cortas. La solución estándar:
se manda un template corto y estático avisando "tenés novedades" (eso sí
es válido como template) y acá se guarda el contenido real, por teléfono.
Cuando el usuario responde algo (lo que abre la ventana de 24hs de
mensajería libre de WhatsApp), el agente llama a la tool
`get_pending_notifications` (ver finmate/agent/tools.py) y recién ahí se
manda el contenido completo, ya como mensaje libre dentro de esa ventana.

Separado a propósito de los otros state files del proyecto
(alert_state.json: dedup de alertas ya enviadas; watchlist_alert_state.json:
dedup de alertas de watchlist ya enviadas): este no es un dedup, es una
cola de contenido todavía no entregado.
"""
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

STATE_FILE = "pending_notifications.json"

# Si el usuario nunca responde, no dejar crecer la cola sin límite — se
# queda solo con los últimos N avisos por teléfono.
MAX_PER_PHONE = 10


def _load() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save(state: dict) -> None:
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Error guardando cola de notificaciones pendientes: {e}")


def queue_pending(phone: str, text: str) -> None:
    """Agrega `text` a la cola de pendientes de `phone`."""
    state = _load()
    items = state.get(phone, [])
    items.append(text)
    if len(items) > MAX_PER_PHONE:
        items = items[-MAX_PER_PHONE:]
    state[phone] = items
    _save(state)


def pop_pending(phone: str) -> Optional[str]:
    """Devuelve y limpia todo el contenido pendiente de `phone`, unido en un
    solo mensaje. None si no había nada pendiente."""
    state = _load()
    items = state.pop(phone, None)
    if not items:
        return None
    _save(state)
    sep = "\n\n━━━━━━━━━━━━━━━━━━━━\n\n"
    return sep.join(items)


def has_pending(phone: str) -> bool:
    return bool(_load().get(phone))
