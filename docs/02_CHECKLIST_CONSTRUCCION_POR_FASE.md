# Finmate — Checklist de construcción por fase

> Fuente: artifact "Checklist Finmate" (claude.ai), 28 agosto 2026. Versión HTML original en
> `docs/originales_html/Checklist_Construccion_28ago2026.html`.
> Regla: cada paso complejo trae su verificación — no se avanza sin confirmar que el anterior funciona.
> Marcas actualizadas al 29 oct 2026 con lo que figura en `CLAUDE.md`.
> Ojo: el código avanzó en un orden distinto al plan (portafolio y watchlist se hicieron antes que
> personalidad). Ver la tabla de equivalencias en `03_ESTADO_ACTUAL_Y_PROXIMOS_PASOS.md`.

Leyenda: `[x]` hecho · `[~]` código escrito, falta desplegar/probar en producción · `[ ]` pendiente

---

## Fase 0 — Cimientos

Objetivo: patrón agente-con-memoria-y-tools funcionando de punta a punta con una función (mercados).

- [x] **Escribir y probar el código base** — orquestador con tool-calling, modelos `users` y `conversation_history`, cache Redis, webhook adaptado.
  - ✔ Verificación (sandbox): la app arranca sin credenciales; loop de tool-calling con cliente mockeado OK; webhook devuelve TwiML válido; DB OK contra SQLite. Revalidado 25 oct 2026.
- [x] **API key de Anthropic** creada en platform.claude.com: `finmate-railway`, sin expiración.
  - ✔ Verificación: empieza con `sk-ant-`. Falta pegarla en Railway.
- [x] **Neon**: proyecto Postgres `finmate` (`shiny-term-24632740`), branch `production`, free plan.
  - ✔ Verificación: formato `postgresql://usuario:password@host/db?sslmode=require` (el código normaliza el driver). Falta pegarlo como `DATABASE_URL`.
- [x] **Upstash**: base Redis `finmate` (Free Tier, Ohio us-east-2).
  - ✔ Verificación: empieza con `rediss://default:...@allowed-fowl-209388.upstash.io:6379`. Falta pegarlo como `REDIS_URL`.
- [x] **Subir el código** a `claudeheymate-code/finmate` (branch `main`).
- [ ] **⛔ Reactivar Railway** — servicio `web` dice "Trial expired" / "Service is offline". Joaco tiene que agregar método de pago. **Bloqueador activo.**
- [ ] **Cargar variables en Railway**: `DATABASE_URL`, `REDIS_URL`, `ANTHROPIC_API_KEY`.
  - ✔ Verificación: las tres guardadas, sin comillas ni espacios extra.
- [ ] **Revisar logs del deploy.**
  - ✔ Verificación: aparece `Base de datos inicializada`, sin excepciones al arrancar.
- [ ] **Probar "hola"** y **"¿cómo están los mercados?"** por WhatsApp.
  - ✔ Verificación de cierre: "hola" ya no es texto fijo (lo genera Claude); mercados trae índices, commodities y USD/CLP reales; `conversation_history` en Neon tiene 4 filas.

## Fase 1 — Memoria y personalidad

Objetivo: recuerda la conversación y habla con estilo propio, sin bajar la calidad del análisis.

- [~] Historial de conversación guardado/recuperado por turno (hecho en Fase 0 del código).
- [ ] Crear `personality_settings` (humor, sarcasmo, frecuencia de chistes, nivel conversador, tono) e insertar un registro de prueba.
  - ✔ Verificación: leer/escribir el registro desde Neon con SQL simple.
- [ ] Inyectar la personalidad en el system prompt del orquestador.
  - ✔ Verificación: cambiar humor/sarcasmo en la DB y ver que cambia el tono en WhatsApp, sin bajar el rigor.
- [ ] Centro de Control mínimo (login + perfil + personalidad), con Flask extendido.
  - ✔ Verificación de cierre: cambiar la personalidad desde el panel y verlo reflejado en WhatsApp.

## Fase 2 — Mercados con contexto

Objetivo: actualizaciones automáticas en apertura/cierre que explican el "por qué".

