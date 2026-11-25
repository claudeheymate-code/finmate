"""
Finmate - WhatsApp Cloud API de Meta (sin intermediario).

Funciones chicas y sin estado para:
  - enviar texto y plantillas por la Graph API,
  - validar que un webhook venga de verdad de Meta (firma X-Hub-Signature-256),
  - leer los mensajes entrantes del JSON que manda Meta.

Los teléfonos se guardan en la base con el mismo formato que usaba Twilio
("whatsapp:+56912345678"), así los usuarios, el panel y la memoria siguen
siendo los mismos al cambiar de proveedor. Meta usa solo dígitos
("56912345678"); las funciones de abajo convierten entre ambos.
"""

import hashlib
import hmac
import logging
from typing import Optional

import httpx

from config.settings import (
    META_APP_SECRET,
    META_GRAPH_VERSION,
    META_PHONE_NUMBER_ID,
    META_REGISTER_PIN,
    META_TEMPLATE_LANG,
    META_TEST_RECIPIENT,
    META_WABA_ID,
    META_WHATSAPP_TOKEN,
)

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com"


def to_meta(phone: str) -> str:
    """'whatsapp:+56912345678' / '+56 9 1234 5678' → '56912345678'."""
    return "".join(ch for ch in str(phone or "") if ch.isdigit())


def to_internal(wa_id: str) -> str:
    """'56912345678' (Meta) → 'whatsapp:+56912345678' (formato de la base)."""
    return "whatsapp:+" + to_meta(wa_id)


def is_configured() -> bool:
    return bool(META_WHATSAPP_TOKEN and META_PHONE_NUMBER_ID)


def _post(payload: dict) -> bool:
    ok = _do_post(payload)
    try:
        from finmate.services.usage import record_whatsapp

        kind = "read" if payload.get("status") == "read" else payload.get("type", "text")
        record_whatsapp(kind, ok)
    except Exception:
        pass
    return ok


def _do_post(payload: dict) -> bool:
    url = f"{GRAPH_BASE}/{META_GRAPH_VERSION}/{META_PHONE_NUMBER_ID}/messages"
    try:
        r = httpx.post(url, json=payload, timeout=15,
                       headers={"Authorization": f"Bearer {META_WHATSAPP_TOKEN}"})
    except Exception as e:
        logger.error(f"Meta: error de red enviando a {payload.get('to')}: {e}")
        return False
    if r.status_code >= 400:
        # El cuerpo trae el motivo (token vencido, número no permitido, plantilla no aprobada...)
        destino = payload.get("to") or ("marcar como leído" if payload.get("status") == "read" else "?")
        logger.error(f"Meta: envío rechazado ({r.status_code}) a {destino}: {r.text[:500]}")
        return False
    try:
        msg_id = (r.json().get("messages") or [{}])[0].get("id", "?")
    except Exception:
        msg_id = "?"
    if payload.get("status") != "read":
        logger.info(f"Meta: mensaje enviado a {payload.get('to')} (id {msg_id})")
    return True


def send_text(to: str, body: str) -> bool:
    return _post({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_meta(to),
        "type": "text",
        "text": {"body": body, "preview_url": False},
    })


def send_buttons(to: str, body: str, buttons: list) -> bool:
    """Mensaje con hasta 3 botones de respuesta rápida: buttons = [(id, título)].
    Solo funciona dentro de la ventana de 24 h (igual que el texto libre).
    El cuerpo admite hasta 1024 caracteres y los títulos hasta 20."""
    return _post({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_meta(to),
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body[:1024]},
            "action": {"buttons": [{"type": "reply", "reply": {"id": bid[:256], "title": title[:20]}}
                                   for bid, title in buttons[:3]]},
        },
    })


def send_template(to: str, name: str, variables: Optional[dict] = None,
                  lang: Optional[str] = None) -> bool:
    """Plantilla aprobada en WhatsApp Manager. `variables` usa las mismas
    claves que ya usaba el código con Twilio ({"1": ..., "2": ...}); se
    mandan en orden como {{1}}, {{2}}..."""
    template = {"name": name, "language": {"code": lang or META_TEMPLATE_LANG}}
    if variables:
        ordered = [variables[k] for k in sorted(variables, key=lambda k: int(k) if str(k).isdigit() else 0)]
        template["components"] = [{
            "type": "body",
            "parameters": [{"type": "text", "text": str(v)} for v in ordered],
        }]
    return _post({
        "messaging_product": "whatsapp",
        "to": to_meta(to),
        "type": "template",
        "template": template,
    })


def mark_as_read(message_id: str) -> None:
    """Muestra los dos tics azules al usuario (opcional, si falla no importa)."""
    _post({"messaging_product": "whatsapp", "status": "read", "message_id": message_id})


def valid_signature(raw_body: bytes, header: Optional[str]) -> bool:
    """Meta firma cada webhook con la clave secreta de la app. Si no hay
    META_APP_SECRET configurada no se puede validar: se acepta, pero queda
    advertido en el log (configurarla antes de abrir el bot a más gente)."""
    if not META_APP_SECRET:
        logger.warning("META_APP_SECRET no configurada: no se valida la firma del webhook de Meta.")
        return True
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(META_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):])


