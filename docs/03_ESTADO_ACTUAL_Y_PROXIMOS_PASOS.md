# Finmate — Estado actual y próximos pasos

> Foto al **29 oct 2026**, actualizada el **8 nov 2026**, consolidada desde `CLAUDE.md` (raíz del repo), que sigue siendo
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

## Bloqueador y pasos para desplegar (acción de Joaco)

1. ✅ Postgres provisionado (Neon `finmate`) → copiar connection string.
2. ✅ Redis provisionado (Upstash `finmate`) → copiar URL `rediss://`.
3. ✅ API key `finmate-railway` creada en platform.claude.com → copiarla.
4. ❌ **Railway: agregar método de pago** (servicio `web` en "Trial expired"). ← bloqueador activo
5. Cargar en Railway → Variables: `DATABASE_URL`, `REDIS_URL`, `ANTHROPIC_API_KEY`.
6. Railway redeploya solo (el código ya está en GitHub `main`).
7. Probar por WhatsApp: "hola", una pregunta de mercados, "agregá 10 AAPL a 150", "seguí a NVDA".
8. En paralelo: crear las 3 plantillas en Twilio (textos en `05_WHATSAPP_TEMPLATES_TWILIO.md`),
   esperar aprobación de Meta y pegar los Content SIDs en Railway.

## Deuda técnica menor

- `twilio` subido de `9.4.0` (yanked) a `9.4.1`.
- `pyflakes`: imports sin usar y f-strings sin placeholders en `webhook.py`, `formatter.py`,
  `engine.py`, `gcal_client.py`, `main.py` — cosmético.
- `_github_upload/` en la raíz parece ser una copia temporal de archivos para subir a GitHub
  (versiones viejas de Fase 0) — revisar si se puede borrar.
- `lu14268l81.tmp` y `.~lock.Finmate_Guia_Completa.pdf#` son temporales de LibreOffice/Office.
