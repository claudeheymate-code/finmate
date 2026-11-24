"""Filtro de tráfico para la app Flask (se instala con install(app)).

Capas:
  1. Bloqueo temporal de IPs que atacan (escaneos, fuerza bruta, floods).
  2. Detección de escaneos de vulnerabilidades (/wp-admin, /.env, .php, ...).
  3. Límite de solicitudes por IP (general y más estricto en los ingresos).
  4. Anti-falsificación (CSRF): toda escritura a /api y /admin/api exige el
     encabezado X-Finmate: 1, que un sitio ajeno no puede poner.
  5. Encabezados de seguridad en todas las respuestas (CSP, HSTS, etc.).
  6. Seguimiento de códigos de acceso incorrectos y prueba de números.

Todo vive en memoria (1 proceso): se reinicia con cada deploy, lo que está
bien para frenar ataques en curso. Lo que importa queda en security_events.
"""

import re
import threading
import time
from collections import defaultdict, deque

from flask import jsonify, request

from finmate.security.monitor import client_ip, record_event

_lock = threading.Lock()
_hits: "defaultdict[str, deque]" = defaultdict(deque)      # clave → tiempos
_blocked: dict = {}                                         # ip → hasta cuándo
_flagged: dict = {}                                         # (tipo, ip) → último aviso

GLOBAL_LIMIT = (300, 60)            # 300 solicitudes por minuto por IP
AUTH_LIMIT = (20, 600)              # 20 intentos de ingreso cada 10 min por IP
BLOCK_SCANNER = 60 * 60             # 1 hora
BLOCK_BRUTEFORCE = 30 * 60          # 30 min
MAX_KEYS = 20000                    # tope de memoria

_SCAN_RE = re.compile(
    r"(\.php\d?$|\.aspx?$|\.jsp$|\.cgi$|/wp-|/wordpress|/xmlrpc|/\.env|/\.git|/\.aws|/\.ssh|/\.htaccess|"
    r"/phpmyadmin|/pma/|/myadmin|/cgi-bin|/etc/passwd|\.\./|%2e%2e|/actuator|/server-status|/boaform|"
    r"/hnap1|/vendor/phpunit|/solr/|/console/|/manager/html|/owa/|/autodiscover|/\.ds_store|/config\.json$|"
    r"/backup|\.sql$|\.bak$|\.zip$|\.tar|/shell|/eval|/setup\.cgi)", re.IGNORECASE)

_AUTH_PATHS = ("/api/auth/", "/admin/login/google", "/admin/oauth/callback", "/admin/api/dev-login",
               "/panel/entrar")
_EXEMPT = ("/whatsapp/webhook", "/health")          # Meta firma sus llamadas; Railway revisa /health
_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _count(key: str, window: int) -> int:
    now = time.time()
    with _lock:
        if len(_hits) > MAX_KEYS:
            _hits.clear()
        q = _hits[key]
        q.append(now)
        while q and q[0] < now - window:
            q.popleft()
        return len(q)


def block_ip(ip: str, seconds: int) -> None:
    if ip:
        with _lock:
            _blocked[ip] = max(_blocked.get(ip, 0), time.time() + seconds)


def is_blocked(ip: str) -> bool:
    if not ip:
        return False
    with _lock:
        until = _blocked.get(ip)
        if until and until < time.time():
            _blocked.pop(ip, None)
            return False
        return bool(until)


def _flag_once(kind: str, ip: str, every: int = 600) -> bool:
    """True la primera vez en `every` segundos (para no registrar lo mismo 300 veces)."""
    key = (kind, ip)
    now = time.time()
    with _lock:
        if now - _flagged.get(key, 0) < every:
            return False
        _flagged[key] = now
        return True


def reset() -> None:
    """Solo para tests."""
    with _lock:
        _hits.clear()
        _blocked.clear()
        _flagged.clear()


# ── Llamadas desde las rutas de ingreso ─────────────────────────────────

def note_login_failure(phone: str = "") -> None:
    """Código de acceso incorrecto. 5 fallos en 15 min desde una IP → bloqueo 30 min."""
    ip = client_ip() or "?"
    n = _count(f"loginfail:{ip}", 15 * 60)
    if n >= 5:
        block_ip(ip, BLOCK_BRUTEFORCE)
        if _flag_once("login_bruteforce", ip):
            record_event("login_bruteforce", "high",
                         f"{n} códigos de acceso incorrectos en 15 minutos desde la misma IP "
                         f"(último número probado: {_mask(phone)}). La IP quedó bloqueada 30 minutos.", ip=ip)


