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

**Documentación completa en `docs/`** (empezar por `docs/00_LEEME_INDICE.md`):
plan de arquitectura con las 9 fases (`docs/01_PLAN_ARQUITECTURA_Y_FASES.md`),
checklist por fase con verificaciones (`docs/02_CHECKLIST_CONSTRUCCION_POR_FASE.md`),
estado actual + equivalencia entre la numeración de fases del plan y la del
código (`docs/03_ESTADO_ACTUAL_Y_PROXIMOS_PASOS.md`), ideas
(`docs/04_BRAINSTORMING_IDEAS.md`) y plantillas de WhatsApp
(`docs/05_WHATSAPP_TEMPLATES_TWILIO.md`). Al cerrar una sesión, actualizar
también el checklist y el doc de estado.

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
  a Railway. Chequeado el 27 oct 2026 directamente en las consolas (Neon,
  Upstash, Railway, Twilio, Claude Platform) — estado real de cada paso:
  1. ✅ Postgres ya está provisionado: proyecto Neon `finmate`
     (`shiny-term-24632740`), branch `production`, free plan. Solo falta
     que Joaco copie el connection string (botón "Connect" → "Show
     password") y lo pegue como `DATABASE_URL` en Railway.
  2. ✅ Redis ya está provisionado: base Upstash `finmate`, free tier. Solo
     falta que Joaco copie el `UPSTASH_REDIS_REST_URL`/token (o el
     `redis://` de la pestaña TCP) y lo pegue como `REDIS_URL` en Railway.
  3. ✅ `ANTHROPIC_API_KEY`: ya existe una key creada en
     platform.claude.com llamada `finmate-railway` (alcance Organización,
     creada 28 ago 2026). Solo falta que Joaco la copie (botón de revelar
     en la tabla de claves) y la pegue como `ANTHROPIC_API_KEY` en Railway
     — el valor en sí nunca lo vi ni lo puedo ver yo.
  4. ❌ **Este es el bloqueador activo de verdad:** el servicio `web` en
     Railway (proyecto `melodious-surprise`) muestra "Trial expired" /
     "Service is offline". Joaco tiene que agregar un método de pago en
     Railway — no es algo que yo pueda hacer (nunca debo ingresar datos de
     pago ni credenciales).
  5. Una vez resuelto el pago: pegar `DATABASE_URL`, `REDIS_URL` y
     `ANTHROPIC_API_KEY` en las Variables de Railway (Joaco tiene que
     hacerlo él mismo — nunca debo ingresar credenciales yo).
  6. Railway va a redeployar solo en cuanto el repo tenga los archivos (ya
     están subidos a GitHub `main`, tanto Fase 0 como Fase 1) y el servicio
     esté activo con las variables cargadas.
  7. Probar "hola", una pregunta de mercados, "agregá 10 AAPL a 150" y
     "seguí a NVDA" por WhatsApp en producción (y confirmar que, si NVDA se
     mueve fuerte, llega la alerta de watchlist sin que nadie pregunte).
  8. En paralelo: trámite de plantillas de WhatsApp Business (Twilio + Meta)
     — la aprobación de Meta tarda días, conviene arrancarlo cuanto antes.
     El código que las usa (Fase 1.6) ya está listo; los 3 textos de
     template quedaron redactados y listos para pegar en Twilio Content
     Template Builder en el doc `claude/whatsapp-templates.md` del
     proyecto de Claude — falta que Joaco los cree ahí y pegue los Content
     SIDs resultantes en Railway (ver Fase 1.6 arriba para el detalle de
     cuáles). Intenté entrar a Twilio Content Template Builder para
     crearlos directamente, pero la sesión del navegador ya había
     expirado (pide login) — no voy a iniciar sesión yo (eso implicaría
     tocar credenciales), así que Joaco tiene que loguearse y crearlos a
     mano con los textos ya redactados. Twilio sigue en cuenta trial con
     saldo (~$10.73 al 26 oct 2026) — alcanza para seguir probando en el
     sandbox mientras tanto.
- **Escrito pero NO desplegado — "Etapa A de fuentes" (noticias y macro
  en tiempo real), del 16 nov 2026 tarde:**
  - Fuentes nuevas en `finmate/data_sources/`: `fred.py` (macro EE.UU. +
    calendario oficial de publicaciones, reemplaza a Alpha Vantage para
    macro), `bcch.py` (Banco Central de Chile: dólar observado, UF, TPM,
    IPC) y `marketaux.py` (noticias por empresa con sentimiento, en lote y
    con intervalo mínimo por el límite de 100 req/día).
  - `finmate/alerts/news_alerts.py`: cada `NEWS_CHECK_INTERVAL_MINUTES`
    (default 3) busca noticias de los símbolos del portafolio + watchlist de
    cada usuario (Finnhub REST siempre, Marketaux cuando toca), deduplica
    por titular entre fuentes, solo noticias de los últimos 90 min, máximo
    6 avisos por usuario por día y 3 titulares por aviso. La primera corrida
    tras un deploy solo "calienta" (no envía). Usa el template de aviso de
    mercado + cola de pendientes si está configurado.
  - `finmate/alerts/macro_alerts.py`: job diario 8:00 que avisa de
    publicaciones de hoy/mañana (IPC, NFP, PIB, PCE, FOMC) a quienes siguen
    ese indicador.
  - `finmate/agent/macro_tools.py`: 3 tools nuevas (`get_us_macro`,
    `get_chile_indicators`, `get_us_release_calendar`), con cache Redis.
  - `main.py`: jobs `news_alert_check` y `macro_reminders`, separados y con
    su propio try/except.
  - Variables cargadas por Joaco en Railway el 16 nov: `FRED_API_KEY`,
    `BCCH_API_TOKEN`, `MARKETAUX_API_KEY`. Todas opcionales: sin clave, esa
    fuente se salta.
  - Tests: `tests/test_etapaA_fuentes.py` (12, HTTP simulado). 41/41 pasan.
  - Sin probar contra las APIs reales (las claves viven solo en Railway).
    Verificar en el primer deploy: códigos de serie de UF
    (`F073.UFF.PRE.Z.D`) e IPC (`F074.IPC.VAR.Z.Z.C.M`) del Banco Central.
  - Siguiente: Etapa B (precios en tiempo real con WebSocket de Finnhub) y
    Etapa C (resumen diario de podcasts por RSS + transcripción).
- **Escrito pero NO desplegado — "Etapa B" (precios en tiempo real) y
  "Etapa C" (resumen diario de podcasts), del 16 nov 2026 tarde:**
  - Etapa B: `finmate/realtime/price_stream.py` mantiene abierto el
    WebSocket gratis de Finnhub (hilo arrancado en `wsgi.py`), suscrito a
    los símbolos de todas las watchlists (máx. 50), y cada 20 s evalúa las
    alertas de watchlist con el precio en vivo vs. el cierre anterior.
    `check_watchlist_alerts` ahora acepta `quote_fn` y tiene un lock, así el
    flujo en vivo y el chequeo de 30 min (que queda de respaldo) comparten
    el estado y nunca duplican un aviso. Reconexión automática 5→60 s.
    `services/quotes.get_quote` usa el precio en vivo si existe. Nueva
    dependencia `websocket-client==1.8.0`. Solo acciones de EE.UU.
  - Etapa C: `finmate/podcasts/` (catálogo + `digest.py`). Lee el RSS de
    Primer Click (DF) `https://anchor.fm/s/713eaf3c/podcast/rss`, detecta el
    episodio nuevo (salta "Especial (video)"), lo transcribe si hay
    `OPENAI_API_KEY` (si no, usa la descripción), lo resume con Claude Haiku
    en 5-6 viñetas y lo manda con link a quienes siguen el podcast + a
    `WHATSAPP_RECIPIENTS`. Job lun-vie cada 15 min entre 6:30 y 11:45.
    Tools nuevas: `follow_podcast`, `unfollow_podcast`,
    `get_podcast_summary` (guardado como news topic tipo "podcast").
  - Tests: `tests/test_etapaBC.py` (13). 53/53 pasan. Lectura del feed real
    de Primer Click verificada. WebSocket real de Finnhub sin probar (la
    clave vive solo en Railway).
  - OpenAI retira `gpt-4o-*-transcribe` el 26 feb 2027: antes de esa fecha
    cambiar `TRANSCRIBE_MODEL`.
- **16 nov 2026, tarde — preparación antes de pagar:**
  - Modelos de Claude por defecto actualizados a `claude-haiku-5-5` /
    `claude-sonnet-5-5` (Haiku 5.5 cuesta desde USD 0,10/0,50 por millón de
    tokens vs USD 1/5 de Haiku 4.5). OJO: en Railway existen
    `ANTHROPIC_MODEL_DEFAULT` y `ANTHROPIC_MODEL_ANALYSIS` y pisan el
    default del código — Joaco tiene que cambiarlas o borrarlas.
  - `scripts/probar_fuentes.py`: prueba cada fuente con las claves reales
    del `.env` local (sin imprimirlas). Correr con `py scripts\probar_fuentes.py`.
  - Railway tiene las 26 variables (incluye REDIS_URL, FLASK_SECRET_KEY,
    OPENAI_API_KEY; PANEL_DEV_LOGIN=false según Joaco). Falta: pagar el plan
    y presionar Deploy ("Apply N changes"). OpenAI con saldo USD 0.
- **16 nov 2026, noche — panel en celular + feedback + página web pública:**
  - Página web pública (GitHub Pages, carpeta `docs/`):
    https://claudeheymate-code.github.io/finmate/ → versión de prueba del
    panel (`docs/demo_panel/`, datos de ejemplo, "servidor" simulado en
    `demo-api.js`; generador en `docs/demo_panel/_generador/`).
  - Celular: menú de pestañas fijo abajo (con etiquetas) y deslizar entre
    pestañas con efecto tipo Instagram (`initTabs` en `panel.js`).
  - Nueva pestaña Feedback (`/panel/feedback`, `POST /api/feedback`, tabla
    `feedback`, `finmate/services/feedback.py`): se guarda en la base y se
    envía a claude.heymate@gmail.com por SMTP (si se configura) o FormSubmit.
    PENDIENTE (Joaco): mandar un primer feedback y presionar "Activate Form"
    en el correo de FormSubmit; luego opcional `FEEDBACK_FORMSUBMIT_ID`.
  - Arreglado: en celular, Inversiones se veía alejada (el `.sr-only` de la
    tabla estiraba la página → `.table-wrap { position: relative }`).
  - 62/62 tests.
- **Deuda técnica menor:** `twilio` estaba pineado en `9.4.0`, que PyPI
  marca como "yanked" — se subió a `9.4.1` (25 oct 2026, sin romper nada,
  verificado). `pyflakes` señala imports sin usar y f-strings sin
  placeholders en `webhook.py`, `formatter.py`, `engine.py`,
  `gcal_client.py`, `main.py` — cosmético, no afecta funcionamiento, no se
  tocó para no mezclar cambios.

## Actualización 8 nov 2026 — Plan Fases 1, 2, 4, 5 y 6 (parcial)

Escrito el 29 oct, verificado el 8 nov contra SQLite temporal + Finnhub real. 20 tools en
`finmate/agent/tools.py`. Nuevos módulos: `personality_tools.py` + `db/personality_repo.py`
(personalidad en system prompt), `market_tools.py` (`explain_movement`), `news_tools.py` +
`db/news_repo.py` + `data_sources/economic_calendar.py` (temas e indicadores seguidos,
catálogo curado sin fechas reales), `finance_tools.py` + `db/finance_repo.py` (gastos/ingresos,
categorías: Vivienda, Alimentación, Transporte, Ocio, Salud, Educación, Otros),
`db/alerts_log_repo.py` (tabla creada, todavía no la usan los motores de alertas).
Tablas nuevas en `db/models.py`: `personality_settings`, `news_topics_followed`,
`economic_indicators_followed`, `transactions`, `budget_categories`, `alerts_log`
(`init_db()` las crea solas). Fixes del 8 nov: `add_expense` exige `tipo` gasto/ingreso,
categorías sin tilde se normalizan, `explain_movement` filtra noticias por ticker/empresa.
**Subido a GitHub `main` el 8 nov 2026** (la carpeta local no es un repo git funcional).
En Railway → Variables, NO aceptar las "Suggested Variables" (son placeholders de `.env.example`). Detalle en `docs/03_ESTADO_ACTUAL_Y_PROXIMOS_PASOS.md`.

## Actualización 16 nov 2026 — Neon, plantillas y pagos

- Neon: las 10 tablas de `models.py` creadas en la base `neondb` (rama `production`) y probadas.
- Twilio: las 3 plantillas creadas (SIDs en `docs/05_WHATSAPP_TEMPLATES_TWILIO.md`), sin mandar a
  Meta porque falta un WhatsApp Sender propio. No cargar los SIDs en Railway hasta que estén aprobadas.
- **Pagos pendientes** (detalle en `docs/03_ESTADO_ACTUAL_Y_PROXIMOS_PASOS.md`): créditos de la API de
  Claude (saldo USD 0, bloqueante), Railway Hobby USD 5/mes (bloqueante), upgrade de Twilio (para
  WhatsApp real).

## Actualización 16 nov 2026 (tarde) — Panel web: etapas 1, 2 y 3 listas

Plan del panel: `docs/06_PANEL_WEB_DISENO_Y_CONEXION.md`. Etapas 1–3 programadas y probadas
(29 tests con `pytest`, SQLite temporal y precios simulados; capturas revisadas en escritorio y
celular). Sin desplegar todavía (Railway sigue pausado).
- **Etapa 1 (datos):** `portfolio_holdings` + `asset_class`, `sector`; `transactions` +
  `occasion`, `merchant`, `receipt_url`; tabla nueva `notification_settings` (umbral de watchlist y
  resumen semanal por usuario). `init_db()` agrega solas las columnas que falten
  (`_ensure_added_columns`, sin Alembic). Categorías de gasto nuevas: Evento Social, Polola,
  Copete, Comidas, Regalos, Viajes, Otros (bot y panel). `finmate/services/portfolio.py`:
  ganancia/pérdida, distribución por clase y sector, top 3 ganadoras/perdedoras; clasifica solo
  (ETFs de bonos → renta fija; acciones → sector de Finnhub `profile2`). `watchlist_alerts.py`
  usa el umbral de cada usuario y `engine.send_weekly_summary` respeta a quien lo apagó.
- **Etapa 2 (API):** `finmate/web/api.py` en `/api/*` (resumen, portafolio, watchlist,
  explicar movimiento, finanzas, personalidad, seguimientos, avisos, chat con el mismo agente).
  Sesión con cookie firmada (`FLASK_SECRET_KEY`), anti-CSRF con encabezado `X-Finmate: 1`,
  cada consulta filtrada por el usuario de la sesión. Login provisorio `/api/auth/dev-login`
  solo si `PANEL_DEV_LOGIN=true` (apagado por defecto; nunca en producción).
- **Etapa 3 (pantallas):** `finmate/web/panel.py` + `templates/panel/` + `static/panel/`
  en `/panel/` (Resumen, Mis inversiones, Mis gastos, Ajustes, Acceso), con la marca.
  Datos de prueba: `python scripts/seed_demo.py +56900000000` (contra una base de prueba).
- **Para probar en local:** `DATABASE_URL=sqlite:///demo.db PANEL_DEV_LOGIN=true FLASK_DEBUG=true
  python scripts/seed_demo.py +56900000000` y luego `python main.py` → http://localhost:5000/panel/
  (sin `FINNHUB_API_KEY` los precios salen vacíos). Tests: `pip install -r requirements-dev.txt && pytest`.
- **Antes de desplegar:** cargar `FLASK_SECRET_KEY` en Railway. Pendiente: etapa 4 (login por
  código de WhatsApp), 5 (boletas con foto) y 6 (lanzamiento).

## Cambios del 16 nov 2026 (noche) — subidos a GitHub, no desplegados en Railway

- **Deslizar entre pestañas sin recargar:** las 5 pestañas viven en la misma
  página (`templates/panel/_pane_*.html` + `base.html`); `initTabs` en
  `panel.js` mueve un "riel" con el dedo y usa `history.pushState`.
- **Barra de abajo se esconde al bajar y vuelve al subir** (`initAutoHideRail`).
- **Sin zoom en el celular:** viewport `maximum-scale=1, user-scalable=no`,
  `touch-action: pan-x pan-y`, bloqueo de pellizco/doble toque en JS y campos
  a 16px (iOS hace zoom al tocar campos más chicos).
- **Gastos:** categorías por defecto Comidas, Carretes, Asados, Regalos,
  Suscripciones, Polola, Copete, Bets (+ "Otros" fijo). Cada usuario puede
  sacar las por defecto (tabla nueva `hidden_categories`) y agregar propias
  (`budget_categories` con `user_id`), solo para su cuenta — en el panel
  ("Mis categorías") y por WhatsApp (tool `manage_expense_categories`).
  Gastos en categorías sacadas siguen apareciendo en los totales.
  La pestaña Gastos ahora tiene torta del mes + torta del año (YTD) y una
  tabla "Este mes vs. Lst Mth" por categoría (`/api/finanzas/resumen` trae
  `anio`).
- **Feedback:** la tarjeta de abajo quedó en una sola frase.
- **Demo pública:** se regenera con `python scripts/build_demo.py` (no toca
  `demo-api.js`, que tiene los datos de ejemplo; su clave de localStorage es
  `finmate-demo-v2`).
- **Ideas de feedback:** se leen desde claude.heymate@gmail.com (correos de
  FormSubmit). Última revisión: 16 nov 2026 — implementadas las 3 ideas
  (tabla comparativa + YTD, barra que se esconde, texto de feedback).
  Pendiente de conversar: botón/íconos de WhatsApp. Revisión 18 nov:
  idioma (sin voseo + selector inglés) y fondo blanco, ver sección abajo.
- **Ojo:** hay un servicio "finmate" en Render que falla al compilar con cada
  cambio (66 correos "build failed"). No es Railway; Joaco debería pausarlo
  o borrarlo si no lo usa.

## Cambio del 20 nov 2026 — WhatsApp por Meta directo (sin Twilio)

Twilio no dejó verificar la cuenta. El bot ahora soporta la **WhatsApp Cloud
API de Meta** directo (sin cuota mensual ni recargo por mensaje); Twilio
queda como respaldo. Se elige solo: con `META_WHATSAPP_TOKEN` +
`META_PHONE_NUMBER_ID` cargadas usa Meta. Detalle completo, variables y pasos:
`docs/08_WHATSAPP_META_CLOUD_API.md`. Código: `finmate/whatsapp/meta_cloud.py`,
`messenger.py`, `webhook.py` (GET de verificación + POST JSON, respuesta en
hilo con dedupe por id). Las variables de plantillas del código se renombraron
a `TEMPLATE_*`. 81/81 tests. Pendiente (Joaco): crear la app en
developers.facebook.com, número de prueba, luego el prepago chileno.

## Cambios del 18 nov 2026 — tema blanco, ícono nuevo e idioma (no subidos aún)

- **Tema blanco** en el panel y la demo: `panel.css` con fondo #FFFFFF, tarjetas
  blancas con borde #E3E8EF + sombra suave, texto azul marino, subidas #00805F y
  bajadas #C2410C (contraste sobre blanco), sin "orbs". Pestaña activa azul con
  ícono blanco. `theme-color`/manifest en #FFFFFF y barra de estado iOS "default".
- **Ícono de pantalla de inicio**: fondo blanco, F azul, línea verde, generado
  desde `docs/marca/finmate-icono.png` (todos los tamaños + maskable). Logo del
  encabezado: `finmate-icon.png` (se borró `finmate-icon-white.png`). Quien ya
  lo tenía en el celular debe quitarlo y volver a agregarlo.
- **Idioma**: tarjeta "Idioma de la app" (Español/English) en Ajustes.
  `static/panel/i18n.js` (se carga en `<head>` vía `_app_head.html`) traduce en
  el navegador textos y atributos, incluso lo que agrega `panel.js`
  (MutationObserver). Textos nuevos → agregarlos a `DICT` o `RULES` en
  `i18n.js`. Preferencia por dispositivo (localStorage `finmate-lang`). El bot
  sigue en español. Montos mantienen formato chileno.
- **Sin voseo** en todo el panel y mensajes de `web/api.py` (tú, español
  neutro). El bot de WhatsApp (orchestrator + tools) **todavía** usa voseo.
- Demo: `scripts/build_demo.py` ahora copia `i18n.js`, íconos y manifest; el
  aviso "versión de prueba" ya no tapa el botón de entrar.
- Tests: `tests/test_idioma_tema.py`. 73/73 pasan.

## Tareas pendientes (anotadas 16 nov 2026)

- **Rentabilidad de fondos chilenos (CMF):** prueba exitosa el 16 nov 2026 desde
  el computador de Joaco con LarrainVial Enfoque (RUN 8723-8) y Monetario (RUN
  8177-9). Fuente: export Excel de la CMF,
  `fm.fm_bpr_dia.php?admins=<RUT>&tipofondo=0&moneda=0&dia_select=<DIA>&mes_peri=<MES>&anio_peri=<AÑO>&lang=es&out=excel`
  (`dia_select` = día del mes; publica con 1 día de retraso; si no hay datos
  devuelve HTML "No se encuentran datos"). Columnas: nombre, RUN, tipo, admin,
  serie, moneda, patrimonio, partícipes, valor cuota. Códigos: LarrainVial AM
  96955500, Banchile 96767630, Scotia AGF 96634320. Falta: (1) confirmar que la
  CMF responde desde Railway (desde la nube de Claude dio 403); (2) módulo con
  descarga diaria, rentabilidad 1d (vs último día hábil)/1m/YTD/12m, sección
  "Fondos" en el panel y tool del bot; (3) preguntar a Joaco su serie (A o APV).
  Morningstar descartado (solo enterprise); Fintual pide token para valores diarios.
- **Login real del panel con código por WhatsApp ("etapa 4"):** no está hecho.
  Hoy solo existe `dev-login` (entra con el número, sin verificar) — nunca
  activarlo en producción.

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

## 23 nov 2026 — Bot de WhatsApp por Meta FUNCIONANDO en producción

- Número propio +56 9 4061 3812 ("Finmate", VERIFIED), phone id `1409562878916070`, WABA
  `932895863123752`. Recibe y responde por la Cloud API (Twilio queda solo de respaldo).
- Por qué no respondía (3 causas, todas resueltas):
  1. `--preload` en el Procfile: base de datos y clientes HTTP se heredaban por fork y el hilo
     de respuesta se colgaba sin log. Se sacó (1 solo worker, así que el scheduler no se duplica).
  2. Imports perezosos desde varios hilos a la vez (respuesta + precios + alertas) podían
     trabarse: `wsgi.py` ahora importa al arrancar orquestador, messenger, alertas y quotes.
  3. `ANTHROPIC_API_KEY` inválida en Railway (401) y saldo USD 0: Joaco creó la clave
     `finmate-railway-2` (vence 23 dic 2026, renovarla antes) y cargó USD 5.
- Diagnóstico nuevo en el log: "Procesando respuesta para…", "Respuesta a … enviada/NO enviada",
  estados de Meta (sent/delivered/FALLÓ) y volcado de hilos si una respuesta tarda más de 90 s.
- Timeouts: Claude 60 s (2 reintentos), Postgres `connect_timeout=10` + `pool_recycle=300`.
- Pendiente: borrar `META_TEST_RECIPIENT` en Railway (hello_world falla con 131058 en números
  reales), borrar variables de Twilio, método de pago en WhatsApp Manager (solo necesario para
  mensajes iniciados por el bot / plantillas), crear plantillas de Meta y cargar `META_TEMPLATE_*`.

## 23 nov 2026 (tarde) — plantillas de Meta, tuteo y avisos sin repetir

- **Plantillas de Meta enviadas a revisión (categoría Utilidad, idioma Spanish `es`):**
  `finmate_watchlist_alert` ({{1}} símbolo, {{2}} variación, {{3}} precio),
  `finmate_market_notify` ({{1}} tipo de novedad) y `finmate_weekly_summary_notify` (sin
  variables). Textos redactados como "Aviso de tu cuenta Finmate…" porque Meta marcaba los
  primeros borradores como Marketing. **Cuando estén aprobadas**, cargar en Railway:
  `META_TEMPLATE_WATCHLIST_ALERT=finmate_watchlist_alert`,
  `META_TEMPLATE_MARKET_NOTIFY=finmate_market_notify`,
  `META_TEMPLATE_WEEKLY_SUMMARY_NOTIFY=finmate_weekly_summary_notify`. No cargarlas antes.
- **Bot en tuteo chileno:** se sacó el voseo de prompt y textos de tools/alertas; el system
  prompt lo pide explícito. Test `tests/test_bot_sin_voseo.py`.
- **Avisos repetidos tras cada redeploy (arreglado):** el estado de dedup/colas vivía en
  archivos JSON del contenedor y Railway los borra al redeployar (NVDA llegó 10 veces). Ahora
  vive en la tabla `kv_state` (`finmate/db/state_store.py`); sin base cae al archivo.
  Afecta watchlist, noticias, motor broadcast, podcasts y cola de pendientes.
- **Movimientos extremos en vivo (≥15%)** se confirman con la cotización REST antes de avisar
  (`EXTREME_MOVE_PCT` en `watchlist_alerts.py`). Ojo: la alerta de NVDA decía ~+34%; NVDA
  cerraba ~US$151 a mediados de nov. Revisar de dónde sale el cierre anterior (`pc`) si se repite.
- `META_TEST_RECIPIENT` ya no está en Railway. Clave de Claude: `finmate-railway-prod`, sin
  vencimiento (Joaco). Render: el servicio "finmate" sigue fallando; requiere que Joaco
  inicie sesión y lo suspenda.
- 90/90 tests.

## Actualización 23 nov 2026 — Panel de administrador (desplegado en Railway)

URL: https://web-production-3626a.up.railway.app/admin/ (login con Google, solo
`ADMIN_EMAILS`, por defecto claude.heymate@gmail.com). Mismo diseño que el panel de usuarios.
- **Pestañas:** Costos (suscripciones editables en kv `admin:subscriptions` + consumo real del
  mes de Claude y WhatsApp, `finmate/services/usage.py`, precios editables en `admin:prices`),
  Usuarios (inicio, último mensaje, nº de mensajes, aprobar/quitar acceso), Inbox (solicitudes
  de números nuevos + feedback con estado y nota interna), Fuentes (catálogo
  `finmate/admin/sources.py` con botón "Probar", notas e ideas).
