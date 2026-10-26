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

## Estado actual (última revisión: 26 oct 2026)

- **En producción (funciona):** bot de comandos informativos sobre mercados
  vía Finnhub + Alpha Vantage (FMP quedó descartado, su free tier expiró).
- **Escrito pero NO desplegado — "Fase 0" (agente con memoria), del 23-24 ago
  2026:** el router de comandos fijos de `finmate/whatsapp/webhook.py` se
  reemplazó por un orquestador (`finmate/agent/orchestrator.py`) que usa
  Claude con tool-calling (`finmate/agent/tools.py`) y persiste memoria de
  conversación en Postgres (`finmate/db/`). Cache opcional sobre Redis en
  `finmate/db/cache.py`. Revalidé el 25 oct 2026 en sandbox (import sin
  credenciales, capa de DB contra SQLite, loop de tool-calling con cliente
  de Anthropic mockeado, webhook end-to-end): todo sigue funcionando igual
  que lo dejó la sesión de agosto.
- **Escrito pero NO desplegado — "Fase 1" (portafolio + watchlist), del 26
  oct 2026:** se agregaron tools de portafolio y watchlist para que el
  agente las maneje por chat (comprar/vender posiciones, seguir activos sin
  tenerlos). Cambios:
  - `finmate/db/models.py`: nuevos modelos `PortfolioHolding` y
    `WatchlistItem` (posición neta actual por símbolo, no libro de
    transacciones).
  - `finmate/db/repository.py`: funciones CRUD (`add_or_update_holding`,
    `remove_holding`, `get_portfolio`, `add_to_watchlist`,
    `remove_from_watchlist`, `get_watchlist`).
  - `finmate/agent/portfolio_tools.py` (nuevo archivo): las 6 tools
    WhatsApp-formateadas que llama el orquestador, reutilizando la cotización
    de Finnhub ya probada en `webhook.py`.
  - `finmate/agent/tools.py`: ahora registra 7 tools en total; `run_tool`
    recibe `user_id` para las tools por-usuario.
  - `finmate/agent/orchestrator.py`: el loop de tool-calling (`_run_agent`)
    propaga `user_id` a `run_tool`.
  - Deliberadamente **no** se conectó el motor de alertas
    (`finmate/alerts/engine.py`) a la watchlist por-usuario en esta pasada,
    para no arriesgar el sistema de alertas broadcast que ya funciona en
    producción — queda para una fase posterior.
  - Validado end-to-end en sandbox (DB contra SQLite, cotizaciones y cliente
    de Anthropic mockeados): todos los checks pasaron, sin romper nada de
    Fase 0.
- **Bloqueador real:** nada de la Fase 0 ni la Fase 1 llegó a Railway.
  Faltan, en orden:
  1. Provisionar Postgres (recomendado: Neon, neon.tech) → `DATABASE_URL`.
  2. (Opcional) Provisionar Redis (recomendado: Upstash, upstash.com) →
     `REDIS_URL`.
  3. Crear API key en console.anthropic.com → `ANTHROPIC_API_KEY`.
  4. Resolver el estado de pago de Railway (el servicio mostró "Trial
     Ended" — Joaco tiene que configurar el método de pago él mismo, no es
     algo que yo pueda hacer).
  5. Pegar `DATABASE_URL`, `REDIS_URL` y `ANTHROPIC_API_KEY` en las
     Variables de Railway (Joaco tiene que hacerlo él mismo — nunca debo
     ingresar credenciales yo).
  6. Railway va a redeployar solo en cuanto el repo tenga los archivos (ya
     están subidos a GitHub `main`, tanto Fase 0 como Fase 1) y el servicio
     esté activo con las variables cargadas.
  7. Probar "hola", una pregunta de mercados y "agregá 10 AAPL a 150" por
     WhatsApp en producción.
  8. En paralelo: trámite de plantillas de WhatsApp Business (Twilio + Meta)
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
├── main.py                 # App principal + scheduler (APScheduler)
├── wsgi.py                 # Entry point para Gunicorn (Procfile)
├── config/settings.py      # Variables de entorno
├── finmate/
│   ├── agent/               # Fase 0 + Fase 1: orquestador + tools del agente (Claude)
│   │   ├── orchestrator.py  # Loop de tool-calling, propaga user_id
│   │   ├── tools.py         # Registro de las 7 tools (mercados + portafolio + watchlist)
│   │   └── portfolio_tools.py  # Fase 1: tools de portafolio y watchlist
│   ├── data_sources/        # Finnhub, FMP (no se usa), Alpha Vantage, aggregator
│   ├── whatsapp/             # webhook (Twilio), messenger, formatter
│   ├── calendar/              # Google Calendar (opcional, no configurado)
│   ├── alerts/                # Motor de alertas (earnings, macro, noticias) — aún no
│   │                           # conectado a la watchlist por-usuario de Fase 1
│   └── db/                    # Fase 0 + Fase 1: modelos SQLAlchemy, repository, cache Redis
```

## Variables de entorno (ya en Railway)

`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`,
`WHATSAPP_RECIPIENTS`, `FINNHUB_API_KEY`, `FMP_API_KEY`,
`ALPHA_VANTAGE_API_KEY`, `TIMEZONE`, `PORT`, `LOG_LEVEL`,
`WEEKLY_SUMMARY_DAY/HOUR/MINUTE`, `ALERT_CHECK_INTERVAL_MINUTES`.

Faltan en Railway (ver bloqueador arriba): `DATABASE_URL`, `REDIS_URL`,
`ANTHROPIC_API_KEY`. Ver `.env.example` para el detalle de cada una. Fase 1
no agrega variables de entorno nuevas.

## Cómo editar archivos de este proyecto desde un sandbox en la nube

No se puede hacer `git push` directo (sin credenciales de GitHub ahí).
Opciones: (1) editor web de GitHub
(`https://github.com/claudeheymate-code/finmate/edit/main/RUTA`), Railway
redeploya solo; (2) si la sesión tiene la carpeta local conectada, los
archivos quedan escritos en disco y Joaco los commitea/pushea él mismo.
