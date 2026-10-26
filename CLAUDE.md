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
- **Escrito pero NO desplegado — "Fase 1.5" (alertas de watchlist por
  usuario), del 26 oct 2026:** conecta la watchlist de Fase 1 con un aviso
  proactivo de WhatsApp (no esperar a que el usuario pregunte). Cambios:
  - `finmate/db/repository.py`: `get_all_watchlist_entries()` — todas las
    filas de watchlist de todos los usuarios, con el teléfono ya resuelto
    (join con `users`).
  - `finmate/alerts/watchlist_alerts.py` (nuevo archivo):
    `check_watchlist_alerts()` recorre esas filas, cotiza cada símbolo una
    sola vez (cache por símbolo dentro de la corrida, aunque varios
    usuarios lo sigan) y manda un WhatsApp 1-a-1 (no broadcast) al que
    corresponda si el movimiento del día supera
    `WATCHLIST_ALERT_THRESHOLD_PCT` (default 5%). Máximo una alerta por
    usuario+símbolo+día (estado propio en `watchlist_alert_state.json`,
    separado del `alert_state.json` del motor broadcast). Si el mercado
    está cerrado para un símbolo, se lo salta.
  - `main.py`: nuevo job `watchlist_alert_check` en el scheduler, mismo
    intervalo que `alert_check` pero **separado a propósito** — con su
    propio try/except y el import adentro de la función — para que un
    error acá (o que falte `DATABASE_URL`) nunca pueda tocar el chequeo de
    alertas broadcast (earnings/macro/noticias) que ya funciona en
    producción. Esto es justamente lo que la Fase 1 había dejado pendiente
    a propósito (ver nota en el historial de este archivo).
  - `config/settings.py`: nueva variable opcional
    `WATCHLIST_ALERT_THRESHOLD_PCT` (default `5`, no hace falta cargarla en
    Railway para que funcione).
  - Validado end-to-end en sandbox (DB SQLite, 2 usuarios con watchlists
    superpuestas, cotizaciones y Twilio mockeados): dispara alerta solo al
    superar el umbral, no duplica cuando dos usuarios siguen el mismo
    símbolo (cachea la cotización), ignora mercado cerrado, y no reenvía
    la misma alerta el mismo día (dedup).
- **Escrito pero NO desplegado — "Fase 1.6" (Content Templates de WhatsApp
  Business + cola de notificaciones pendientes), del 26 oct 2026:** mientras
  el bot corre en el sandbox de Twilio, mandar texto libre por iniciativa
  propia (resumen semanal, alertas) funciona sin problema. Pero en un número
  real de WhatsApp Business, Meta exige que cualquier mensaje que el bot
  inicie fuera de la ventana de 24hs de mensajería libre use un Content
  Template aprobado — texto mayormente fijo, pocas variables cortas. Esto
  no estaba resuelto en ninguna fase anterior y habría roto earnings/macro/
  noticias/resumen semanal/alertas de watchlist apenas Joaco consiguiera un
  número real. Cambios:
  - `finmate/alerts/pending.py` (nuevo archivo): cola de contenido pendiente
    por teléfono (`queue_pending`/`pop_pending`), separada de los state
    files de dedup existentes — esto no es dedup, es contenido todavía no
    entregado.
  - `config/settings.py`: 3 variables opcionales nuevas (Content SIDs de
    Twilio): `TWILIO_TEMPLATE_WATCHLIST_ALERT_SID`,
    `TWILIO_TEMPLATE_MARKET_NOTIFY_SID`,
    `TWILIO_TEMPLATE_WEEKLY_SUMMARY_NOTIFY_SID`. Mientras no estén
    configuradas, nada cambia (se sigue mandando texto libre, como hoy).
  - `finmate/whatsapp/messenger.py`: nuevos métodos `send_template()` /
    `broadcast_template()` (usan `content_sid` + `content_variables` del
    SDK de Twilio en vez de `body` libre).
  - `finmate/alerts/watchlist_alerts.py`: si hay
    `TWILIO_TEMPLATE_WATCHLIST_ALERT_SID` configurado, manda la alerta como
    template (symbol, variación % y precio como variables — es corta y
    estructurada, entra en un template). Si no, cae al texto libre de
    siempre.
  - `finmate/alerts/engine.py`: nuevo método `_broadcast_or_queue()` — si
    hay template de aviso de mercado/resumen semanal configurado, encola el
    contenido real (`queue_pending`) y manda un template corto de aviso; si
    no, broadcast de texto libre como hasta ahora. Reemplaza los 4 llamados
    a `broadcast()` (earnings, macro, noticias, resumen semanal).
  - `finmate/agent/tools.py`: nueva tool `get_pending_notifications` — el
    agente la llama cuando el usuario responde afirmativo a un aviso corto
    ("dale", "mostrame"), y entrega el contenido real encolado. Como la
    cola vive por teléfono (no por `user_id` de la DB), se agregó el
    concepto de tools "phone-scoped" (`_PHONE_SCOPED_TOOLS`) separado de
    las "user-scoped" de Fase 1.
  - `finmate/agent/orchestrator.py`: `_run_agent` y `handle_message` ahora
    también propagan `phone` (no solo `user_id`) a `run_tool`.
  - Validado end-to-end en sandbox (DB SQLite, Twilio y cliente de
    Anthropic mockeados) en dos modos — `TWILIO_TEMPLATE_*` sin configurar
    (confirma que el comportamiento actual no cambia) y configurado
    (confirma que se manda el template corto, se encola el contenido, y que
    `get_pending_notifications` lo entrega correctamente) — más un test
    separado de extremo a extremo del orquestador confirmando que `phone`
    llega intacto desde `handle_message` hasta la tool.
  - Pendiente (trabajo de Joaco, no de código): crear los 3 templates en
    Twilio Content Template Builder y someterlos a aprobación de Meta, y
    pegar los 3 Content SIDs (`HXxxxxx...`) resultantes en las variables de
    Railway. Mientras no estén, el bot sigue funcionando exactamente igual
    que ahora.