- **Acceso por aprobación:** `users.access_status` (NULL = aprobado, así los usuarios antiguos
  siguen entrando). Con `ACCESS_APPROVAL_REQUIRED=true` (default) un número nuevo queda
  `pending`: el bot le responde que su acceso está pendiente (sin llamar a Claude), se avisa a
  `WHATSAPP_RECIPIENTS` con link al Inbox y no puede pedir código para el panel. Al aprobar se le
  manda bienvenida por WhatsApp (si está dentro de las 24 h).
- Código: `finmate/web/admin.py`, `finmate/admin/`, `templates/admin/`, `static/panel/admin.{css,js}`.
  Tests: `tests/test_admin.py` (12). Suite completa: 124/124.
- **Google OAuth listo (23 nov):** proyecto Google Cloud `finmate-515700`, app "Finmate Admin"
  en modo Prueba (usuario de prueba: claude.heymate@gmail.com), cliente web "Finmate Admin
  (Railway)". Variables cargadas en Railway; login probado y funcionando. Ojo: tras cambiar
  variables en Railway hubo que hacer Redeploy a mano. `ADMIN_DEV_LOGIN` nunca en producción.
  Pendiente: completar el costo del chip prepago en Costos.
- **Registro (23 nov, noche):** un número nuevo pendiente recibe un pedido de *nombre y apellido*
  y *correo* (`finmate/agent/signup.py`, reglas simples sin Claude; el borrador vive en kv
  `signup:<user_id>`). Con ambos datos se guardan en `users.name`/`users.email`/`registered_at`,
  y se avisa al admin por WhatsApp (`WHATSAPP_RECIPIENTS`) y por correo (mismo envío que el
  feedback: SMTP o FormSubmit a claude.heymate@gmail.com). Admin → Usuarios muestra el correo y
  tiene "Descargar CSV" (`/admin/api/usuarios.csv`). 126/126 tests.