def note_unknown_number(phone: str = "") -> None:
    """Pidieron código para un número que no existe. 5 en 30 min → aviso."""
    ip = client_ip() or "?"
    n = _count(f"unknown:{ip}", 30 * 60)
    if n >= 5 and _flag_once("login_enumeration", ip, 1800):
        record_event("login_enumeration", "medium",
                     f"Se pidieron códigos para {n} números que no usan Finmate en 30 minutos desde la misma IP "
                     "(alguien podría estar probando qué números están registrados).", ip=ip)


def _mask(phone: str) -> str:
    d = (phone or "").replace("whatsapp:", "")
    return d[:5] + "••••" + d[-2:] if len(d) > 7 else "—"


# ── Hooks de Flask ──────────────────────────────────────────────────────

def _before():
    path = request.path or "/"
    if path.startswith(_EXEMPT) or path.startswith("/panel/static/"):
        return None
    ip = client_ip() or "?"
    if is_blocked(ip):
        return jsonify({"error": "bloqueado_temporalmente"}), 403

    if _SCAN_RE.search(path):
        n = _count(f"scan:{ip}", 600)
        if n >= 3:
            block_ip(ip, BLOCK_SCANNER)
        if _flag_once("scanner", ip):
            record_event("scanner", "medium",
                         f"Una IP está probando rutas típicas de ataque (ej. {path[:80]}). "
                         "Finmate no tiene esas rutas; si insiste, se bloquea 1 hora.", ip=ip)
        return "Not found", 404

    limit, window = AUTH_LIMIT if path.startswith(_AUTH_PATHS) else GLOBAL_LIMIT
    bucket = "auth" if path.startswith(_AUTH_PATHS) else "all"
    if _count(f"{bucket}:{ip}", window) > limit:
        if _flag_once(f"flood:{bucket}", ip):
            record_event("flood", "high" if bucket == "auth" else "medium",
                         ("Demasiados intentos de ingreso" if bucket == "auth" else "Demasiadas solicitudes")
                         + f" desde la misma IP (más de {limit} en {window // 60} min). Se frenaron con error 429.",
                         ip=ip)
        return jsonify({"error": "demasiadas_solicitudes"}), 429

    if (request.method in _MUTATING and (path.startswith("/api/") or path.startswith("/admin/api/"))
            and request.headers.get("X-Finmate") != "1"):
        if _flag_once("csrf_missing", ip, 3600):
            record_event("csrf_missing", "low",
                         "Llegó una escritura a la API sin el encabezado anti-falsificación. Si no fuiste tú "
                         "probando, puede ser un intento de usar la sesión de alguien desde otro sitio.", ip=ip)
        return jsonify({"error": "falta_encabezado_csrf"}), 403
    return None


CSP = ("default-src 'self'; "
       "script-src 'self'; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com data:; "
       "img-src 'self' data: blob: https:; "
       "connect-src 'self'; "
       "frame-ancestors 'self'; base-uri 'self'; form-action 'self' https://accounts.google.com; "
       "object-src 'none'")


def _after(resp):
    h = resp.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "SAMEORIGIN")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
    if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if (resp.mimetype or "").startswith("text/html"):
        h.setdefault("Content-Security-Policy", CSP)
    if request.path.startswith(("/api/", "/admin/")):
        h.setdefault("Cache-Control", "no-store")
    h.pop("Server", None)
    return resp


def install(app) -> None:
    app.before_request(_before)
    app.after_request(_after)


# ── Mensajes de WhatsApp por número ─────────────────────────────────────

MESSAGE_LIMIT = (25, 600)           # 25 mensajes en 10 minutos por número


def note_message(phone: str) -> bool:
    """False si un número está mandando demasiados mensajes (protege el gasto de
    Claude ante spam o un número comprometido). El bot le contesta un aviso corto."""
    limit, window = MESSAGE_LIMIT
    n = _count(f"msg:{phone}", window)
    if n <= limit:
        return True
    if _flag_once("message_flood", phone, 3600):
        record_event("message_flood", "medium",
                     f"El número {_mask(phone)} mandó más de {limit} mensajes en {window // 60} minutos. "
                     "Mientras siga así, el bot le responde un aviso corto sin usar Claude.", ip=None, path=None)
    return False
