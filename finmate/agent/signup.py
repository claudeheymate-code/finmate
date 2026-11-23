"""Registro de números nuevos: el bot pide nombre y correo antes de dejar la solicitud en el Inbox.

Se interpreta el texto con reglas simples (sin llamar a Claude): el correo se
detecta con una expresión regular y el nombre es lo que queda después de sacar
el correo y frases como "me llamo" o "mi correo es".
"""
import re
from typing import Optional, Tuple

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

_FILLER = re.compile(
    r"\b(hola|holi|buenas|buenos d[ií]as|buenas tardes|buenas noches|ok|okey|dale|listo|gracias|"
    r"me llamo|mi nombre es|mi nombre|nombre|soy|mi correo es|mi correo|mi mail es|mi mail|mi email es|"
    r"mi email|correo|mail|e-mail|email|es|y|mi)\b[:,.]?",
    re.IGNORECASE,
)
_NOT_A_NAME = re.compile(r"\d|https?://|[?¿!¡]")


def parse_signup(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Devuelve (nombre, correo) encontrados en el mensaje; cada uno puede ser None."""
    text = (text or "").strip()
    m = EMAIL_RE.search(text)
    email = m.group(0).lower().rstrip(".") if m else None
    rest = EMAIL_RE.sub(" ", text)
    rest = _FILLER.sub(" ", rest)
    rest = re.sub(r"[,;:/|\-–—\n]+", " ", rest)
    rest = re.sub(r"\s+", " ", rest).strip(" .")
    name = None
    if rest and not _NOT_A_NAME.search(rest):
        words = rest.split()
        if 1 <= len(words) <= 5 and all(len(w) <= 25 for w in words) and len(rest) >= 2:
            name = " ".join(w[:1].upper() + w[1:] for w in words)
    return name, email
