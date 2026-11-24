"""Chequeos automáticos de seguridad (diario, mensual y a pedido desde el admin).

  - Configuración: accesos de desarrollo encendidos, claves faltantes o débiles.
  - Integridad: los archivos que corren en el servidor son idénticos a los de
    GitHub para el commit desplegado (y no cambiaron desde que arrancó).
    Detecta código modificado o agregado a escondidas.
  - Dependencias: consulta la base pública de vulnerabilidades OSV (Google)
    con las librerías instaladas y sus versiones.
  - Consumo: gasto de Claude del mes sobre el umbral configurado.

Cada problema queda como evento en Inbox → Seguridad; el resultado completo
del último chequeo se guarda en kv_state para mostrarlo en el panel.
"""

import datetime as dt
import hashlib
import logging
import os
from pathlib import Path

import httpx

from finmate.security.monitor import record_event

logger = logging.getLogger("finmate.security")

ROOT = Path(__file__).resolve().parents[2]
_CODE_EXT = {".py", ".html", ".js", ".css", ".json", ".txt"}
_SKIP_DIRS = {"tests", "docs", "__pycache__", ".git", ".pytest_cache", "node_modules", ".venv", "venv"}
GITHUB_REPO = os.getenv("SECURITY_GITHUB_REPO", "claudeheymate-code/finmate")
LAST_CHECK_KEY = "security:last_check"
_baseline: dict = {}


# ── Configuración ───────────────────────────────────────────────────────

def check_config() -> list[dict]:
    from config import settings

    issues = []

    def add(sev, msg):
        issues.append({"severity": sev, "detail": msg})

    if getattr(settings, "PANEL_DEV_LOGIN", False):
        add("critical", "PANEL_DEV_LOGIN está en true: cualquiera puede entrar al panel de un usuario solo "
                        "con su número. Bórrala o ponla en false en Railway.")
    if getattr(settings, "ADMIN_DEV_LOGIN", False):
        add("critical", "ADMIN_DEV_LOGIN está en true: se puede entrar al admin sin Google. Bórrala en Railway.")
    if getattr(settings, "FLASK_DEBUG", False):
        add("high", "FLASK_DEBUG está en true en producción (muestra detalles internos si hay errores).")
    key = getattr(settings, "FLASK_SECRET_KEY", "")
    if not key:
        add("high", "Falta FLASK_SECRET_KEY: las sesiones se firman con una clave temporal.")
    elif len(key) < 32:
        add("medium", "FLASK_SECRET_KEY es corta (menos de 32 caracteres). Usa una más larga y aleatoria.")
    if not getattr(settings, "META_APP_SECRET", ""):
        add("high", "Falta META_APP_SECRET: no se puede comprobar que los mensajes de WhatsApp vengan de Meta.")
    if len(getattr(settings, "META_VERIFY_TOKEN", "") or "") < 12:
        add("low", "META_VERIFY_TOKEN es corto o falta (se usa al verificar el webhook con Meta).")
    if not getattr(settings, "ACCESS_APPROVAL_REQUIRED", True):
        add("low", "ACCESS_APPROVAL_REQUIRED está apagado: cualquier número puede usar el bot sin aprobación.")
    if not getattr(settings, "WHATSAPP_RECIPIENTS", []):
        add("medium", "WHATSAPP_RECIPIENTS está vacío: los avisos de seguridad no pueden llegarte por WhatsApp.")
    return issues


# ── Integridad de archivos ──────────────────────────────────────────────

