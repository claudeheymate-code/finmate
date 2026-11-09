# Finmate — Plan de arquitectura y fases (v2)

> Fuente: artifact "Finmate Agente" (claude.ai), 24 agosto 2026. Versión HTML original en
> `docs/originales_html/Plan_Arquitectura_v2_24ago2026.html`.
> Estado de avance real de cada fase: ver `03_ESTADO_ACTUAL_Y_PROXIMOS_PASOS.md`.

Plan de construcción para las cuatro funciones (noticias/datos económicos, portafolio,
mercados, finanzas personales), la proactividad con memoria persistente, la personalidad
configurable y el Centro de Control web. Para cada decisión técnica: la mejor opción sin
mirar el costo, y una alternativa más económica.

---

## 00 · Resumen ejecutivo

Finmate pasa de agente conversacional básico a un **asistente financiero proactivo,
personalizable y con memoria persistente**, con cuatro funciones, personalidad
configurable, y un **Centro de Control web** para administrar todo sin tocar código.

Lo más importante: el agente ya no solo *responde* — debe **iniciar conversaciones**
dentro de horarios configurados por el usuario. Eso trae dos piezas nuevas:

1. Un **scheduler proactivo** consciente de horarios/timezone por usuario.
2. Resolver la restricción de WhatsApp Business sobre mensajes iniciados por el negocio (sección 03).

También aparece la necesidad de un **sitio web propio** (Centro de Control).

Ejes: proactividad real · memoria persistente estructurada · personalidad configurable · Centro de Control web.

---

## 01 · Decisiones técnicas: mejor opción vs. económica

| # | Decisión | Mejor opción (sin mirar costo) | Alternativa económica | Elegido hasta ahora |
|---|---|---|---|---|
| 01 | Modelo LLM orquestador | Claude Opus en todo el razonamiento | Enrutado por complejidad: Haiku por defecto, Sonnet para portafolio/análisis | **Económica** (Haiku default + Sonnet para análisis) |
| 02 | Base de datos y memoria | Postgres gestionado HA + Redis | Addon Postgres de Railway | **Mejor**: Neon (Postgres) + Upstash (Redis) |
| 03 | Memoria semántica | Vector DB dedicada (Pinecone/Weaviate) | pgvector en el mismo Postgres | Sin decidir |
| 04 | Cotizaciones multi-asset | Polygon.io premium | Finnhub + Alpha Vantage + CoinGecko | **Económica** (Finnhub + Alpha Vantage; FMP descartado) |
| 05 | Calendario económico | Trading Economics API | Calendario curado a mano (~10-15 indicadores: Fed, CPI, NFP, PIB, IPC Chile) | Sin decidir |
| 06 | Noticias filtradas | Benzinga News API | Finnhub News + filtrado por LLM | Económica (Finnhub, de facto) |
| 07 | Mensajería proactiva WhatsApp | Número WhatsApp Business + plantillas Meta | Seguir con sandbox actual | **Mejor** — código listo (Fase 1.6), falta trámite Meta |
| 08 | Scheduler proactivo | Temporal.io / AWS EventBridge | APScheduler dentro de Flask | Económica (APScheduler, de facto) |
| 09 | Stack Centro de Control | Next.js + FastAPI (Vercel + Railway) | Extender Flask con Jinja2 | Económica (según checklist) |
| 10 | Autenticación del panel | Auth0 / Clerk con MFA | Flask-Login + bcrypt | Sin decidir |
| 11 | Hosting general | Cloud gestionado (AWS/GCP) con auto-scaling | Todo en Railway | Económica (Railway) |

### Detalle de cada decisión

**Grupo A — Inteligencia y memoria**
- **01 Modelo LLM.** Mejor: Opus en todo — más calidad de análisis y matices de personalidad, costo por token alto (sube con cada mensaje proactivo). Económica: Haiku por defecto, Sonnet solo para portafolio/económicos — la mayoría de los mensajes no necesita el modelo caro.
- **02 Base de datos.** Mejor: Postgres HA + Redis (backups, réplicas, Redis acelera lecturas frecuentes). Económica: addon Postgres de Railway, suficiente para pocos usuarios.
- **03 Memoria semántica.** Mejor: vector DB dedicada (recall semántico robusto de preferencias dichas en lenguaje libre). Económica: pgvector en el mismo Postgres, gratis y suficiente a esta escala.

