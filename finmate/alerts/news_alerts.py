"""
Finmate - Alertas de noticias por usuario (Etapa A de fuentes, 16 nov 2026).

Cada NEWS_CHECK_INTERVAL_MINUTES (default 3) junta los símbolos del
portafolio y la watchlist de cada usuario, busca noticias nuevas en Finnhub
(REST, cada corrida) y Marketaux (en lote, como máximo cada
MARKETAUX_MIN_INTERVAL_MINUTES por el límite de 100 req/día del plan
gratis), elimina duplicados entre fuentes y le manda a cada usuario un solo
mensaje con las noticias de SUS activos.

Reglas para no saturar:
- Solo noticias publicadas en los últimos FRESH_MINUTES.
- La primera corrida (sin estado previo) solo "calienta": marca todo como
  visto sin enviar, para no mandar una avalancha al desplegar.
- Máximo NEWS_ALERTS_MAX_PER_USER_PER_DAY mensajes por usuario por día y
  MAX_ITEMS_PER_MESSAGE titulares por mensaje.

Igual que las alertas de watchlist, corre como job separado en main.py: un
error aquí nunca toca el resto de las alertas.
"""
import datetime as dt
import hashlib
import json
import logging
import os
import re
from collections import defaultdict
from typing import Callable, Optional

import httpx

from config.settings import (
    FINNHUB_API_KEY,
    NEWS_ALERTS_MAX_PER_USER_PER_DAY,
    TEMPLATE_MARKET_NOTIFY,
)
from finmate.data_sources import marketaux

logger = logging.getLogger(__name__)

STATE_FILE = "news_alert_state.json"
FRESH_MINUTES = 90
MAX_ITEMS_PER_MESSAGE = 3
MAX_SEEN = 5000
FINNHUB_URL = "https://finnhub.io/api/v1"

_company_names: dict = {}


def _load_state() -> dict:
    from finmate.db.state_store import load_json

    return load_json(STATE_FILE, {})


def _save_state(state: dict, today: str = None) -> None:
    try:
        seen = state.get("seen", {})
        if len(seen) > MAX_SEEN:
            for k in list(seen.keys())[: len(seen) - MAX_SEEN]:
                del seen[k]
        today = today or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        state["daily"] = {k: v for k, v in state.get("daily", {}).items() if k.endswith(today)}
        from finmate.db.state_store import save_json

        save_json(STATE_FILE, state)
    except Exception as e:
        logger.error(f"Error guardando estado de alertas de noticias: {e}")


def _key(item: dict) -> str:
    """Clave de duplicado: titular normalizado (la misma noticia llega por
    Finnhub y Marketaux con URLs distintas)."""
    norm = re.sub(r"[^a-z0-9]+", "", (item.get("headline") or "").lower())[:90]
    return hashlib.sha1(f"{item.get('symbol')}|{norm}".encode()).hexdigest()[:16]


def _parse_time(value) -> Optional[dt.datetime]:
    if isinstance(value, (int, float)) and value > 0:
        return dt.datetime.fromtimestamp(value, dt.timezone.utc)
    if isinstance(value, str) and value:
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _company_name(client: httpx.Client, symbol: str) -> str:
    if symbol in _company_names:
        return _company_names[symbol]
    name = ""
    try:
        r = client.get(f"{FINNHUB_URL}/stock/profile2", params={"symbol": symbol, "token": FINNHUB_API_KEY})
        r.raise_for_status()
        name = (r.json() or {}).get("name", "") or ""
        # "Apple Inc" -> "apple": la primera palabra alcanza para filtrar.
        name = name.split(" ")[0].strip(",.").lower() if name else ""
    except Exception as e:
        logger.debug(f"No pude obtener el nombre de {symbol}: {e}")
    _company_names[symbol] = name
    return name