- **Íconos y app admin en celular (23 nov, noche):** ícono nuevo (logo de Joaco). App de usuarios:
  fondo blanco (`icon-*.png`, `apple-touch-icon.png`, `manifest.json`, cache `?v=4`). App admin:
  fondo azul #082449 con la F blanca (`admin-*.png`, `admin-manifest.json` con scope `/admin/`,
  `templates/admin/_app_head.html`), se instala aparte como "Finmate Admin". En celular el admin
  usa lo mismo que la de usuarios: barra abajo con píldora, se esconde al bajar, deslizar cambia
  de pestaña, sin zoom, y las tablas se ven como tarjetas (`.admin-table.stack`). Demo pública
  regenerada con el ícono nuevo. 127/127 tests.
- **Mensaje de aprobación (23 nov):** al aprobar en el admin, el usuario recibe por WhatsApp
  `approval_message()` (`finmate/web/admin.py`): aviso de aprobado, link a `/panel/`, qué tiene
  cada pestaña y para qué sirve la app. Se guarda en el historial. Solo llega si el usuario
  escribió en las últimas 24 h (ventana de WhatsApp); si no, el admin lo ve y el usuario se
  entera al volver a escribir. 128/128 tests.

## Actualización 24 nov 2026 — Limpieza completa + capas de seguridad

