"""Texto para WhatsApp: formato correcto y emojis según el gusto de cada usuario."""

import re
import threading
import time

# ── Formato de WhatsApp ─────────────────────────────────────────────────
# WhatsApp usa *negrita*, _cursiva_ y ~tachado~ con UN símbolo por lado. Claude a veces
# escribe Markdown (**negrita**, ## títulos, [texto](link)) y en WhatsApp quedan los
# asteriscos a la vista. Esto lo convierte antes de mandar cualquier mensaje.

_BOLD_MD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.S)
_UNDER_MD = re.compile(r"(?<![\w_])__(?=\S)(.+?)(?<=\S)__(?![\w_])", re.S)
_STRIKE_MD = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~", re.S)
_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
_HR = re.compile(r"^[ \t]*(-{3,}|\*{3,}|_{3,})[ \t]*$", re.M)


def whatsapp_markup(text: str) -> str:
    if not text:
        return text
    t = _BOLD_MD.sub(lambda m: f"*{m.group(1).strip('*')}*", text)
    t = _UNDER_MD.sub(r"_\1_", t)
    t = _STRIKE_MD.sub(r"~\1~", t)
    t = _HEADING.sub(lambda m: f"*{m.group(1).strip('*')}*", t)
    t = _LINK.sub(lambda m: m.group(1) if m.group(1) == m.group(2) else f"{m.group(1)}: {m.group(2)}", t)
    t = _HR.sub("", t)
    t = re.sub(r"\*{2,}", "*", t)                 # restos de ** sueltos
    return re.sub(r"\n{3,}", "\n\n", t)


# ── Emojis ──────────────────────────────────────────────────────────────
# Rango de pictogramas; deja fuera ▲ ▼ • → y similares (útiles en listas sin emojis).
_EMOJI = re.compile(
    "["
    "\U0001F000-\U0001FAFF"      # emojis, banderas, símbolos
    "☀-➿"              # ☀ ☕ ✅ ✨ ❌ etc.
    "⬀-⯿"              # ⬆ ⬇ ⭐
    "⌀-⏿"              # ⌚ ⏰
    "️‍⃣"         # selectores y uniones
    "]+")
EMOJI_DEFAULT = 4


def strip_emojis(text: str) -> str:
    if not text:
        return text
    t = _EMOJI.sub("", text)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"^[ \t]+(?=\S)", "", t, flags=re.M)      # sangría que dejó un emoji al inicio
    return t.strip()


_cache: dict = {}
_lock = threading.Lock()
_TTL = 60


def emoji_level_for_phone(phone: str) -> int:
    """Nivel de emojis (1-10) del dueño de este número; por defecto 4. Cache de 1 minuto."""
    now = time.time()
    with _lock:
        hit = _cache.get(phone)
        if hit and now - hit[0] < _TTL:
            return hit[1]
    level = EMOJI_DEFAULT
    try:
        from finmate.db.personality_repo import get_personality
        from finmate.db.repository import find_user_by_phone

        user = find_user_by_phone(phone)
        if user is not None:
            level = int(get_personality(user.id).get("emojis") or EMOJI_DEFAULT)
    except Exception:  # noqa: BLE001
        pass
    with _lock:
        _cache[phone] = (now, level)
    return level


def forget_emoji_level(phone: str = None) -> None:
    with _lock:
        if phone:
            _cache.pop(phone, None)
        else:
            _cache.clear()


def prepare_for(phone: str, text: str) -> str:
    """Lo que se aplica a TODO mensaje que sale: formato de WhatsApp y, si el usuario
    eligió 'sin emojis' (1-2), se sacan los emojis."""
    out = whatsapp_markup(text or "")
    if out and emoji_level_for_phone(phone) <= 2:
        out = strip_emojis(out)
    return out