def fetch_finnhub_news(symbols, now: dt.datetime) -> list:
    if not FINNHUB_API_KEY:
        return []
    out = []
    frm = (now - dt.timedelta(days=1)).date().isoformat()
    to = now.date().isoformat()
    with httpx.Client(timeout=10) as client:
        for sym in sorted(set(symbols)):
            try:
                r = client.get(f"{FINNHUB_URL}/company-news",
                               params={"symbol": sym, "from": frm, "to": to, "token": FINNHUB_API_KEY})
                r.raise_for_status()
                items = r.json() or []
            except Exception as e:
                logger.error(f"Error noticias Finnhub {sym}: {e}")
                continue
            keys = {sym.lower()}
            name = _company_name(client, sym)
            if name and len(name) > 2:
                keys.add(name)
            for it in items:
                text = f"{it.get('headline', '')} {it.get('summary', '')}".lower()
                if not any(k in text for k in keys):
                    continue
                out.append({
                    "symbol": sym,
                    "headline": it.get("headline") or "",
                    "summary": it.get("summary") or "",
                    "url": it.get("url") or "",
                    "source": it.get("source") or "Finnhub",
                    "datetime": it.get("datetime"),
                    "sentiment": None,
                })
    return out


def _format_message(items: list) -> str:
    lines = ["📰 *Noticias de tus activos*", ""]
    for it in items:
        s = it.get("sentiment")
        mood = ""
        if isinstance(s, (int, float)):
            mood = " 🟢" if s >= 0.3 else (" 🔴" if s <= -0.3 else "")
        lines.append(f"*{it['symbol']}*{mood} — {it['headline'].strip()}")
        if it.get("url"):
            lines.append(it["url"])
        lines.append("")
    lines.append("_Escribime \"¿por qué se movió " + items[0]["symbol"] + "?\" si quieres el análisis._")
    return "\n".join(lines).strip()


def check_news_alerts(
    messenger=None,
    tracked: Optional[list] = None,
    finnhub_fetch: Callable = fetch_finnhub_news,
    marketaux_fetch: Callable = marketaux.get_news,
    now: Optional[dt.datetime] = None,
) -> int:
    """Busca noticias nuevas y avisa a cada usuario. Devuelve cuántos
    mensajes se enviaron. Los parámetros opcionales existen para los tests."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if tracked is None:
        from finmate.db.repository import get_all_tracked_symbols
        tracked = get_all_tracked_symbols()
    if not tracked:
        return 0

    by_symbol = defaultdict(list)
    for user_id, phone, symbol in tracked:
        by_symbol[symbol.upper()].append((user_id, phone))
    symbols = list(by_symbol)

    items = list(finnhub_fetch(symbols, now))
    after = (now - dt.timedelta(minutes=FRESH_MINUTES)).strftime("%Y-%m-%dT%H:%M")
    items += list(marketaux_fetch(symbols, published_after=after))

    state = _load_state()
    warmup = "seen" not in state
    seen = state.setdefault("seen", {})
    daily = state.setdefault("daily", {})
    today = now.strftime("%Y-%m-%d")
    cutoff = now - dt.timedelta(minutes=FRESH_MINUTES)

    per_user = defaultdict(list)
    phones = {}
    for it in items:
        k = _key(it)
        if k in seen:
            continue
        seen[k] = now.isoformat()
        published = _parse_time(it.get("datetime"))
        if warmup or published is None or published < cutoff:
            continue
        for user_id, phone in by_symbol.get(it["symbol"], []):
            per_user[user_id].append(it)
            phones[user_id] = phone

    sent = 0
    if per_user:
        if messenger is None:
            from finmate.whatsapp.messenger import WhatsAppMessenger
            messenger = WhatsAppMessenger()
        for user_id, user_items in per_user.items():
            dkey = f"{user_id}_{today}"
            if daily.get(dkey, 0) >= NEWS_ALERTS_MAX_PER_USER_PER_DAY:
                continue
            # Primero las de sentimiento más marcado (si lo hay).
            user_items.sort(key=lambda x: -abs(x.get("sentiment") or 0))
            msg = _format_message(user_items[:MAX_ITEMS_PER_MESSAGE])
            phone = phones[user_id]
            try:
                if TEMPLATE_MARKET_NOTIFY:
                    from finmate.alerts.pending import queue_pending
                    queue_pending(phone, msg)
                    ok = messenger.send_template(phone, TEMPLATE_MARKET_NOTIFY,
                                                 {"1": "Noticias de tus activos"})
                else:
                    ok = messenger.send_message(phone, msg)
            except Exception as e:
                logger.error(f"Error enviando noticias a {phone}: {e}")
                ok = False
            if ok:
                daily[dkey] = daily.get(dkey, 0) + 1
                sent += 1

    _save_state(state, today)
    logger.info(f"Chequeo de noticias: {len(items)} revisadas, {sent} mensajes enviados"
                + (" (corrida de calentamiento)" if warmup else ""))
    return sent
