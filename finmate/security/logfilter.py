"""Oculta claves y tokens en los logs.

Antes, cada consulta a Finnhub o Marketaux dejaba la URL completa en el log de
Railway, con la clave a la vista (token=..., api_token=...). Este filtro la
reemplaza por "***" en cualquier mensaje, venga de donde venga.
"""

import logging
import re

_PATTERNS = [
    # parámetros de URL o formularios: token=..., api_token=..., apikey=..., access_token=..., key=...
    (re.compile(r"(?i)\b((?:api_?)?token|apikey|api_key|access_token|client_secret|secret|password|key)=([^&\s\"'<>]+)"),
     r"\1=***"),
    # encabezados Authorization: Bearer xxx
    (re.compile(r"(?i)(bearer\s+)[a-z0-9._\-]{12,}"), r"\1***"),
    # claves de Anthropic / OpenAI con formato conocido
    (re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{16,}"), "sk-***"),
    # tokens largos de Meta (EAA...)
    (re.compile(r"\bEAA[A-Za-z0-9]{30,}"), "EAA***"),
]


def redact(text: str) -> str:
    for rx, repl in _PATTERNS:
        text = rx.sub(repl, text)
    return text


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            clean = redact(msg)
            if clean != msg:
                record.msg, record.args = clean, None
            if record.exc_info and not record.exc_text:
                record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
        except Exception:  # noqa: BLE001
            pass
        return True


def install() -> None:
    """Agrega el filtro a todos los handlers del logger raíz y baja el ruido de
    las librerías HTTP (sus URLs ya no se registran salvo advertencias)."""
    f = RedactSecretsFilter()
    root = logging.getLogger()
    for h in root.handlers:
        if not any(isinstance(x, RedactSecretsFilter) for x in h.filters):
            h.addFilter(f)
    logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)  # "Running job…" cada 3 min
    for name in ("httpx", "httpcore", "urllib3", "websocket"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.WARNING)
        for h in lg.handlers:
            h.addFilter(f)