**Fuente de verdad:** GitHub `main`. Antes de editar en una sesión nueva, clonar el repo
(`git clone https://github.com/claudeheymate-code/finmate.git`, es público) y comparar con la
carpeta local; subir con el editor web de GitHub (no hay credenciales para push).

- **Bug grave de seguridad corregido:** el webhook aceptaba la ruta antigua de Twilio (formulario
  sin firma): cualquiera podía hacerse pasar por cualquier número y recibir la respuesta del bot
  (portafolio, link de acceso al panel). Se sacó Twilio completo (messenger, webhook, settings,
  dependencia `twilio`). Todo POST al webhook que no sea JSON firmado por Meta → 403 + evento.
- **Claves en los logs:** las URLs de Finnhub/Marketaux dejaban la clave a la vista en Railway.
  `finmate/security/logfilter.py` las oculta (token=, api_token=, sk-…, EAA…) y baja el ruido
  (httpx, apscheduler, "0 alertas enviadas"). **Recomendado rotar FINNHUB_API_KEY y
  MARKETAUX_API_KEY** (estuvieron visibles en los logs).
- **Servidor:** `railway.json` tenía `--preload` (pisa al Procfile): la conexión a la base se
  creaba antes del fork → cuelgues intermitentes. Ahora: sin preload, 8 hilos, timeout 120 s.
