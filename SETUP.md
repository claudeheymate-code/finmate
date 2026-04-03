# Finmate — Guía de Setup

Bot financiero informativo para WhatsApp. Envía resúmenes semanales y alertas en tiempo real sobre mercados, earnings y datos macroeconómicos.

## Requisitos

- Python 3.11+
- Cuenta de Twilio (gratis para empezar)
- Al menos una API key financiera (Finnhub recomendado)
- Cuenta de Google Cloud (para Calendar, opcional)

---

## Paso 1: API Keys Financieras (5 min)

Necesitas al menos **una** de estas. Recomiendo las tres para mejor cobertura.

### Finnhub (principal — noticias, earnings, macro)
1. Ve a https://finnhub.io/register
2. Crea cuenta gratuita
3. Copia tu API key desde el dashboard
4. Free tier: 60 requests/minuto

### Financial Modeling Prep (índices, movers)
1. Ve a https://site.financialmodelingprep.com/developer
2. Crea cuenta gratuita
3. Copia tu API key
4. Free tier: 250 requests/día

### Alpha Vantage (datos macro EE.UU.)
1. Ve a https://www.alphavantage.co/support/#api-key
2. Solicita una API key gratuita
3. Free tier: 25 requests/día

---

## Paso 2: Twilio para WhatsApp (10 min)

1. Crea cuenta en https://www.twilio.com/try-twilio
2. Ve a **Messaging > Try it Out > Send a WhatsApp message**
3. Sigue las instrucciones para activar el **Sandbox de WhatsApp**:
   - Envía el código que te dan a `+1 415 523 8886` desde tu WhatsApp
   - Esto conecta tu número al sandbox
4. Copia tu `Account SID` y `Auth Token` desde el dashboard
5. **Para producción** (después del sandbox):
   - Solicita un número de WhatsApp Business en Twilio
   - Configura las plantillas de mensajes

### Configurar el Webhook
Una vez deployes en Railway, configura la URL del webhook en Twilio:
- Ve a **Messaging > Settings > WhatsApp Sandbox Settings**
- En "When a message comes in": `https://TU-APP.railway.app/whatsapp/webhook`
- Método: POST

---

## Paso 3: Google Calendar (opcional, 10 min)

1. Ve a https://console.cloud.google.com
2. Crea un proyecto nuevo (o usa uno existente)
3. Habilita la **Google Calendar API**
4. Ve a **Credenciales > Crear credenciales > ID de cliente OAuth**
5. Tipo: "Aplicación de escritorio"
6. Descarga el archivo JSON y renómbralo como `credentials.json`
7. Colócalo en la raíz del proyecto
8. La primera vez que corras el bot, se abrirá un navegador para autorizar

---

## Paso 4: Configurar variables de entorno

Copia `.env.example` a `.env` y completa los valores:

```bash
cp .env.example .env
```

Edita `.env` con tus credenciales reales.

---

## Paso 5: Instalar y correr localmente

```bash
# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -r requirements.txt

# Correr
python main.py
```

El bot estará corriendo en `http://localhost:5000`.

---

## Paso 6: Deploy en Railway

1. Sube el proyecto a un repo de GitHub
2. Ve a https://railway.com y crea cuenta
3. **New Project > Deploy from GitHub repo**
4. Selecciona tu repo de Finmate
5. En **Variables**, agrega todas las de tu `.env`
6. Railway detectará automáticamente el `Procfile` y hará deploy
7. Copia la URL pública y configúrala como webhook en Twilio (Paso 2)

---

## Cómo funciona

### Resumen Semanal (automático)
- Se envía cada **domingo a las 20:00** (configurable)
- Incluye: índices, noticias top, earnings, datos macro
- También actualiza Google Calendar con los eventos de la semana siguiente

### Alertas en Tiempo Real (automático)
- Se chequean cada **30 minutos** (configurable)
- Detecta: earnings publicados, datos macro publicados, noticias relevantes
- Solo notifica novedades (no repite alertas)

### Comandos por WhatsApp (interactivo)
Envía estos mensajes al bot:
- `hola` — Saludo y bienvenida
- `resumen` — Resumen semanal bajo demanda
- `mercados` — Estado actual de índices
- `ayuda` — Lista de comandos

---

## Arquitectura

```
Finmate/
├── main.py              # App principal + scheduler
├── wsgi.py              # Entry point para Gunicorn
├── config/
│   └── settings.py      # Variables de entorno
├── finmate/
│   ├── data_sources/    # Clientes de APIs financieras
│   │   ├── finnhub_client.py
│   │   ├── fmp_client.py
│   │   ├── alpha_vantage_client.py
│   │   └── aggregator.py
│   ├── whatsapp/        # Mensajería + webhook
│   │   ├── messenger.py
│   │   ├── formatter.py
│   │   └── webhook.py
│   ├── calendar/        # Google Calendar
│   │   └── gcal_client.py
│   └── alerts/          # Motor de alertas
│       └── engine.py
├── requirements.txt
├── Procfile             # Deploy (Railway/Heroku)
├── railway.json         # Config de Railway
└── .env.example         # Plantilla de variables
```

---

## Notas importantes

- **No emite recomendaciones de inversión** — Solo informa e interpreta datos
- **Sandbox de Twilio** — El sandbox expira después de 3 días de inactividad; para uso permanente necesitas un número WhatsApp Business aprobado
- **Rate limits** — Las APIs gratuitas tienen límites; el bot está diseñado para respetarlos
- **Google Calendar** — Es opcional; el bot funciona perfectamente solo con WhatsApp