- **Bloqueador real:** nada de la Fase 0, Fase 1, Fase 1.5 ni Fase 1.6 llegó
  a Railway. Faltan, en orden:
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
  7. Probar "hola", una pregunta de mercados, "agregá 10 AAPL a 150" y
     "seguí a NVDA" por WhatsApp en producción (y confirmar que, si NVDA se
     mueve fuerte, llega la alerta de watchlist sin que nadie pregunte).
  8. En paralelo: trámite de plantillas de WhatsApp Business (Twilio + Meta)
     — la aprobación de Meta tarda días, conviene arrancarlo cuanto antes.
     El código que las usa (Fase 1.6) ya está listo; falta crear los 3
     templates en Twilio y pegar sus Content SIDs en Railway (ver Fase 1.6
     arriba para el detalle de cuáles).
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
│   ├── alerts/                # engine.py: motor broadcast (earnings, macro, noticias,
│   │                           # resumen semanal). watchlist_alerts.py (Fase 1.5): alertas
│   │                           # 1-a-1 por usuario sobre su watchlist — job separado en main.py
│   │                           # pending.py (Fase 1.6): cola de contenido pendiente por
│   │                           # teléfono, para cuando el aviso se manda como Content Template
│   └── db/                    # Fase 0 + Fase 1: modelos SQLAlchemy, repository, cache Redis
```

## Variables de entorno (ya en Railway)

`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`,
`WHATSAPP_RECIPIENTS`, `FINNHUB_API_KEY`, `FMP_API_KEY`,
`ALPHA_VANTAGE_API_KEY`, `TIMEZONE`, `PORT`, `LOG_LEVEL`,
`WEEKLY_SUMMARY_DAY/HOUR/MINUTE`, `ALERT_CHECK_INTERVAL_MINUTES`.

Faltan en Railway (ver bloqueador arriba): `DATABASE_URL`, `REDIS_URL`,
`ANTHROPIC_API_KEY`. Ver `.env.example` para el detalle de cada una. Fase 1
no agrega variables de entorno nuevas. Fase 1.5 agrega una opcional:
`WATCHLIST_ALERT_THRESHOLD_PCT` (default `5`, no hace falta cargarla). Fase
1.6 agrega 3 opcionales más (Content SIDs de Twilio, ver Fase 1.6 arriba):
`TWILIO_TEMPLATE_WATCHLIST_ALERT_SID`, `TWILIO_TEMPLATE_MARKET_NOTIFY_SID`,
`TWILIO_TEMPLATE_WEEKLY_SUMMARY_NOTIFY_SID` — tampoco hace falta cargarlas
para que el bot siga funcionando como hoy.

## Cómo editar archivos de este proyecto desde un sandbox en la nube

No se puede hacer `git push` directo (sin credenciales de GitHub ahí).
Opciones: (1) editor web de GitHub
(`https://github.com/claudeheymate-code/finmate/edit/main/RUTA`), Railway
redeploya solo; (2) si la sesión tiene la carpeta local conectada, los
archivos quedan escritos en disco y Joaco los commitea/pushea él mismo.