- **Páginas:** CSS/JS con versión por deploy (`asset_v` en templates, evita mezclar caché vieja →
  páginas descuadradas); `api()` con timeout (20 s, chat 90 s) y mensaje claro en vez de quedar
  "Cargando…". Auditoría con navegador headless: 20 páginas (celular y escritorio) sin errores
  ni desbordes.
- **Limpieza:** fuera FMP (`fmp_client.py`; índices del resumen semanal ahora con Finnhub SPY/DIA/
  QQQ), `alerts_log_repo.py` (nunca se usó), `finmate-icon-white.png`, imports sin uso.
  La tabla `alerts_log` sigue en la base (no se borra nada de datos).
- **Bot:** registro de números nuevos ya no depende de la clave de Claude; límite de 25 mensajes/
  10 min por número (protege el gasto); sesión del panel se corta al quitar el acceso.
- **Seguridad (`finmate/security/`):** `guard.py` (bloqueo de escaneos /.env /wp-admin…, límite
  por IP 300/min y 20 ingresos/10 min, fuerza bruta de códigos → bloqueo 30 min, anti-CSRF en
  toda escritura, CSP/HSTS/X-Frame…), `monitor.py` (tabla `security_events`, agrupa repetidos,
  WhatsApp al admin si es grave, máx. 1 por tipo cada 30 min), `checks.py` (configuración
  insegura, integridad de archivos vs. arranque y vs. GitHub por `RAILWAY_GIT_COMMIT_SHA`,
  librerías vulnerables vía OSV, gasto de Claude > `SECURITY_CLAUDE_MONTHLY_ALERT_USD`).
  Admin → Inbox → **Seguridad** (estado, eventos, "Ejecutar chequeo ahora", marcar revisado).
