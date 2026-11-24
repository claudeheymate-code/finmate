"""
Finmate - Resumen diario de podcasts (Etapa C).

Spotify no entrega el contenido de los episodios por su API, así que se usa
el feed RSS público del podcast (el mismo que alimenta a Spotify y Apple):

1. Revisa el feed y detecta un episodio nuevo (de las últimas 24 h).
2. Si hay OPENAI_API_KEY, descarga el audio y lo transcribe
   (~USD 0,003/min con gpt-4o-mini-transcribe: unos USD 0,05 por episodio de
   15 min). Sin esa clave, usa la descripción del episodio.
3. Claude (modelo económico) lo resume en 5-6 puntos para inversionistas.
4. Lo manda por WhatsApp a quienes siguen el podcast (tool follow_podcast)
   (cada usuario lo activa por chat o desde su panel), con el link al episodio.

El resumen es corto y en palabras propias (no reproduce la transcripción),
y siempre enlaza al episodio original.
"""
import datetime as dt
import email.utils
import html
import logging
import re
import xml.etree.ElementTree as ET
from typing import Optional

import httpx

from config.settings import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL_DEFAULT,
    OPENAI_API_KEY,
    TRANSCRIBE_MODEL,
    TEMPLATE_MARKET_NOTIFY,
)
from finmate.podcasts.catalog import PODCASTS

logger = logging.getLogger(__name__)

STATE_FILE = "podcast_state.json"
MAX_AUDIO_BYTES = 24 * 1024 * 1024  # límite de OpenAI: 25 MB por archivo
MAX_TRANSCRIPT_CHARS = 30000
ITUNES_NS = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def _load_state() -> dict:
    from finmate.db.state_store import load_json

    return load_json(STATE_FILE, {})


def _save_state(state: dict) -> None:
    try:
        for pid in list(state):
            seen = state[pid].get("seen", [])
            state[pid]["seen"] = seen[-50:]
        from finmate.db.state_store import save_json

        save_json(STATE_FILE, state)
    except Exception as e:
        logger.error(f"Error guardando estado de podcasts: {e}")


def _clean_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>|</p>", "\n", text or "", flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(text)).strip()