- [~] **Plantillas de WhatsApp Business** — código listo (Fase 1.6 del código), textos redactados en `05_WHATSAPP_TEMPLATES_TWILIO.md`. Falta crearlas en Twilio y someterlas a Meta.
  - ✔ Verificación: al menos una plantilla "Approved" en Twilio Content.
- [~] Cotización de tickers puntuales (no solo índices) — usado por las tools de portafolio/watchlist vía Finnhub.
  - ✔ Verificación: "¿cómo está Apple?" devuelve precio real.
- [~] `watchlist_items` + tool de alta/baja desde el chat (Fase 1 del código).
  - ✔ Verificación: agregar un ticker por chat y verlo en la tabla.
- [~] Alertas proactivas por movimiento de la watchlist (Fase 1.5 del código; umbral `WATCHLIST_ALERT_THRESHOLD_PCT`, default 5%).
- [ ] Scheduler proactivo con triggers de apertura/cierre por timezone y horario configurado.
  - ✔ Verificación: forzar un trigger "en 2 minutos" y que llegue el mensaje con plantilla aprobada sin que el usuario escriba antes.
- [ ] Tool "explicar movimiento" — precio + variación + noticia relacionada.
  - ✔ Verificación de cierre: "¿por qué se movió tanto el Nasdaq hoy?" conecta el número con una noticia real.

## Fase 3 — Portafolio

Objetivo: análisis anclado a las posiciones reales.

- [~] `portfolio_holdings` + tools de alta/edición/baja vía chat (Fase 1 del código; posición neta por símbolo, no libro de transacciones).
  - ✔ Verificación: cargar una posición de prueba y verla en la DB.
- [ ] Cálculo de valor actual, rentabilidad absoluta/%, P&L por posición y total, distribución.
  - ✔ Verificación: comparar con un cálculo a mano en Excel.
- [ ] Cruzar portafolio con noticias y riesgos/oportunidades (portafolio como contexto obligatorio).
  - ✔ Verificación de cierre: "¿qué riesgos tiene mi portafolio?" menciona los activos reales.

## Fase 4 — Noticias y datos económicos

- [ ] `news_topics_followed` y `economic_indicators_followed` + edición por chat o panel.
  - ✔ Verificación: "seguime las noticias de bancos regionales" queda guardado.
- [ ] Integrar calendario económico (consenso + dato anterior).
  - ✔ Verificación: "qué dato importante viene esta semana" vs. calendario público de la Fed.
- [ ] Pre-aviso y post-publicación automáticos con comparación e interpretación.
  - ✔ Verificación: llegan las dos alertas (antes y después) con dato, consenso, interpretación e impacto.
- [ ] Resúmenes diarios/semanales personalizados.
  - ✔ Verificación de cierre: el resumen solo incluye los temas que el usuario sigue.

## Fase 5 — Finanzas personales

- [ ] `transactions` y `budget_categories` con el set inicial de categorías.
- [ ] Extracción estructurada de gasto desde lenguaje natural.
  - ✔ Verificación: 5 gastos escritos distinto ("gasté 8 lucas en el almuerzo", "uber 5.500"...) quedan bien categorizados.
- [ ] Resumen mensual automático y consulta on-demand.
  - ✔ Verificación de cierre: el resumen coincide con una suma manual.

## Fase 6 — Control de ruido

- [~] Dedup de alertas (hoy por archivos JSON de estado, no tabla `alerts_log`).
- [ ] Crear `alerts_log` y umbral de materialidad configurable.
  - ✔ Verificación de cierre: provocar dos veces la misma alerta y que no llegue duplicada.

## Fase 7 — Centro de Control completo

- [ ] Módulos restantes: horarios, noticias, indicadores, mercados seguidos, portafolio, finanzas, reportes.
  - ✔ Verificación de cierre: un cambio por módulo desde el panel se refleja de inmediato en WhatsApp.

## Fase 8 — Hardening y uso real

- [ ] Errores robustos, logging/observabilidad, aislamiento de datos por usuario.
  - ✔ Verificación: con una key inválida de Finnhub, el bot responde un mensaje claro en vez de romperse.
- [ ] Semana de prueba con uso real y ajuste fino.
  - ✔ Verificación final: una semana sin que el bot rompa, con las 4 funciones respondiendo bien.
