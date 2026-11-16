# Finmate — Estado actual y próximos pasos

> Foto al **29 oct 2026**, actualizada el **16 nov 2026** (tarde), consolidada desde `CLAUDE.md` (raíz del repo), que sigue siendo
> el resumen vivo. Si hay diferencias, manda `CLAUDE.md`.

## En una línea

En producción solo corre el bot de comandos informativos (Finnhub + Alpha Vantage). Todo lo
nuevo (agente con Claude, memoria, portafolio, watchlist, alertas por usuario, plantillas
WhatsApp) está **escrito y probado en sandbox, pero no desplegado**, porque **Railway está
offline por trial vencido**.

## Ojo: dos numeraciones de "fases"

El plan (doc `01_...`) tiene 9 fases (0 a 8). El código se fue construyendo con su propia
numeración, en otro orden. Equivalencias:

| Fase en el código (CLAUDE.md) | Fecha | Qué hace | Corresponde en el plan a |
|---|---|---|---|
| Fase 0 | 23-24 ago 2026 | Orquestador Claude + tool-calling + memoria en Postgres + cache Redis | Plan Fase 0 (+ historial de Plan Fase 1) |
| Fase 1 | 26 oct 2026 | Portafolio + watchlist por chat (6 tools, 7 en total) | Plan Fase 3 (portafolio) + parte de Plan Fase 2 (watchlist) |
| Fase 1.5 | 26 oct 2026 | Alertas proactivas 1-a-1 cuando un símbolo de la watchlist se mueve > umbral | Parte de Plan Fase 2 (+ dedup de Plan Fase 6) |
| Fase 1.6 | 26 oct 2026 | Content Templates de WhatsApp + cola de notificaciones pendientes | Decisión 07 / requisito de Plan Fase 2 |

**Actualización 8 nov 2026 — código escrito el 29 oct (después de armar estos docs) y probado hoy:**

| Plan | Qué se agregó | Archivos | Estado |
|---|---|---|---|
| Fase 1 | Personalidad configurable por chat (humor, sarcasmo, chistes, nivel conversador, tono) inyectada en el system prompt | `agent/personality_tools.py`, `db/personality_repo.py`, `agent/orchestrator.py` | ✅ probado local |
| Fase 2 | Tool `explain_movement` (precio + variación + noticias del activo) | `agent/market_tools.py` | ✅ probado con Finnhub real |
| Fase 4 | Seguir temas de noticias e indicadores; catálogo curado de ~15 indicadores EE.UU./Chile (sin fechas reales todavía) | `agent/news_tools.py`, `db/news_repo.py`, `data_sources/economic_calendar.py` | ✅ probado local |
| Fase 5 | Gastos/ingresos por chat, resumen mensual, últimos movimientos | `agent/finance_tools.py`, `db/finance_repo.py` | ✅ probado local |
| Fase 6 | Tabla `alerts_log` + repo | `db/alerts_log_repo.py` | ⚠️ creada, falta conectarla a los motores de alertas (siguen usando JSON) |

El agente tiene ahora **20 tools**. Prueba del 8 nov: todas corridas contra una SQLite temporal
(Finnhub real). Se corrigieron 3 bugs: (1) un gasto mandado con monto positivo quedaba como
ingreso → nuevo parámetro obligatorio `tipo` (gasto/ingreso) que manda sobre el signo;
(2) categorías sin tilde ("alimentacion") caían en "Otros" → normalización sin tildes;
(3) `explain_movement` mostraba noticias que no eran del activo → filtra por ticker/nombre de la empresa.

**Todavía sin empezar del plan:** Centro de Control web (Fases 1 y 7), scheduler de
apertura/cierre (Fase 2), P&L/rentabilidad del portafolio (Fase 3 — hoy solo muestra valor
actual), fechas reales del calendario económico y pre-aviso/post-dato (Fase 4), conectar
`alerts_log` y umbral de materialidad (Fase 6), hardening (Fase 8).

**✅ 8 nov 2026: todo el código y `docs/` subidos a GitHub `main`** (7 commits por el editor web;
verificado que el repo queda idéntico a esta carpeta y arranca con las 20 tools). La carpeta local
sigue sin ser un repo git funcional (`.git` incompleto): para próximos cambios, clonar de nuevo o
subir por el editor web de GitHub.

⚠️ **Railway → Variables muestra "Suggested Variables" tomadas de `.env.example`: son valores de
ejemplo (`xxxx`, `usuario:password`). No apretar "Add" en ese bloque** — pisaría las claves reales de
Twilio/Finnhub. Cargar a mano solo `DATABASE_URL`, `REDIS_URL` y `ANTHROPIC_API_KEY` con "New Variable".