- **Jobs:** chequeo diario 4:17 y revisión mensual día 1 a las 10:07 (recordatorio de limpieza
  en el Inbox + WhatsApp). 145/145 tests (`tests/test_seguridad.py`, 17 nuevos).

## Actualización 24 nov 2026 (tarde) — Arreglos del bot, fotos/PDF y "jornada"

- **Por qué a veces respondía "no puedo procesar":** (1) fotos, stickers y
  reacciones recibían "solo puedo leer texto" → ahora reacciones/stickers se
  ignoran y fotos/PDF se procesan; (2) se acababan las rondas de tools y salía
  "No pude generar una respuesta" → ahora 8 rondas, 1500 tokens y, si no hay
  texto, se fuerza una respuesta final (`tool_choice=none`); (3) errores 401 de
  la key vieja de Claude (20–23 nov) → ahora un 401 o falta de créditos crea un
  evento `claude_error` en el Inbox de seguridad del admin.
- **Fotos y documentos:** `meta_cloud.parse_incoming` trae `media`,
  `download_media()` las baja (máx 15 MB). `webhook._queue_media` agrupa los
  archivos que llegan juntos (4 s) y llama a `handle_message(attachments=...)`.
  Imágenes (≤5 MB), PDF y CSV/texto. Con adjuntos se usa
  `ANTHROPIC_MODEL_ANALYSIS` (Sonnet). Tools nuevas en
  `agent/document_tools.py`: `add_expenses_batch` (cartolas/boletas, siempre
  con confirmación previa) e `import_portfolio` (pantallazo/cartola de
  inversiones, modo replace). 36 tools.
- **Jornada por usuario:** columnas `workday_enabled/start/end/weekends` en
  `notification_settings` (default 08:30–18:30 lun–vie). `services/workday.py`:
  fuera de la jornada los avisos proactivos (watchlist, noticias, macro,
  podcasts, broadcast, resumen semanal) se guardan (`held:{uid}`) en vez de
  mandarse. `services/daily_brief.py`: al inicio y al cierre manda un párrafo
  con lo relevante (índices, sus símbolos, noticias, portafolio, Chile y, al
  inicio, calendario + lo retenido). Job `workday_briefs` cada 5 min en
  `main.py` (reemplazó a los avisos de apertura/cierre de mercado). Se
  configura en Ajustes → "Tu jornada" o por chat (`set_notification_settings`).
- Logs más limpios: Finnhub 403 bloquea ese endpoint 24 h; gcal sin
  credenciales se loguea una vez; aviso de discrepancia de watchlist 1 vez/día.
- 165 tests pasan.

## 25 nov 2026 — Nuevo formato de los resúmenes de jornada (no subido aún)

`services/daily_brief.py`: encabezado con fecha (`☀️ *Inicio de jornada* · miércoles 25 nov`), un
párrafo conceptual de Claude Haiku (qué pasó y por qué, noticias de mayor impacto, máx. 2-3 cifras)
y debajo viñetas armadas por código (nunca por Claude): 📊 índices vía ETF (SPY/QQQ/DIA/ECH), 🇨🇱
dólar/UF/TPM (BCCH), ⭐ tus tickers ordenados por variación (💼 = en portafolio), 💼 portafolio, y
solo al inicio 🗓️ datos de EE.UU. de hoy (FRED) y 📬 avisos guardados fuera de horario. Secciones
sin datos no aparecen. Sin Claude, el párrafo usa los titulares. `send_brief` recibe `tz_name`.
Sin futuros, IPSA ni cobre (no hay fuente gratis conectada). 168/168 tests.

## 25 nov 2026 (tarde) — Perfil de noticias con notas 1-3 (no subido aún)

- **Formato:** negrita solo en títulos de sección/aviso; viñetas y párrafo sin asteriscos
  (`daily_brief._plain` limpia lo que devuelva Claude). Avisos de resultados/macro/noticias en
  `formatter.py` sin "ALERTA —" ni cursivas.