def parse_incoming(payload: dict) -> list[dict]:
    """Saca los mensajes de un webhook de Meta. Ignora los avisos de estado
    (enviado/entregado/leído). Devuelve [{id, from, type, text}]."""
    out = []
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        return out
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            names = {c.get("wa_id"): ((c.get("profile") or {}).get("name") or "").strip()
                     for c in value.get("contacts") or []}
            for m in value.get("messages") or []:
                mtype = m.get("type", "")
                text = ""
                button_id = ""
                if mtype == "text":
                    text = (m.get("text") or {}).get("body", "")
                elif mtype == "button":  # respuesta a un botón de plantilla
                    text = (m.get("button") or {}).get("text", "")
                    button_id = (m.get("button") or {}).get("payload", "") or ""
                elif mtype == "interactive":
                    it = m.get("interactive") or {}
                    reply = it.get("button_reply") or it.get("list_reply") or {}
                    text = reply.get("title", "")
                    button_id = reply.get("id", "") or ""
                media = None
                if mtype in ("image", "document", "audio", "video", "sticker"):
                    md = m.get(mtype) or {}
                    media = {"id": md.get("id", ""), "mime_type": md.get("mime_type", ""),
                             "filename": md.get("filename", ""), "caption": (md.get("caption") or "").strip()}
                    text = media["caption"]
                out.append({"id": m.get("id", ""), "from": m.get("from", ""), "type": mtype,
                            "text": text.strip(), "name": names.get(m.get("from"), ""), "media": media,
                            "button_id": button_id})
    return out


MAX_MEDIA_BYTES = 15 * 1024 * 1024   # WhatsApp permite hasta 100 MB en documentos; Claude, mucho menos


def download_media(media_id: str):
    """Descarga un archivo que mandó el usuario. Devuelve (bytes, mime_type) o (None, motivo)."""
    if not media_id or not is_configured():
        return None, "sin_configurar"
    headers = {"Authorization": f"Bearer {META_WHATSAPP_TOKEN}"}
    try:
        with httpx.Client(timeout=30) as c:
            meta = c.get(f"{GRAPH_BASE}/{META_GRAPH_VERSION}/{media_id}", headers=headers)
            meta.raise_for_status()
            info = meta.json()
            if int(info.get("file_size") or 0) > MAX_MEDIA_BYTES:
                return None, "muy_grande"
            r = c.get(info["url"], headers=headers, follow_redirects=True)
            r.raise_for_status()
            if len(r.content) > MAX_MEDIA_BYTES:
                return None, "muy_grande"
            return r.content, (info.get("mime_type") or r.headers.get("content-type") or "").split(";")[0]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"No pude descargar el archivo {media_id} de Meta: {type(e).__name__}")
        return None, "error"


def parse_statuses(payload: dict) -> list[dict]:
    """Avisos de estado de mensajes enviados (sent/delivered/read/failed).
    Los fallidos traen el motivo en `errors` (código + título), útil para
    saber por qué Meta no entregó un mensaje."""
    out = []
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        return out
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            for st in (change.get("value") or {}).get("statuses") or []:
                errs = st.get("errors") or []
                out.append({
                    "status": st.get("status", ""),
                    "to": st.get("recipient_id", ""),
                    "errors": [f"{e.get('code')} {e.get('title') or ''} {((e.get('error_data') or {}).get('details') or '')}".strip()
                               for e in errs],
                })
    return out


def startup_check() -> None:
    """Al arrancar: confirma que el token sirve y deja en el log el número y
    su estado; si hay META_WABA_ID, suscribe la app a esa cuenta de WhatsApp
    (sin esa suscripción Meta no avisa de los mensajes entrantes). Nunca
    lanza errores: solo informa en el log."""
    if not is_configured():
        return
    headers = {"Authorization": f"Bearer {META_WHATSAPP_TOKEN}"}
    base = f"{GRAPH_BASE}/{META_GRAPH_VERSION}"
    try:
        r = httpx.get(f"{base}/{META_PHONE_NUMBER_ID}", headers=headers, timeout=15,
                      params={"fields": "display_phone_number,verified_name,code_verification_status,quality_rating"})
        if r.status_code >= 400:
            logger.error(f"Meta (arranque): el token o el número no sirven ({r.status_code}): {r.text[:300]}")
            return
        d = r.json()
        logger.info(f"Meta (arranque): token OK · número {d.get('display_phone_number')} "
                    f"'{d.get('verified_name')}' · verificación {d.get('code_verification_status')} · calidad {d.get('quality_rating')}")
    except Exception as e:
        logger.error(f"Meta (arranque): no se pudo consultar el número: {e}")
        return
    if META_REGISTER_PIN:
        try:
            r = httpx.post(f"{base}/{META_PHONE_NUMBER_ID}/register", headers=headers, timeout=15,
                           json={"messaging_product": "whatsapp", "pin": META_REGISTER_PIN})
            if r.status_code >= 400:
                logger.error(f"Meta (arranque): no se pudo registrar el número ({r.status_code}): {r.text[:300]}")
            else:
                logger.info("Meta (arranque): número registrado en la Cloud API (ya puede enviar mensajes).")
        except Exception as e:
            logger.error(f"Meta (arranque): error registrando el número: {e}")
    if META_TEST_RECIPIENT:
        ok = send_template(META_TEST_RECIPIENT, "hello_world", None, lang="en_US")
        logger.info(f"Meta (arranque): mensaje de prueba hello_world a {to_meta(META_TEST_RECIPIENT)}: {'enviado' if ok else 'falló (ver error arriba)'}")
    if not META_WABA_ID:
        logger.info("Meta (arranque): sin META_WABA_ID, no se revisa la suscripción de la cuenta de WhatsApp.")
        return
    try:
        r = httpx.post(f"{base}/{META_WABA_ID}/subscribed_apps", headers=headers, timeout=15)
        if r.status_code >= 400:
            logger.error(f"Meta (arranque): no se pudo suscribir la app a la cuenta {META_WABA_ID} ({r.status_code}): {r.text[:300]}")
        else:
            logger.info(f"Meta (arranque): app suscrita a la cuenta de WhatsApp {META_WABA_ID} (avisos de mensajes activos).")
    except Exception as e:
        logger.error(f"Meta (arranque): error suscribiendo la cuenta de WhatsApp: {e}")