Sugerencia: al retomar con Claude Code, definir si se sigue la numeración del plan o la del
código, y mantener una sola.

## Panel web (16 nov 2026)

Etapas 1, 2 y 3 del panel programadas y probadas (ver `06_PANEL_WEB_DISENO_Y_CONEXION.md` y
CLAUDE.md). Faltan la 4 (login por código), la 5 (boletas con foto) y la 6 (lanzamiento).
Al desplegar hay que sumar en Railway la variable `FLASK_SECRET_KEY`.

## Fuentes en tiempo real — Etapa A (16 nov 2026)

Lista en código y probada (41/41 tests), sin desplegar. FRED (macro EE.UU. +
calendario), Banco Central de Chile (dólar, UF, TPM, IPC) y Marketaux
(noticias con sentimiento) conectados; alertas de noticias por usuario cada
3 min y recordatorio diario de datos macro. Claves ya cargadas en Railway.
Próximas: Etapa B (WebSocket de precios Finnhub) y Etapa C (podcasts por
RSS + transcripción + resumen).

## 💳 Pagos pendientes (acción de Joaco) — revisado 16 nov 2026

| # | Qué pagar | Cuánto | ¿Bloquea? | Dónde |
|---|---|---|---|---|
| 1 | **Créditos de la API de Claude** — el saldo está en **USD 0.00**; sin créditos el agente no responde aunque Railway esté arriba | Mínimo USD 5 (vencen al año). Sugerido USD 10–20 para empezar | **Sí** | platform.claude.com → Facturación → "Comprar créditos" |
| 2 | **Railway plan Hobby** — el servicio `web` está en "Trial expired" | USD 5/mes, incluye USD 5 de uso; si el consumo pasa de 5, se paga la diferencia | **Sí** | railway.com → Settings → Billing |
| 3 | **Twilio: salir del trial (upgrade)** — necesario para registrar un número propio de WhatsApp Business ("WhatsApp Sender") y mandar las plantillas a Meta. También pide una cuenta de Meta Business Portfolio | Registrar el sender no cuesta; se paga USD 0.005 por mensaje (enviado o recibido) + la tarifa de Meta por plantilla Utility (varía por país) + el costo mensual del número | No para probar en el sandbox; **sí** para alertas proactivas reales | console.twilio.com → "Upgrade Now" (saldo trial actual: USD 10.73) |
| — | Neon (Postgres), Upstash (Redis), GitHub | USD 0 (planes free) | No | Revisar de vez en cuando que no se pase del free tier |

Orden sugerido: 1 y 2 juntos (son los que desbloquean el deploy), 3 cuando el bot ya funcione en el sandbox.
Registrar cada pago en `Claude outputs/Finmate_Costos.xlsx` (hojas Suscripciones y Pagos).

## Bloqueador y pasos para desplegar (acción de Joaco)

1. ✅ Postgres provisionado (Neon `finmate`, base `neondb`) → copiar connection string. **16 nov: las 10 tablas ya están creadas y probadas** (escritura/lectura OK).
2. ✅ Redis provisionado (Upstash `finmate`) → copiar URL `rediss://`.
3. ✅ API key `finmate-railway` creada en platform.claude.com → copiarla.
4. ❌ **Railway: agregar método de pago** (servicio `web` en "Trial expired"). ← bloqueador activo
5. Cargar en Railway → Variables: `DATABASE_URL`, `REDIS_URL`, `ANTHROPIC_API_KEY`.
6. Railway redeploya solo (el código ya está en GitHub `main`).
7. Probar por WhatsApp: "hola", una pregunta de mercados, "agregá 10 AAPL a 150", "seguí a NVDA".
8. ✅ 16 nov: las 3 plantillas **ya están creadas** en Twilio (estado "Not Submitted"; para mandarlas a Meta falta el pago 3). ~~Crear las 3 plantillas en Twilio (textos en `05_WHATSAPP_TEMPLATES_TWILIO.md`),
   esperar aprobación de Meta y pegar los Content SIDs en Railway.~~ **No cargar los SIDs en Railway hasta que Meta las apruebe** (si se cargan antes, el bot intenta mandar plantillas no aprobadas en vez de texto libre).

## Deuda técnica menor

- `twilio` subido de `9.4.0` (yanked) a `9.4.1`.
- `pyflakes`: imports sin usar y f-strings sin placeholders en `webhook.py`, `formatter.py`,
  `engine.py`, `gcal_client.py`, `main.py` — cosmético.
- `_github_upload/` en la raíz parece ser una copia temporal de archivos para subir a GitHub
  (versiones viejas de Fase 0) — revisar si se puede borrar.
- `lu14268l81.tmp` y `.~lock.Finmate_Guia_Completa.pdf#` son temporales de LibreOffice/Office.