**Grupo B — Datos financieros**
- **04 Cotizaciones.** Mejor: Polygon.io (incluye bonos y opciones, un solo proveedor). Económica: Finnhub + Alpha Vantage + CoinGecko (falta buena cobertura de bonos).
- **05 Calendario económico.** Mejor: Trading Economics (consenso + dato anterior, global). Económica: tabla propia curada a mano con calendarios oficiales gratuitos.
- **06 Noticias.** Mejor: Benzinga (etiquetas por ticker/sector/país + sentiment). Económica: Finnhub News + el LLM decide relevancia según preferencias del usuario.

**Grupo C — Entrega proactiva**
- **07 Mensajería proactiva.** Mejor: número WhatsApp Business + plantillas aprobadas por Meta (única forma confiable de avisar fuera de la ventana de 24h). Económica: sandbox actual — es un parche, no cumple el requisito.
- **08 Scheduler.** Mejor: orquestador durable (Temporal / EventBridge). Económica: APScheduler en el proceso Flask — riesgo de perder triggers si el proceso se reinicia.

**Grupo D — Centro de Control**
- **09 Stack web.** Mejor: Next.js + FastAPI. Económica: extender Flask con Jinja2.
- **10 Auth.** Mejor: Auth0/Clerk con MFA. Económica: Flask-Login + bcrypt.
- **11 Hosting.** Mejor: servicios separados en AWS/GCP. Económica: todo en Railway.

---

## 02 · Modelo de datos ampliado

| Tabla | Función | Para qué | Columnas clave | ¿Existe en código? |
|---|---|---|---|---|
| `users` | base | Identifica usuario por WhatsApp | phone, name, timezone, created_at | ✅ Fase 0 |
| `personality_settings` | base | Cómo habla el agente con cada usuario | user_id, humor, sarcasmo, frec_chistes, nivel_conversador, tono | ❌ |
| `notification_schedules` | base | Horarios/frecuencia autorizados para avisar | user_id, tipo_alerta, dias, hora_inicio, hora_fin | ❌ |
| `conversation_history` | base | Memoria de corto plazo | user_id, role, content, timestamp | ✅ Fase 0 |
| `watchlist_items` | mercados | Activos seguidos | user_id, symbol, asset_type, notify_open, notify_close | ✅ Fase 1 (código) |
| `portfolio_holdings` | portafolio | Posiciones del usuario | user_id, symbol, quantity, avg_price, purchase_date | ✅ Fase 1 (código) |
| `news_topics_followed` | noticias | Temas/empresas/países de interés | user_id, tipo, valor | ❌ |
| `economic_indicators_followed` | económicos | Indicadores macro seguidos | user_id, indicator_code, country | ❌ |
| `transactions` | finanzas | Gastos e ingresos por chat | user_id, amount, category, date, description | ❌ |
| `budget_categories` | finanzas | Categorías de gasto | user_id, name, is_default | ❌ |
| `alerts_log` | proactividad | Evitar alertas duplicadas | user_id, alert_type, ref_id, sent_at | ⚠️ Parcial: hoy se usa JSON (`alert_state.json`, `watchlist_alert_state.json`) |

---

## 03 · La restricción de WhatsApp que hay que resolver

> **WhatsApp Business solo permite texto libre dentro de una ventana de 24 horas** desde el
> último mensaje del usuario. Un mensaje que el agente inicia por su cuenta fuera de esa
> ventana **debe usar una plantilla pre-aprobada por Meta**.

Implica: (1) registrar y aprobar plantillas para cada tipo de alerta proactiva, y
(2) la aprobación de Meta tarda días → arrancar el trámite en paralelo cuanto antes.
Textos listos en `05_WHATSAPP_TEMPLATES_TWILIO.md`.

---

## 04 · Plan paso a paso por fases (9 fases)

Cada fase tiene un entregable probable de punta a punta antes de pasar a la siguiente.
El checklist con verificaciones por paso está en `02_CHECKLIST_CONSTRUCCION_POR_FASE.md`.

