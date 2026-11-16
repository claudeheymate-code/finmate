# Finmate — Panel web: diseño y conexión con el bot

> 16 nov 2026. Corresponde al "Centro de Control" del plan (Fases 1 y 7).
> Diseño: lienzo "Finmate — Panel de control web" en claude.ai
> (https://claude.ai/artifact/E9Dxi6u4C8pv2mGz768XEx). Marca en `docs/marca/`.

## Marca

| Color | Hex | Uso en el panel |
|---|---|---|
| Azul marino | `#082448` | Base (fondo `#061A36`, un tono más profundo) |
| Verde esmeralda | `#009B77` | Botones principales, barras, acento |
| Gris claro | `#F4F6F8` | Reservado para una versión clara futura |
| Gris pizarra | `#64748B` | Halos de fondo, textos secundarios |
| Blanco | `#FFFFFF` | Texto principal, estado activo del menú |

Para leer bien sobre azul se usan dos tonos derivados: verde claro `#3DDBB0` para subidas y
ámbar `#FFB37A` para bajadas (siempre con flecha, no solo color). Tipografías: Outfit
(títulos y números, parecida al wordmark) e Inter (texto). Estilo "glass": tarjetas
translúcidas con desenfoque sobre fondo azul con halos verde y azul.

## Pantallas

1. **Acceso** — entrar con el número de WhatsApp; el código llega por el chat de Finmate.
2. **Resumen** — valor del portafolio, ganancia total, gastos del mes, alertas activas,
   activos, últimos mensajes del chat y lo que seguís.
3. **Portafolio y watchlist** — posiciones con ganancia/pérdida, distribución, alta de
   posiciones, watchlist con umbral de alerta y "¿por qué se movió?".
4. **Finanzas personales** — ingresos, gastos, balance, gastos por categoría, movimientos y
   formulario gasto/ingreso.
5. **Ajustes y personalidad** — sliders de humor, sarcasmo, chistes, nivel conversador y tono
   con vista previa; temas e indicadores seguidos; umbral de alertas, resumen semanal y
   WhatsApp vinculado.

Barra superior en todas: "Preguntale a Finmate…" (habla con el mismo agente del bot).

## Cómo se conecta con el bot

**Idea central: el panel y el bot son dos puertas a la misma casa.** Los dos viven en el
mismo servicio de Railway, usan la misma base de datos Neon y las mismas funciones de
`finmate/db/` que ya usan las 20 tools. No hay sincronización que mantener: si agregás una
posición en la web, el bot la ve en el próximo mensaje, y al revés.

```
WhatsApp ──► Twilio ──► /webhook ─┐
                                   ├─► orquestador (Claude) ─► tools ─► finmate/db/* ─► Neon
Navegador ──► /panel + /api/* ─────┘                                  └─► Finnhub / Alpha Vantage
```

### Stack (decisiones 09, 10 y 11 del plan, opción económica)
- **Mismo Flask** que ya corre el bot: rutas nuevas `/panel/*` (páginas) y `/api/*` (JSON).
  Sin servidor extra → USD 0 adicional en Railway.
- **Frontend**: plantillas Jinja2 + Tailwind (con los colores de marca) + un poco de
  JavaScript para formularios y sliders. Si más adelante crece, se puede pasar a React/Next.js
  sin cambiar la API.
- **Sesión**: cookie firmada de Flask (`HttpOnly`, `Secure`, `SameSite=Lax`), 30 días.

### Acceso sin contraseña (código por WhatsApp)
1. El usuario escribe su número → `POST /api/auth/codigo`.
2. El servidor genera un código de 6 dígitos, guarda su hash en Redis (Upstash) por
   10 minutos y lo manda por WhatsApp con Twilio.
3. El usuario lo ingresa → `POST /api/auth/verificar` → se crea la sesión ligada al
   `users.id` de ese teléfono (el mismo usuario del bot).
4. Límite: 3 códigos cada 15 minutos por número y 5 intentos por código.

Ojo: fuera de la ventana de 24 h, Meta exige plantilla para mandar el código. Hay que crear
una cuarta plantilla, categoría **Authentication** (`finmate_login_code`), cuando exista el
número propio.

### API (cada endpoint reutiliza lo que ya usan las tools)

| Endpoint | Pantalla | Reutiliza |
|---|---|---|
| `GET /api/resumen` | Resumen | portafolio + watchlist + resumen del mes + seguimientos |
| `GET/POST/DELETE /api/portafolio` | Portafolio | `repository.add_or_update_holding`, `remove_holding`, `get_portfolio` |
| `GET/POST/DELETE /api/watchlist` | Portafolio | `repository.add_to_watchlist`, `remove_from_watchlist` |
| `GET /api/mercado/explicar/<símbolo>` | Portafolio | `market_tools.tool_explain_movement` (en JSON) |
| `GET/POST /api/finanzas/movimientos` | Finanzas | `finance_repo.add_transaction`, últimos movimientos |
| `GET /api/finanzas/resumen?anio=&mes=` | Finanzas | `finance_repo.get_monthly_summary` |
| `GET/PUT /api/personalidad` | Ajustes | `personality_repo.get_personality` / `set_personality` |
| `GET/POST/DELETE /api/seguimientos` | Ajustes | `news_repo` (temas e indicadores) |
| `PUT /api/avisos` | Ajustes | **nuevo**: umbral y resumen semanal por usuario |
| `POST /api/chat` | Barra superior | `orchestrator.handle_message` (misma memoria que WhatsApp) |

Cada consulta filtra por el `user_id` de la sesión: nadie puede ver datos de otro.

### Lo que falta en el código para que el panel funcione
1. **Ganancia/pérdida del portafolio** (Plan Fase 3): costo promedio vs precio actual,
   por posición y total, y distribución por sector.
2. **Ajustes de avisos por usuario**: hoy el umbral (`WATCHLIST_ALERT_THRESHOLD_PCT`) y el
   resumen semanal son globales. Tabla nueva `notification_settings` (es la
   `notification_schedules` del plan) y que `watchlist_alerts.py` y `engine.py` la lean.
3. **Fechas reales del calendario económico** (Plan Fase 4); hoy el catálogo no tiene fechas.
4. Las rutas `/panel` y `/api`, el login por código y las plantillas Jinja.
5. Plantilla `finmate_login_code` (Authentication) en Twilio cuando haya número propio.

### Orden sugerido
1. Ganancia/pérdida + `notification_settings` (sirven también al bot).
2. API `/api/*` con tests.
3. Login por código (mientras tanto, en desarrollo se puede entrar con un enlace de un solo
   uso que manda el bot dentro de la ventana de 24 h).
4. Páginas: Resumen → Portafolio → Finanzas → Ajustes.
5. Dominio propio (opcional, ej. `app.finmate.cl`) apuntando a Railway.