def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _code_files() -> dict:
    """{ruta relativa: hash git} de los archivos de código desplegados."""
    out = {}
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix not in _CODE_EXT:
            continue
        rel = p.relative_to(ROOT)
        if any(part in _SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        try:
            out[rel.as_posix()] = _git_blob_sha(p.read_bytes())
        except OSError:
            continue
    return out


def snapshot_baseline() -> None:
    """Se llama al arrancar: guarda cómo están los archivos en este momento."""
    global _baseline
    try:
        _baseline = _code_files()
        logger.info(f"Seguridad: línea base de integridad con {len(_baseline)} archivos.")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Seguridad: no pude crear la línea base de integridad: {e}")


def check_integrity() -> list[dict]:
    issues = []
    current = _code_files()
    # 1) ¿Cambió algo desde que arrancó el servidor? (en Railway el código no debería cambiar nunca)
    if _baseline:
        changed = sorted(k for k in current if k in _baseline and current[k] != _baseline[k])
        added = sorted(k for k in current if k not in _baseline)
        removed = sorted(k for k in _baseline if k not in current)
        if changed or added or removed:
            issues.append({"severity": "critical", "detail": (
                "Los archivos del servidor cambiaron después de arrancar (esto no pasa con un deploy normal). "
                + _list("Modificados", changed) + _list("Nuevos", added) + _list("Borrados", removed))})
    # 2) ¿Lo que corre es igual a GitHub para el commit desplegado?
    sha = os.getenv("RAILWAY_GIT_COMMIT_SHA", "")
    if sha:
        try:
            r = httpx.get(f"https://api.github.com/repos/{GITHUB_REPO}/git/trees/{sha}",
                          params={"recursive": "1"}, timeout=15,
                          headers={"Accept": "application/vnd.github+json", "User-Agent": "finmate-security"})
            if r.status_code == 200:
                remote = {t["path"]: t["sha"] for t in r.json().get("tree", []) if t.get("type") == "blob"}
                diff = sorted(k for k, v in current.items() if remote.get(k) not in (None, v))
                extra = sorted(k for k in current if k not in remote and k.endswith(".py"))
                if diff or extra:
                    issues.append({"severity": "critical", "detail": (
                        f"El código en el servidor no coincide con GitHub (commit {sha[:7]}). "
                        + _list("Distintos", diff) + _list("Que no están en GitHub", extra))})
            else:
                logger.info(f"Seguridad: GitHub respondió {r.status_code} al comparar archivos.")
        except Exception as e:  # noqa: BLE001
            logger.info(f"Seguridad: no pude comparar con GitHub: {e}")
    return issues


def _list(label: str, items: list) -> str:
    if not items:
        return ""
    more = f" y {len(items) - 8} más" if len(items) > 8 else ""
    return f" {label}: {', '.join(items[:8])}{more}."


# ── Dependencias vulnerables (OSV) ──────────────────────────────────────

def _installed() -> list[tuple]:
    from importlib import metadata

    req = set()
    try:
        for line in (ROOT / "requirements.txt").read_text().splitlines():
            line = line.split("#")[0].strip()
            if line and "==" in line:
                req.add(line.split("==")[0].split("[")[0].strip().lower().replace("_", "-"))
    except OSError:
        pass
    out = []
    for d in metadata.distributions():
        name = (d.metadata.get("Name") or "").lower().replace("_", "-")
        if name and (not req or name in req):
            out.append((name, d.version))
    return sorted(set(out))


def check_dependencies() -> list[dict]:
    pkgs = _installed()
    if not pkgs:
        return []
    try:
        r = httpx.post("https://api.osv.dev/v1/querybatch", timeout=20, json={
            "queries": [{"package": {"name": n, "ecosystem": "PyPI"}, "version": v} for n, v in pkgs]})
        r.raise_for_status()
        results = r.json().get("results", [])
    except Exception as e:  # noqa: BLE001
        logger.info(f"Seguridad: no pude consultar vulnerabilidades (OSV): {e}")
        return []
    found = []
    for (name, ver), res in zip(pkgs, results):
        ids = [v.get("id") for v in (res or {}).get("vulns", []) if v.get("id")]
        if ids:
            found.append(f"{name} {ver} ({', '.join(ids[:3])}{'…' if len(ids) > 3 else ''})")
    if not found:
        return []
    return [{"severity": "high", "detail": (
        "Hay librerías con vulnerabilidades conocidas: " + "; ".join(found[:10])
        + ". Hay que subir su versión en requirements.txt (pídeselo a Claude en la revisión mensual).")}]


# ── Consumo de Claude ───────────────────────────────────────────────────

def check_spend() -> list[dict]:
    limit = float(os.getenv("SECURITY_CLAUDE_MONTHLY_ALERT_USD", "15"))
    try:
        from finmate.web.admin import _usage_with_costs

        u = _usage_with_costs()
        cost = u.get("claude_cost_usd") or 0
    except Exception:  # noqa: BLE001
        return []
    if cost >= limit:
        return [{"severity": "high", "detail": (
            f"Claude lleva US${cost:.2f} este mes (umbral: US${limit:.0f}). Si no esperabas tanto uso, revisa en "
            "Usuarios quién está mandando más mensajes. El umbral se cambia con SECURITY_CLAUDE_MONTHLY_ALERT_USD.")}]
    return []


# ── Orquestación ────────────────────────────────────────────────────────

_KIND = {"config": "config", "integrity": "integrity", "dependencies": "dependency_vuln", "spend": "spend_spike"}


def run_checks(trigger: str = "manual") -> dict:
    """Corre todos los chequeos, registra los problemas y guarda el informe."""
    report = {"at": dt.datetime.utcnow().isoformat(), "trigger": trigger, "sections": {}}
    for name, fn in (("config", check_config), ("integrity", check_integrity),
                     ("dependencies", check_dependencies), ("spend", check_spend)):
        try:
            issues = fn()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Seguridad: falló el chequeo {name}: {e}")
            issues = [{"severity": "low", "detail": f"No se pudo completar este chequeo ({type(e).__name__})."}]
        report["sections"][name] = issues
        for it in issues:
            record_event(_KIND[name], it["severity"], it["detail"], ip=None, path=None)
    total = sum(len(v) for v in report["sections"].values())
    report["ok"] = total == 0
    try:
        from finmate.db.state_store import save_json

        save_json(LAST_CHECK_KEY, report)
    except Exception:  # noqa: BLE001
        pass
    logger.info(f"Seguridad: chequeo {trigger} terminado, {total} problema(s).")
    return report


def last_report() -> dict:
    try:
        from finmate.db.state_store import load_json

        return load_json(LAST_CHECK_KEY, {}) or {}
    except Exception:  # noqa: BLE001
        return {}


MONTHLY_CHECKLIST = (
    "1) Abre Inbox → Seguridad y marca como revisado lo que ya entiendes.\n"
    "2) Pídele a Claude: \"haz la limpieza y chequeo mensual de Finmate\" (revisa código sin uso, "
    "bugs de las páginas y actualiza librerías con vulnerabilidades).\n"
    "3) Revisa en Costos que el gasto del mes sea el esperado.\n"
    "4) Revisa en Usuarios que no haya números que no conozcas con acceso."
)


def run_monthly_review() -> dict:
    """Primer día de cada mes: chequeo completo + recordatorio en el Inbox y por WhatsApp."""
    report = run_checks("mensual")
    n = sum(len(v) for v in report["sections"].values())
    estado = "Todo en orden en el chequeo automático." if n == 0 else f"El chequeo automático encontró {n} punto(s) a revisar."
    record_event("monthly_review", "medium", f"Toca la revisión mensual de limpieza y seguridad. {estado}\n\n"
                 + MONTHLY_CHECKLIST, ip=None, path=None, notify=True)
    return report