### Fase 0 — Cimientos: base de datos y orquestador
Objetivo: patrón agente-con-tools funcionando de punta a punta con una sola función.
- Elegir y provisionar la base de datos (decisión 02); tablas `users`, `conversation_history`.
- Elegir el modelo LLM (decisión 01) y cargar la API key en Railway.
- Reemplazar el router de comandos por un orquestador con tool-calling (tool de mercados).
- Iniciar en paralelo el trámite de plantillas de WhatsApp.

### Fase 1 — Memoria y personalidad
Objetivo: el agente recuerda la conversación y habla con estilo propio, sin bajar la calidad del análisis.
- Guardar/recuperar `conversation_history` en cada turno.
- Crear `personality_settings` e inyectarlo en el system prompt (humor, sarcasmo, chistes, nivel conversador, tono).
- Reforzar que la personalidad **nunca** baja el rigor del análisis.
- Centro de Control mínimo: login + perfil + personalidad.

### Fase 2 — Mercados y cotizaciones con contexto (Función 3)
Objetivo: actualizaciones automáticas en apertura/cierre que explican el "por qué".
- Resolver mensajería proactiva (decisión 07) — requisito duro.
- Scheduler proactivo (decisión 08) por timezone y horario, con `watchlist_items`.
- Tool precio + variación + noticia relacionada para explicar el movimiento.
- Alertas en apertura, cierre y horarios custom, respetando feriados.

### Fase 3 — Portafolio (Función 2)
Objetivo: análisis anclado a las posiciones reales, nunca genérico.
- Tools de alta/edición/baja vía chat con `portfolio_holdings`.
- Valor actual, rentabilidad absoluta y %, P&L por posición y total, distribución/exposición.
- Cruzar posiciones con noticias y riesgos/oportunidades (portafolio como contexto obligatorio).
- Centro de Control: módulo de portafolio.

### Fase 4 — Noticias y datos económicos (Función 1)
Objetivo: pre-aviso y post-publicación de datos económicos, resúmenes personalizados.
- `news_topics_followed` y `economic_indicators_followed` + edición en el panel.
- Calendario económico (decisión 05): pre-aviso con dato, fecha, anterior, consenso, relevancia, escenarios.
- Post-publicación: resultado real vs. expectativa, interpretación, impacto.
- Resúmenes diarios/semanales personalizados.

### Fase 5 — Finanzas personales y presupuesto (Función 4)
Objetivo: registrar gastos hablando normal y ver el mes de un vistazo.
- Extracción estructurada (monto, fecha, descripción, categoría) → `transactions`.
- Categorías iniciales propuestas: Vivienda, Alimentación, Transporte, Ocio, Salud, Educación, Otros.
- Resumen mensual automático + consulta on-demand.

### Fase 6 — Control de ruido
Objetivo: avisar lo importante, no todo.
- `alerts_log` para no repetir alertas.
- Umbral de materialidad configurable.
- Cruzar frecuencia con `notification_schedules` y "qué tan conversador" pidió ser el usuario.

### Fase 7 — Centro de Control completo
Objetivo: administrar todo sin tocar la base de datos a mano.
- Confirmar stack (09) y auth (10).
- Módulos: perfil, personalidad, horarios, noticias, indicadores, mercados seguidos, portafolio, finanzas, reportes.
- Cada cambio del panel se refleja de inmediato en el agente.

### Fase 8 — Hardening y uso real
Objetivo: aguantar el uso diario sin sorpresas.
- Errores robustos, reintentos, logging/observabilidad de envíos proactivos.
- Aislamiento de datos por usuario, manejo seguro de secrets.
- Confirmar hosting (11) según uso real.
- Semana de prueba real y ajuste fino de prompts, umbrales y plantillas.

---

## 05 · Riesgos y notas

- Aprobación de plantillas Meta: días, no minutos.
- El costo del LLM sube con más proactividad.
- Licencias de datos económicos/noticias — revisar ToS.
- Categorías de gasto: propuesta inicial, no definitiva.

El mayor riesgo no es técnico sino de plataforma: sin la decisión 07 resuelta, la
proactividad no es posible tal como está planteada.

## 06 · Antes de tocar código (pendientes de decisión)

- [ ] Elegir mejor/económica para cada decisión aún abierta (03, 05, 10).
- [ ] Trámite de WhatsApp Business + plantillas (en curso).
- [ ] Confirmar el set inicial de categorías de presupuesto (Fase 5).
