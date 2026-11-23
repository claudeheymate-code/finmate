"""Suscripciones y costos fijos del sistema (panel admin → Costos).

Se guardan en kv_state (clave admin:subscriptions) para que el administrador
las edite desde el panel. La primera vez se cargan valores iniciales con lo
que se sabe hoy; los montos se revisan y ajustan desde el panel.
"""
import uuid

from finmate.db.state_store import load_json, save_json

KEY = "admin:subscriptions"
CYCLES = ("mensual", "anual", "prepago", "por uso", "gratis")
CURRENCIES = ("USD", "CLP")

DEFAULTS = [
    {"name": "Railway", "detail": "Servidor del bot y del panel (plan Hobby)", "cost": 5, "currency": "USD",
     "cycle": "mensual", "renews_on": "", "url": "https://railway.com/account/billing", "essential": True,
     "notes": "Si no se paga, el bot y el panel se apagan."},
    {"name": "Claude API (Anthropic)", "detail": "Inteligencia del bot (créditos prepagados)", "cost": 5, "currency": "USD",
     "cycle": "prepago", "renews_on": "", "url": "https://platform.claude.com/settings/billing", "essential": True,
     "notes": "Saldo cargado el 23 nov 2026. El consumo real del mes aparece abajo, en «Consumo medido»."},
    {"name": "Meta · WhatsApp Cloud API", "detail": "Envío de mensajes de WhatsApp", "cost": 0, "currency": "USD",
     "cycle": "por uso", "renews_on": "",
     "url": "https://business.facebook.com/latest/billing_hub/payment_settings/?business_id=110632086967407",
     "essential": True,
     "notes": "Responder a quien te escribe es gratis (ventana de 24 h). Los avisos que inicia el bot con plantilla se cobran por mensaje."},
    {"name": "Chip prepago (+56 9 4061 3812)", "detail": "Número de WhatsApp del bot", "cost": 0, "currency": "CLP",
     "cycle": "mensual", "renews_on": "", "url": "", "essential": True,
     "notes": "Recargar periódicamente para que la compañía no dé de baja el número. Completa el monto de la recarga."},
    {"name": "Neon (Postgres)", "detail": "Base de datos", "cost": 0, "currency": "USD", "cycle": "gratis",
     "renews_on": "", "url": "https://console.neon.tech", "essential": False, "notes": "Plan gratis."},
    {"name": "Upstash (Redis)", "detail": "Caché", "cost": 0, "currency": "USD", "cycle": "gratis",
     "renews_on": "", "url": "https://console.upstash.com", "essential": False, "notes": "Plan gratis."},
    {"name": "OpenAI (transcripción de podcasts)", "detail": "Opcional", "cost": 0, "currency": "USD", "cycle": "prepago",
     "renews_on": "", "url": "https://platform.openai.com/settings/organization/billing", "essential": False,
     "notes": "Saldo USD 0: sin saldo se resume con la descripción del episodio."},
]


def list_subscriptions() -> list:
    data = load_json(KEY, None)
    if data is None:
        data = [dict(d, id=uuid.uuid4().hex[:8]) for d in DEFAULTS]
        save_json(KEY, data)
    return data


def _clean(item: dict) -> dict:
    name = str(item.get("name") or "").strip()[:80]
    if not name:
        raise ValueError("El nombre es obligatorio.")
    try:
        cost = float(item.get("cost") or 0)
    except (TypeError, ValueError):
        raise ValueError("El costo tiene que ser un número.")
    if cost < 0:
        raise ValueError("El costo no puede ser negativo.")
    currency = str(item.get("currency") or "USD").upper()
    if currency not in CURRENCIES:
        raise ValueError("Moneda: USD o CLP.")
    cycle = str(item.get("cycle") or "mensual").lower()
    if cycle not in CYCLES:
        raise ValueError("Ciclo: " + ", ".join(CYCLES) + ".")
    url = str(item.get("url") or "").strip()[:300]
    if url and not url.startswith(("http://", "https://")):
        raise ValueError("El link tiene que empezar con https://")
    return {
        "name": name, "detail": str(item.get("detail") or "").strip()[:140], "cost": cost,
        "currency": currency, "cycle": cycle, "renews_on": str(item.get("renews_on") or "").strip()[:10],
        "url": url, "essential": bool(item.get("essential")), "notes": str(item.get("notes") or "").strip()[:500],
    }


def upsert(item: dict) -> list:
    data = list_subscriptions()
    clean = _clean(item)
    sid = item.get("id")
    for i, d in enumerate(data):
        if d.get("id") == sid:
            data[i] = dict(clean, id=sid)
            break
    else:
        data.append(dict(clean, id=uuid.uuid4().hex[:8]))
    save_json(KEY, data)
    return data


def delete(sid: str) -> list:
    data = [d for d in list_subscriptions() if d.get("id") != sid]
    save_json(KEY, data)
    return data


def monthly_totals(data: list) -> dict:
    """Costo mensual fijo por moneda (anual ÷ 12; prepago, por uso y gratis no suman)."""
    out = {"USD": 0.0, "CLP": 0.0}
    for d in data:
        if d["cycle"] == "mensual":
            out[d["currency"]] += d["cost"]
        elif d["cycle"] == "anual":
            out[d["currency"]] += d["cost"] / 12
    return {k: round(v, 2) for k, v in out.items()}
