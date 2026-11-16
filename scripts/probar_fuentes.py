"""
Finmate - Prueba de las fuentes con las claves REALES, antes de desplegar.

Uso (desde la carpeta del proyecto, en PowerShell):
    py scripts\\probar_fuentes.py

Lee las claves del archivo .env (el mismo formato que .env.example). Nunca
imprime las claves: solo dice si cada fuente respondió bien y muestra un
dato de ejemplo. No manda WhatsApp ni escribe en la base de datos.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

import httpx  # noqa: E402

OK, FAIL, SKIP = "✅", "❌", "⏭️"
results = []


_SECRET_VARS = ("FINNHUB_API_KEY", "FRED_API_KEY", "BCCH_API_TOKEN", "MARKETAUX_API_KEY",
                "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "REDIS_URL", "DATABASE_URL",
                "TWILIO_AUTH_TOKEN", "FLASK_SECRET_KEY")


def _redact(text: str) -> str:
    """Nunca mostrar una clave, ni siquiera dentro de un mensaje de error."""
    import re
    for var in _SECRET_VARS:
        val = os.getenv(var, "").strip().strip('"')
        if len(val) >= 6:
            text = text.replace(val, "<clave>")
    return re.sub(r"(token|api_key|api_token)=[^&\s']+", r"\1=<clave>", text)


def check(name, fn):
    try:
        status, detail = fn()
    except Exception as e:  # noqa: BLE001
        status, detail = FAIL, f"{type(e).__name__}: {e}"
    detail = _redact(str(detail))[:300]
    results.append((status, name, detail))
    print(f"{status} {name}: {detail}", flush=True)


def has(var):
    return bool(os.getenv(var, "").strip())


def finnhub_rest():
    if not has("FINNHUB_API_KEY"):
        return SKIP, "falta FINNHUB_API_KEY"
    r = httpx.get("https://finnhub.io/api/v1/quote", params={"symbol": "AAPL", "token": os.getenv("FINNHUB_API_KEY")}, timeout=10)
    r.raise_for_status()
    d = r.json()
    return (OK, f"AAPL ${d.get('c')} ({d.get('dp')}%)") if d.get("c") else (FAIL, f"respuesta vacía {d}")


def finnhub_ws():
    if not has("FINNHUB_API_KEY"):
        return SKIP, "falta FINNHUB_API_KEY"
    import websocket
    ws = websocket.create_connection(f"wss://ws.finnhub.io?token={os.getenv('FINNHUB_API_KEY')}", timeout=10)
    ws.send(json.dumps({"type": "subscribe", "symbol": "AAPL"}))
    ws.send(json.dumps({"type": "subscribe", "symbol": "BINANCE:BTCUSDT"}))  # cripto opera 24/7
    end = time.time() + 15
    kinds = set()
    while time.time() < end:
        try:
            msg = json.loads(ws.recv())
        except Exception:
            break
        kinds.add(msg.get("type"))
        if msg.get("type") == "trade":
            ws.close()
            t = msg["data"][0]
            return OK, f"conectado, operación en vivo {t['s']} ${t['p']}"
    ws.close()
    return (OK if "ping" in kinds else FAIL), f"conectado, sin operaciones en 15 s (mensajes: {sorted(k for k in kinds if k) or 'ninguno'})"


def fred():
    from finmate.data_sources import fred as f
    if not f.is_configured():
        return SKIP, "falta FRED_API_KEY"
    data = f.get_snapshot()
    if not data:
        return FAIL, "no devolvió datos"
    rel = f.get_upcoming_releases(days_ahead=14)
    return OK, f"{len(data)}/{len(f.SERIES)} series (ej: {data[0]['label']} {data[0]['value']}); {len(rel)} publicaciones en 14 días"


def bcch():
    from finmate.data_sources import bcch as b
    if not b.is_configured():
        return SKIP, "falta BCCH_API_TOKEN"
    data = b.get_snapshot()
    got = {d["code"] for d in data}
    missing = [c for c in b.SERIES if c not in got]
    sample = ", ".join(f"{d['code']}={d['value']}" for d in data)
    if not data:
        return FAIL, "no devolvió datos (¿token activado en la BDE?)"
    return (OK if not missing else FAIL), sample + (f" | sin datos: {missing}" if missing else "")


def marketaux():
    from finmate.data_sources import marketaux as m
    if not m.is_configured():
        return SKIP, "falta MARKETAUX_API_KEY"
    news = m.get_news(["AAPL", "NVDA", "MSFT"], force=True)
    return OK, f"{len(news)} noticias (consume 1 de las 100 consultas del día)"


def anthropic_check():
    if not has("ANTHROPIC_API_KEY"):
        return SKIP, "falta ANTHROPIC_API_KEY"
    import anthropic
    from config.settings import ANTHROPIC_MODEL_DEFAULT
    c = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    r = c.messages.create(model=ANTHROPIC_MODEL_DEFAULT, max_tokens=10, messages=[{"role": "user", "content": "Responde solo: ok"}])
    return OK, f"modelo {ANTHROPIC_MODEL_DEFAULT} respondió '{r.content[0].text.strip()}'"


def openai_check():
    if not has("OPENAI_API_KEY"):
        return SKIP, "falta OPENAI_API_KEY (opcional)"
    r = httpx.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"}, timeout=10)
    if r.status_code == 200:
        return OK, "clave válida (el saldo se ve en Billing; sin saldo la transcripción falla y se usa la descripción)"
    return FAIL, f"HTTP {r.status_code}"


def podcast():
    from finmate.podcasts.catalog import PODCASTS
    from finmate.podcasts.digest import fetch_feed
    eps = fetch_feed(PODCASTS["primer_click"]["rss"])
    return OK, f"último episodio: {eps[0]['title']}"


def redis_check():
    if not has("REDIS_URL"):
        return SKIP, "falta REDIS_URL"
    import redis
    from config.settings import REDIS_URL
    c = redis.from_url(REDIS_URL, socket_timeout=5)
    c.set("finmate:prueba", "1", ex=10)
    return OK, "conexión y escritura OK"


def database():
    if not has("DATABASE_URL"):
        return SKIP, "falta DATABASE_URL"
    from sqlalchemy import create_engine, inspect
    from config.settings import DATABASE_URL
    tables = inspect(create_engine(DATABASE_URL)).get_table_names()
    return OK, f"{len(tables)} tablas"


if __name__ == "__main__":
    print("Probando fuentes de Finmate con las claves del .env...\n")
    check("Finnhub (cotizaciones)", finnhub_rest)
    check("Finnhub (precios en tiempo real)", finnhub_ws)
    check("FRED (macro EE.UU.)", fred)
    check("Banco Central de Chile", bcch)
    check("Marketaux (noticias)", marketaux)
    check("Primer Click (RSS)", podcast)
    check("Claude (Anthropic)", anthropic_check)
    check("OpenAI (transcripción)", openai_check)
    check("Redis (Upstash)", redis_check)
    check("Postgres (Neon)", database)
    fails = [r for r in results if r[0] == FAIL]
    print(f"\n{len(results) - len(fails)}/{len(results)} sin errores.")
    sys.exit(1 if fails else 0)