- **Perfil (`finmate/services/news_profile.py`):** cada noticia tiene claves `sym:X`, `tema:<tema>`
  (clasificador por palabras clave, 15 temas) y `tipo:activo|mercado|resultados|macro`. Cada nota
  1-3 se suma a sus claves (olvido 3% por nota). Estimado = promedio con supuesto inicial 3 que
  pesa 4 notas → cambia de a poco. Nivel 3 ≥2,4; 2 ≥1,6; 1 debajo. El `tipo` se limita a 3 notas
  de peso (empuja pero no baja un tema solo). Nivel 1 "gradual": se muestra en el resumen con
  probabilidad que baja de 100% a 10%, y se descarta solo con evidencia ≥12 y estimado <1,4
  (~9 notas si es de una empresa, ~24 si es un tema general). Tablas nuevas: `news_preferences`,
  `news_ratings`, `news_display_settings`. Estado en kv: `newsref:`, `newslast:`, `digest:`,
  `briefcodes:`.
- **Entrega:** `news_profile.deliver()` lo usan `news_alerts` (ahora una noticia por mensaje) y
  `engine._broadcast_or_queue(news=...)` (resultados, macro, noticias del mercado). Por chat va con
  botones 1·Poco / 2·Algo / 3·Mucho (`meta_cloud.send_buttons`, `messenger.send_buttons`; si no se
  puede, texto con "Responde 1, 2 o 3"). Nivel 2, nivel 1 mostrado y todo lo de fuera de horario
  → `digest`, que sale en el resumen de jornada como "📰 Noticias para ti" con letras (a3 b1).
- **Calificar:** botón → `webhook` → `orchestrator.handle_rating_button`. Texto "3" solo si lo
  último que mandó el bot fue una noticia; "a3 b1" hasta 48 h después del resumen. Ambos sin Claude.
- **Bot:** tools `get_news_profile`, `set_news_preference`; el prompt explica los niveles en la
  bienvenida (paso 3) y que a pedido se muestran todas las noticias. `_clean_history` junta turnos
  seguidos del mismo rol (avisos guardados en el historial).
- **Panel:** Ajustes → "Tus noticias" (dónde va cada nivel + lo aprendido por tema, con fijar a mano
  o automático). API `/api/noticias/perfil` (GET/PUT/DELETE) y `/api/noticias/display` (PUT).
- **Bienvenida** (`admin.approval_message`) explica los 3 niveles. Podcasts y recordatorios de
  calendario macro no se califican (no son noticias). 184/184 tests (`tests/test_perfil_noticias.py`).

## 25 nov 2026 — Pestaña Anuncios en el panel admin (no subido aún)

`/admin/anuncios`: redactar un mensaje (título opcional + texto), vista previa estilo WhatsApp,
botón "Ayúdame a redactar" (Claude Haiku convierte notas en anuncio, `announcements.draft_with_ai`),
"Usar ejemplo" (anuncio del perfil de noticias), enviar "Solo a mí (prueba)" a `WHATSAPP_RECIPIENTS`
o a todos los usuarios aprobados (con segundo toque de confirmación). Código:
`finmate/admin/announcements.py`; tablas `announcements` y `announcement_deliveries`.
Ventana de 24 h: a quien escribió hace < 23,5 h le llega al tiro ("sent"); si hay
`TEMPLATE_MARKET_NOTIFY`, plantilla + cola ("template"); si no, queda "pending" y
`webhook._answer_meta` lo manda justo después de responder su próximo mensaje ("later").
Historial con conteos y "Dejar de entregar" para los pendientes. El anuncio queda en el
historial del bot. Tests: `tests/test_anuncios.py`. 190/190.

## 25 nov 2026 — Resúmenes que no llegaban: ventana de 24 h (no subido aún)

Diagnóstico (logs de Railway): a las 08:30 el bot "envió" los 3 resúmenes de inicio, pero Meta
rechazó el del usuario 4 (…9451) con `131047 Re-engagement message`: no escribía hace ~33 h. Meta
acepta el envío y lo rechaza después (webhook de estado), así que nuestro log decía "enviado" y lo
guardado para ese resumen se perdía. Lo mismo pasaba con noticias y alertas de watchlist.
Arreglo: `workday.window_open/can_message` (último mensaje del usuario < 23,5 h, o plantilla
configurada). Sin ventana: `send_brief` no manda ni vacía nada y marca `brief:pending:{uid}`;
cuando el usuario escribe, `webhook` llama `daily_brief.deliver_pending_brief` → un solo resumen
"🗞️ Lo que te perdiste" armado con todo lo acumulado. `workday.allow` guarda los avisos y
`news_profile.deliver` manda las noticias al resumen. Admin → Usuarios muestra "24 h" o
"Ventana cerrada". La solución de fondo son las plantillas de Meta: al aprobarse y cargar
`META_TEMPLATE_MARKET_NOTIFY`, todo vuelve a llegar a tiempo. Tests: `tests/test_ventana_24h.py`
(el conftest deja la ventana abierta por defecto; fixture `window_closed`). 196/196.

## 25 nov 2026 — Plantillas aprobadas + aviso diario por plantilla (no subido aún)

- Las 3 plantillas del 23 nov están **aprobadas** ("Activa: calidad pendiente"). Joaco agregó el
  medio de pago en WhatsApp Manager. Decisión de Joaco: **NO cargar** `META_TEMPLATE_WATCHLIST_ALERT`,
  `META_TEMPLATE_MARKET_NOTIFY` ni `META_TEMPLATE_WEEKLY_SUMMARY_NOTIFY` (con ellas cargadas el código
  usa la plantilla SIEMPRE, incluso con la ventana abierta). En su lugar, un aviso diario.
- Plantilla nueva `finmate_buenos_dias` (Utilidad, es, **en revisión** desde el 25 nov 11:2x). Meta
  rechazaba las versiones con "Buenos días…" como Utilidad (sugería Marketing). Texto enviado:
  "Aviso de tu cuenta Finmate: {{1}}, tu resumen de inicio de jornada de hoy ya está disponible
  ({{2}}). Recibes este aviso porque activaste el resumen diario. Responde a este mensaje para
  recibir el detalle completo." Botones: "Sí, mándamelo" / "Hoy no". {{1}} nombre, {{2}} destacado.
- Código: `META_TEMPLATE_MORNING_BRIEF` (config). En `send_brief("start")`, si la ventana de 24 h
  está cerrada y es lunes a viernes, manda la plantilla con `morning_highlight()` (Claude Haiku, una
  frase por día, cache kv `morning:highlight:<fecha>`) y deja el resumen pendiente
  (`via=template`). `webhook` → `handle_morning_reply`: "Sí, mándamelo" manda el resumen normal;
  "Hoy no" lo descarta. Cualquier otro mensaje: respuesta normal + resumen pendiente.