def parse_feed(xml_text: str) -> list:
    """Episodios del feed, del más nuevo al más viejo:
    [{"guid","title","published","description","audio_url","audio_bytes","link","duration"}]."""
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    out = []
    for it in (channel.findall("item") if channel is not None else []):
        enc = it.find("enclosure")
        try:
            published = email.utils.parsedate_to_datetime(it.findtext("pubDate") or "")
        except (TypeError, ValueError):
            published = None
        out.append({
            "guid": (it.findtext("guid") or it.findtext("title") or "").strip(),
            "title": (it.findtext("title") or "").strip(),
            "published": published,
            "description": _clean_html(it.findtext("description") or ""),
            "audio_url": enc.attrib.get("url") if enc is not None else None,
            "audio_bytes": int(enc.attrib.get("length") or 0) if enc is not None else 0,
            "link": (it.findtext("link") or "").strip(),
            "duration": it.findtext(f"{ITUNES_NS}duration") or "",
        })
    out.sort(key=lambda e: e["published"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
    return out


def fetch_feed(rss_url: str) -> list:
    r = httpx.get(rss_url, timeout=20, follow_redirects=True)
    r.raise_for_status()
    return parse_feed(r.text)


def pick_new_episode(episodes: list, seen: list, skip_prefixes: list,
                     now: Optional[dt.datetime] = None) -> Optional[dict]:
    now = now or dt.datetime.now(dt.timezone.utc)
    for ep in episodes:
        if not ep["published"] or now - ep["published"] > dt.timedelta(hours=24):
            continue
        if ep["guid"] in seen:
            continue
        if any(ep["title"].startswith(p) for p in skip_prefixes):
            continue
        return ep
    return None


def transcribe(episode: dict) -> Optional[str]:
    """Transcripción con OpenAI, o None si no hay clave o el audio es muy grande."""
    if not OPENAI_API_KEY or not episode.get("audio_url"):
        return None
    if episode.get("audio_bytes", 0) > MAX_AUDIO_BYTES:
        logger.info(f"Audio de '{episode['title']}' supera 24 MB; uso la descripción")
        return None
    try:
        audio = httpx.get(episode["audio_url"], timeout=120, follow_redirects=True)
        audio.raise_for_status()
        if len(audio.content) > MAX_AUDIO_BYTES:
            return None
        r = httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            data={"model": TRANSCRIBE_MODEL, "language": "es", "response_format": "json"},
            files={"file": ("episodio.mp3", audio.content, "audio/mpeg")},
            timeout=300,
        )
        r.raise_for_status()
        return (r.json() or {}).get("text") or None
    except Exception as e:
        logger.error(f"Error transcribiendo '{episode.get('title')}': {e}")
        return None


_PROMPT = """Eres Finmate, un asistente financiero que escribe por WhatsApp a un inversionista chileno.
Resume este episodio del podcast "{podcast}" en 5 o 6 viñetas breves (máximo 25 palabras cada una).
Prioriza lo que mueve mercados: tasas, dólar, acciones o sectores mencionados, datos económicos y su posible impacto.
Escribe en tus propias palabras, sin citar frases textuales largas. No inventes datos que no estén en el material.
Responde solo con las viñetas, cada una empezando con "• ".

Título: {title}
Descripción: {description}
{transcript_block}"""


def summarize(podcast_name: str, episode: dict, transcript: Optional[str], client=None) -> str:
    """Viñetas con Claude; si no hay clave de Anthropic, la descripción limpia."""
    if client is None and ANTHROPIC_API_KEY:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    if client is None:
        return episode.get("description") or ""
    block = f"Transcripción:\n{transcript[:MAX_TRANSCRIPT_CHARS]}" if transcript else \
        "(Sin transcripción: resume a partir de la descripción, sin agregar detalles que no estén ahí.)"
    try:
        resp = client.messages.create(
            model=ANTHROPIC_MODEL_DEFAULT,
            max_tokens=600,
            messages=[{"role": "user", "content": _PROMPT.format(
                podcast=podcast_name, title=episode["title"],
                description=episode.get("description", ""), transcript_block=block)}],
        )
        text = "".join(getattr(b, "text", "") for b in resp.content).strip()
        return text or episode.get("description") or ""
    except Exception as e:
        logger.error(f"Error resumiendo '{episode['title']}': {e}")
        return episode.get("description") or ""


def format_digest(podcast_name: str, episode: dict, summary: str, transcribed: bool) -> str:
    lines = [f"🎧 *{podcast_name}*", f"_{episode['title']}_", "", summary.strip(), ""]
    if episode.get("link"):
        lines.append(f"Escúchalo: {episode['link']}")
    if not transcribed:
        lines.append("_(Resumen basado en la descripción del episodio.)_")
    return "\n".join(lines).strip()


def _recipients(podcast_id: str) -> list:
    phones = []
    try:
        from finmate.db.news_repo import get_topic_followers
        phones = [p for _uid, p in get_topic_followers("podcast", podcast_id)]
    except Exception as e:
        logger.warning(f"No pude leer seguidores del podcast {podcast_id}: {e}")
    return phones


def check_podcast_digests(messenger=None, now: Optional[dt.datetime] = None,
                          feed_fn=fetch_feed, transcribe_fn=transcribe,
                          summarize_fn=summarize, recipients_fn=_recipients) -> int:
    """Revisa cada podcast del catálogo y manda el resumen del episodio nuevo.
    Devuelve cuántos mensajes se enviaron."""
    state = _load_state()
    sent = 0
    for pid, meta in PODCASTS.items():
        pstate = state.setdefault(pid, {"seen": []})
        try:
            episodes = feed_fn(meta["rss"])
        except Exception as e:
            logger.error(f"No pude leer el feed de {meta['name']}: {e}")
            continue
        ep = pick_new_episode(episodes, pstate["seen"], meta.get("skip_title_prefixes", []), now)
        if ep is None:
            continue
        transcript = transcribe_fn(ep)
        summary = summarize_fn(meta["name"], ep, transcript)
        msg = format_digest(meta["name"], ep, summary, transcribed=bool(transcript))
        pstate["seen"].append(ep["guid"])
        pstate["last"] = {"title": ep["title"], "message": msg,
                          "published": ep["published"].isoformat() if ep["published"] else ""}
        _save_state(state)  # guardar antes de enviar: nunca se resume dos veces

        phones = recipients_fn(pid)
        if phones and messenger is None:
            from finmate.whatsapp.messenger import WhatsAppMessenger
            messenger = WhatsAppMessenger()
        from finmate.services.workday import allow as _workday_allow

        for phone in phones:
            if not _workday_allow(phone, msg, "podcast"):
                continue
            try:
                if TEMPLATE_MARKET_NOTIFY:
                    from finmate.alerts.pending import queue_pending
                    queue_pending(phone, msg)
                    ok = messenger.send_template(phone, TEMPLATE_MARKET_NOTIFY,
                                                 {"1": f"Resumen de {meta['name']}"})
                else:
                    ok = messenger.send_message(phone, msg)
            except Exception as e:
                logger.error(f"Error enviando resumen de podcast a {phone}: {e}")
                ok = False
            sent += 1 if ok else 0
        logger.info(f"Resumen de {meta['name']} enviado a {sent} usuarios: {ep['title']}")
    return sent


def get_last_digest(podcast_id: str) -> Optional[str]:
    return (_load_state().get(podcast_id) or {}).get("last", {}).get("message")
