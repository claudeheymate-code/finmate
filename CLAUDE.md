# Finmate — Contexto del proyecto para Claude

Bot/agente financiero de WhatsApp. Repo GitHub: `claudeheymate-code/finmate`
(branch `main`). Deploy: Railway, proyecto `melodious-surprise / production`
(https://railway.com/project/9d151bd6-2970-4d33-9b0e-3cd2e961ff78), auto-deploy
desde GitHub. Usuario del proyecto: Joaco (joacocornejocalaf@gmail.com,
WhatsApp +56954161465).

Historial detallado de decisiones y pruebas: ver `RESUMEN_CONVERSACION.md` en
esta misma carpeta. Este archivo es el resumen vivo y corto — actualizalo al
final de cada sesión en vez de dejar que `RESUMEN_CONVERSACION.md` crezca sin
curar.

## Estado actual (última revisión: 25 oct 2026)

- **En producción (funciona):** bot de comandos informativos sobre mercados
  vía Finnhub + Alpha Vantage (FMP quedó descartado, su free tier expiró).
- **Escrito pero NO desplegado — "Fase 0" (agente con memoria), del 23-24 ago
  2026:** el router de comandos fijos de `finmate/whatsapp/webhook.py` se
  reemplazó por un orquestador (`finmate/agent/orchestrator.py`) que usa
  Claude con tool-calling (`finmate/agent/tools.py`, una sola tool por ahora:
  `get_market_data`) y persiste memoria de conversación en Postgres
  (`finmate/db/`). Cache opcional sobre Redis en `finmate/db/cache.py`.
  Revalidé el 25 oct 2026 en sandbox (import sin credenciales, capa de DB
  contra SQLite, loop de tool-calling con cliente de Anthropic mockeado,
  webhook end-to-end): todo sigue funcionando igual que lo dejó la sesión de
  agosto. **No se tocó nada de esto desde entonces.**
- **Bloqueador real:** nada de la Fase 0 llegó a Railway. Faltan, en orden:
  1. Provisionar Postgres (recomendado: Neon, neon.tech) → `DATABASE_URL`.
  2. (Opcional) Provisionar Redis (recomendado: Upstash, upstash.com) →
     `REDIS_URL`.
  3. Crear API key en console.anthropic.com → `ANTHROPIC_API_KEY`.
  4. Subir los archivos de la Fase 0 al repo de GitHub y dejar que Railway
     redeploye. El sandbox de Claude Code en la nube **no puede hacer
     `git push`** (sin token de GitHub válido ahí) ni montar la carpeta local
     por shell todavía — la vía que funciona es el editor web de GitHub, o
     que Joaco haga el commit/push él mismo desde su máquina con los
     archivos ya escritos en disco.
  5. Probar "hola" y una pregunta de mercados por WhatsApp en producción.
  6. En paralelo: trámite de plantillas de WhatsApp Business (Twilio + Meta)
     — la aprobación de Meta tarda días, conviene arrancarlo cuanto antes.
- **Deuda técnica menor:** `twilio` estaba pineado en `9.4.0`, que PyPI
  marca como "yanked" — se subió a `9.4.1` (25 oct 2026, sin romper nada,
  verificado). `pyflakes` señala imports sin usar y f-strings sin
  placeholders en `webhook.py`, `formatter.py`, `engine.py`,
  `gcal_client.py`, `main.py` — cosmético, no afecta funcionamiento, no se
  tocó para no mezclar cambios.

## Arquitectura

```
Finmate/
├── main.py              # App principal + scheduler (APScheduler)
├── wsgi.py              # Entry point para Gunicorn (Procfile)
├── config/settings.py   # Variables de entorno
├── finmate/
│   ├── agent/           # Fase 0: orquestador + tools del agente (Claude)
│   ├── data_sources/    # Finnhub, FMP (no se usa), Alpha Vantage, aggregator
│   ├── whatsapp/        # webhook (Twilio), messenger, formatter
│   ├── calendar/        # Google Calendar (opcional, no configurado)
│   ├── alerts/          # Motor de alertas (earnings, macro, noticias)
│   └── db/              # Fase 0: modelos SQLAlchemy, repository, cache Redis
```

## Variables de entorno (ya en Railway)

`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`,
`WHATSAPP_RECIPIENTS`, `FINNHUB_API_KEY`, `FMP_API_KEY`,
`ALPHA_VANTAGE_API_KEY`, `TIMEZONE`, `PORT`, `LOG_LEVEL`,
`WEEKLY_SUMMARY_DAY/HOUR/MINUTE`, `ALERT_CHECK_INTERVAL_MINUTES`.

Faltan en Railway (ver bloqueador arriba): `DATABASE_URL`, `REDIS_URL`,
`ANTHROPIC_API_KEY`. Ver `.env.example` para el detalle de cada una.

## Cómo editar archivos de este proyecto desde un sandbox en la nube

No se puede hacer `git push` directo (sin credenciales de GitHub ahí).
Opciones: (1) editor web de GitHub
(`https://github.com/claudeheymate-code/finmate/edit/main/RUTA`), Railway
redeploya solo; (2) si la sesión tiene la carpeta local conectada, los
archivos quedan escritos en disco y Joaco los commitea/pushea él mismo.