- **Al aprobarse:** cargar en Railway `META_TEMPLATE_MORNING_BRIEF=finmate_buenos_dias`. 200/200 tests.
- **25 nov, 12:10 — notas en silencio (pedido de Joaco):** al calificar (botón, "3" o "a3 b1") el
  bot ya no responde "Anotado" ni guarda la nota en el historial; `news_profile.RATED` marca que se
  registró, `handle_message` devuelve "" y `webhook` no manda nada. WhatsApp igual muestra el botón
  tocado como mensaje del usuario (no se puede ocultar). 201/201 tests.
- **25 nov, 12:30 — asteriscos y emojis:** Claude escribía `**negrita**` (Markdown) y en WhatsApp
  quedaban los asteriscos a la vista. `finmate/utils/text.py`: `whatsapp_markup` (** → *, ## → *título*,
  [t](url) → "t: url", __ → _, ~~ → ~) se aplica a TODO mensaje en `WhatsAppMessenger.send_message`
  y `send_buttons`; el prompt pide un solo asterisco. Ajuste nuevo de personalidad **Emojis 1-10**
  (`personality_settings.emojis`, default 4): va en el prompt (1-2 ninguno, listas con •; 5-7
  emojis en listas; 8-10 muchos) y con 1-2 `prepare_for` quita los emojis de todo lo que sale
  (resúmenes, avisos, noticias), dejando ▲▼•. Panel → Ajustes → Personalidad: slider "Emojis".
  Tool `set_personality` acepta `emojis`. 206/206 tests (`tests/test_formato_whatsapp.py`).

## 25 nov 2026 (tarde) — Costo por usuario en el admin (subido a GitHub)

- `services/usage.py`: además del total mensual, anota el consumo por número en
  `usage:users:<AAAA-MM>` → `{"569…": {"claude": {modelo: tokens}, "wa": {"text", "template", …}}}`.
  WhatsApp se atribuye por destinatario (`meta_cloud._post` pasa `to`); Claude por contexto
  (`usage.for_user(phone)`, que envuelve `orchestrator.handle_message` y `daily_brief._build_and_send`).
  Lo global (destacado del día, redactar anuncios) queda solo en el total. Empezó a medirse al
  desplegar (`usage:users:since`); lo anterior no tiene detalle por usuario.
- Admin → Usuarios: tarjeta "Costo por usuario" con 3 niveles (bajo 0–29, medio 30–150, alto 151+
  mensajes del mes): estimado mensual = costo promedio por mensaje del mes × 20/80/300 mensajes,
  más el promedio real de los usuarios de cada nivel. Tabla: mensajes del mes, costo del mes y costo
  por mensaje (detalle Claude/WhatsApp al pasar el mouse). CSV con costo del mes. Usa los precios de
  Costos (modelos de Claude y plantilla de WhatsApp).
- Arreglo: `.hide-sm { display: inline }` desarmaba las columnas de las tablas del admin en
  escritorio (celdas inline); ahora `td/th.hide-sm` son `table-cell`.
- La carpeta local NO tiene estos cambios (se hicieron sobre el clon de GitHub): hacer pull/copiar.
- 209/209 tests (`tests/test_costos_usuarios.py`).

## 25 nov 2026 — Imágenes del portafolio por WhatsApp

- Tool `send_portfolio_chart` (`kind`: `torta`, `torta_clase`, `torta_sector`, `barras`, `tabla`):
  el bot genera un PNG con matplotlib en el servidor (`finmate/services/charts.py`, colores de la
  marca, máx. 7 porciones / 14 filas) y lo manda como imagen (`meta_cloud.upload_media` +
  `send_image`; `messenger.send_image`). Cuando el usuario pide su portafolio, el bot ofrece
  torta, barras o tabla (sección IMÁGENES DEL PORTAFOLIO del prompt).
- Costos: generar la imagen US$0 (CPU propia, <1 s); subir media a Meta gratis; la imagen cuenta
  como mensaje de servicio (gratis hasta 1.000/mes por número desde oct 2026, después se cobra).
- Dependencia nueva `matplotlib==3.11.2`. Tests: `tests/test_imagenes_portafolio.py`. 218/218.

## 25 nov 2026 (noche) — Fondos mutuos chilenos (CMF), para todos los usuarios

- Fuente: export Excel público de la CMF con `admins=0` → **todas** las administradoras en 1
  archivo diario (~700 KB, ~2.880 series, ~22 AGF). Sin clave. Publica con 1 día de retraso.
  `finmate/data_sources/cmf_fondos.py` (descarga, lectura con `xlrd` en latin-1, nombres cortos
  de bancos y alias "banco de chile" → Banchile, etc.).
- Base: tablas `fund_quotes` (fecha+RUN+serie) y `followed_funds` (lo que sigue cada usuario,
  con cuotas opcionales). Retención: últimos 45 días completos + último día de cada mes.
- `finmate/services/funds.py`: `refresh()` (jobs 9:43 y 18:43 + uno a los 3 min de arrancar),
  `backfill()` una sola vez (cierres de los últimos 13 meses, marcado en kv `cmf:backfill_done`),
  búsqueda por nombre/banco/tipo, rentabilidad 1d/1m/año/12m, ranking (una serie por fondo,
  sin series chicas ni de inversionistas calificados), mis fondos.
- Bot: tools `search_funds`, `get_fund`, `rank_funds`, `follow_fund`, `get_my_funds` + sección
  FONDOS MUTUOS CHILENOS en el prompt (información, no recomendación).
- Panel → Mis inversiones → tarjeta "Fondos mutuos": mis fondos (con cuotas y saldo), buscador
  por nombre/banco/tipo con todas las series, ranking 1m/año/12m. API `/api/fondos/*`.
- Admin → Fuentes → "CMF — Fondos mutuos" → **Probar**: baja el último día, lo guarda y, si
  falta, arranca la carga de 13 meses. Es la forma de confirmar que la CMF responde desde Railway
  (desde la nube de Claude daba 403; desde el computador de Joaco funciona).
- Si Railway recibe 403: plan B = subir el archivo diario desde el computador de Joaco.
- Tests: `tests/test_fondos_cmf.py` (+ `tests/fixtures/cmf_fondos_muestra.xls`, recorte real).
