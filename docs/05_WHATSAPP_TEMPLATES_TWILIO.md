# Finmate — Content Templates para Twilio (Fase 1.6 del código)

> Fuente: doc `claude/whatsapp-templates.md` del proyecto "Finmate" en claude.ai (27 oct 2026).

Listos para pegar en Twilio Content Template Builder
(console.twilio.com → Messaging → Content Template Builder → Create new).
Los 3 corresponden exactamente a las 3 variables de entorno que ya están en
`config/settings.py` — una vez aprobados por Meta, el Content SID de cada
uno (empieza con `HX...`) va en la variable correspondiente en Railway.

Para cada uno: Channel = **WhatsApp**, Category = **Utility** (son avisos de
servicio sobre algo que el usuario ya eligió seguir — portafolio/watchlist —
no marketing; aprueba más rápido y sale más barato por mensaje que
Marketing). Language = **Spanish (es)** o **Spanish - Latin America (es_419)**
si Twilio lo ofrece como opción separada.

---

## 1. `finmate_watchlist_alert`

Variable env: `TWILIO_TEMPLATE_WATCHLIST_ALERT_SID`
Usado por: `finmate/alerts/watchlist_alerts.py` (alerta 1-a-1 cuando un
símbolo de la watchlist del usuario se mueve más del umbral configurado).

**Body:**
```
📊 Tu activo *{{1}}* se movió {{2}} hoy. Precio actual: {{3}}. Respondé para ver más o dejar de seguirlo.
```

**Variables de ejemplo (para el submission a Meta):**
- `{{1}}` → `AAPL`
- `{{2}}` → `+6.52%`
- `{{3}}` → `$182.40`

El código manda estas 3 variables en ese orden exacto
(`{"1": symbol, "2": change_fmt, "3": price_fmt}`).

---

## 2. `finmate_market_notify`

Variable env: `TWILIO_TEMPLATE_MARKET_NOTIFY_SID`
Usado por: `finmate/alerts/engine.py` (`_broadcast_or_queue`) — aviso corto
cuando hay una alerta de earnings, dato macro o noticia de mercado. El
contenido completo se manda después, como texto libre, cuando el usuario
responde (vía la tool `get_pending_notifications`).

**Body:**
```
🔔 Tenés una novedad de mercado: {{1}}. Respondé para ver el detalle completo.
```

**Variable de ejemplo:**
- `{{1}}` → `Resultados corporativos`

El código manda uno de estos 3 valores como `{{1}}`: `Resultados corporativos`,
`Dato macroeconómico` o `Noticia de mercado`.

---

## 3. `finmate_weekly_summary_notify`

Variable env: `TWILIO_TEMPLATE_WEEKLY_SUMMARY_NOTIFY_SID`
Usado por: `finmate/alerts/engine.py` (`send_weekly_summary`) — aviso corto
semanal. El resumen completo se manda después, como texto libre, cuando el
usuario responde.

**Body (sin variables):**
```
📈 Tu resumen semanal de mercados con Finmate ya está listo. Respondé "sí" o "mostrame" para verlo.
```

---

## Después de que Meta apruebe

1. Copiar el Content SID de cada template aprobado (Twilio Console →
   Content Template Builder → el template → `HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`).
2. Pegarlos en Railway → Variables del servicio:
   - `TWILIO_TEMPLATE_WATCHLIST_ALERT_SID`
   - `TWILIO_TEMPLATE_MARKET_NOTIFY_SID`
   - `TWILIO_TEMPLATE_WEEKLY_SUMMARY_NOTIFY_SID`
3. No hace falta redeploy manual — Railway las toma en el próximo restart.
   Mientras no estén las 3 cargadas, el bot sigue mandando texto libre para
   las que falten (es por variable, no todo o nada).

Meta normalmente tarda entre unas horas y unos días en aprobar un template
Utility bien formado. Si alguno es rechazado, el motivo más común es texto
ambiguo o que suene a marketing — estos 3 están redactados como avisos de
servicio neutros a propósito.
