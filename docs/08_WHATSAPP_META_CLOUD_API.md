# 08 — WhatsApp por Meta directo (Cloud API)

Desde el 20 nov 2026 el bot puede hablar con WhatsApp **sin Twilio**, directo
con la WhatsApp Cloud API de Meta. Motivo: Twilio no dejó verificar la cuenta,
cobra USD 0,005 extra por mensaje y Meta directo no tiene cuota mensual.

## Cómo elige el proveedor

`config/settings.py`: si están `META_WHATSAPP_TOKEN` y `META_PHONE_NUMBER_ID`,
se usa Meta; si no, Twilio (como antes). Se puede forzar con
`WHATSAPP_PROVIDER=meta|twilio`.

## Variables de Railway

| Variable | De dónde sale |
|---|---|
| `META_WHATSAPP_TOKEN` | Token **permanente** de un usuario del sistema (Business Settings → Usuarios del sistema → Generar token, permisos `whatsapp_business_messaging` y `whatsapp_business_management`). El token temporal de la pantalla "Configuración de la API" dura 24 h: sirve solo para probar. |
| `META_PHONE_NUMBER_ID` | App → WhatsApp → Configuración de la API → "Identificador del número de teléfono" (15 dígitos). **No** el de la cuenta (WABA). |
| `META_VERIFY_TOKEN` | Un texto que inventas (ej. `finmate-webhook-2026`). El mismo se escribe al configurar el webhook en Meta. |
| `META_APP_SECRET` | App → Configuración de la app → Básica → "Clave secreta de la app". Valida que los webhooks vengan de Meta. |
| `META_TEMPLATE_*` | Nombres de las plantillas aprobadas (ver abajo). Vacías = texto libre. |

## Webhook

- URL: `https://<dominio-de-railway>/whatsapp/webhook` (la misma ruta que usaba Twilio).
- Token de verificación: el valor de `META_VERIFY_TOKEN`.
- Suscribirse al campo **messages**.
- El bot responde 200 al tiro y contesta en un hilo aparte (Meta reintenta si
  demora); los reintentos se ignoran por id de mensaje.

## Plantillas (para avisos que el bot inicia)

Crear en WhatsApp Manager → Plantillas, categoría **Utility**, idioma Español
(`es`), con los textos de `05_WHATSAPP_TEMPLATES_TWILIO.md` (mismas variables
`{{1}}`, `{{2}}`, `{{3}}`). Cuando estén aprobadas, cargar en Railway:
`META_TEMPLATE_WATCHLIST_ALERT=finmate_watchlist_alert`,
`META_TEMPLATE_MARKET_NOTIFY=finmate_market_notify`,
`META_TEMPLATE_WEEKLY_SUMMARY_NOTIFY=finmate_weekly_summary_notify`.

## Número

- Para probar: Meta da un número de prueba gratis que puede escribir a hasta
  5 números autorizados.
- Producción: agregar el prepago chileno en WhatsApp Manager → Números de
  teléfono → Agregar (código por SMS o llamada; el chip debe estar en un
  celular en ese momento y **sin WhatsApp instalado**). Definir PIN de
  verificación en dos pasos y guardarlo.
- Sin verificación de empresa: hasta 250 contactos por día en mensajes que
  inicia el bot; las respuestas no tienen límite.

## Código

- `finmate/whatsapp/meta_cloud.py`: envío (texto, plantillas, leído), firma y lectura del JSON.
- `finmate/whatsapp/messenger.py`: elige Meta o Twilio; el resto del código no cambió.
- `finmate/whatsapp/webhook.py`: GET de verificación + POST JSON de Meta; Twilio sigue igual.
- Plantillas: el código usa `TEMPLATE_*` (antes `TWILIO_TEMPLATE_*_SID`), que apunta al proveedor activo.
- Tests: `tests/test_meta_whatsapp.py`.
- Teléfonos en la base: mismo formato `whatsapp:+569...` que con Twilio (usuarios y memoria se mantienen).
