"""Fondos mutuos chilenos desde la CMF (Comisión para el Mercado Financiero).

La CMF publica todos los días (con 1 día de retraso) el patrimonio, los
partícipes y el valor cuota de TODAS las series de TODOS los fondos mutuos
del país (~2.900 series de ~22 administradoras: Banchile, BCI, Santander,
BancoEstado, Itaú, LarrainVial, Fintual, etc.). Es información pública: no
pide clave ni registro.

Fuente: export Excel de la consulta "Patrimonio, Rentabilidad, Partícipes y
Valor de la Cuota de Fondos Mutuos" (cmfchile.cl → Estadísticas → Fondos
Mutuos). Con `admins=0` trae todas las administradoras en un solo archivo
(.xls binario de ~700 KB). Si no hay datos para ese día devuelve una página
HTML con "No se encuentran datos".
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import unicodedata

import httpx

logger = logging.getLogger(__name__)

URL = "https://www.cmfchile.cl/institucional/estadisticas/fm.fm_bpr_dia.php"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Finmate/1.0; +https://web-production-3626a.up.railway.app)"}
TIMEOUT = 60
XLS_MAGIC = b"\xd0\xcf\x11\xe0"  # inicio de un .xls binario (OLE2)

# Tipo de fondo según la CMF (columna "Tipo de fondo (2)" del Excel)
TIPOS = {
    1: "Deuda corto plazo ≤ 90 días",
    2: "Deuda corto plazo ≤ 365 días",
    3: "Deuda mediano y largo plazo",
    4: "Mixto",
    5: "Accionario",
    6: "Libre inversión",
    7: "Estructurado",
    8: "Inversionistas calificados",
}

# Nombre corto de cada administradora (se reconoce por una palabra clave)
_ADMIN_SHORT = [
    ("LARRAINVIAL", "LarrainVial"), ("BANCHILE", "Banchile"), ("BANCOESTADO", "BancoEstado"),
    ("BANCO INTERNACIONAL", "Banco Internacional"), ("BCI", "BCI"), ("BICE", "BICE"),
    ("BTG", "BTG Pactual"), ("CREDICORP", "Credicorp Capital"), ("FINTUAL", "Fintual"),
    ("ITAU", "Itaú"), ("MBI", "MBI"), ("PRINCIPAL", "Principal"), ("PRUDENTIAL", "Prudential"),
    ("SANTANDER", "Santander"), ("SCOTIA", "Scotia"), ("SECURITY", "Security"), ("SURA", "SURA"),
    ("SOYFOCUS", "SoyFocus"), ("TOESCA", "Toesca"), ("VINCI", "Vinci Compass"), ("ZURICH", "Zurich"),
    ("AMERIS", "Ameris"),
]

# Cómo le dice la gente a cada administradora → nombre corto
ADMIN_ALIASES = {
    "banco de chile": "Banchile", "banco chile": "Banchile", "banchile": "Banchile",
    "banco estado": "BancoEstado", "bancoestado": "BancoEstado", "estado": "BancoEstado",
    "bci": "BCI", "santander": "Santander", "itau": "Itaú", "scotia": "Scotia", "scotiabank": "Scotia",
    "security": "Security", "bice": "BICE", "larrainvial": "LarrainVial", "larrain vial": "LarrainVial",
    "larrain": "LarrainVial", "lv": "LarrainVial", "fintual": "Fintual", "btg": "BTG Pactual",
    "btg pactual": "BTG Pactual", "sura": "SURA", "principal": "Principal", "zurich": "Zurich",
    "credicorp": "Credicorp Capital", "prudential": "Prudential", "soyfocus": "SoyFocus",
    "soy focus": "SoyFocus", "toesca": "Toesca", "vinci": "Vinci Compass", "compass": "Vinci Compass",
    "mbi": "MBI", "ameris": "Ameris", "internacional": "Banco Internacional",
    "banco internacional": "Banco Internacional",
}


def norm(text: str) -> str:
    """Minúsculas, sin tildes y con espacios simples (para comparar nombres)."""
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().lower()


def admin_short(full: str) -> str:
    up = norm(full).upper()
    for key, short in _ADMIN_SHORT:
        if key in up:
            return short
    name = re.sub(r"(?i)\b(administradora|general|de|fondos|s\.?a\.?|asset management)\b", " ", str(full))
    return re.sub(r"\s+", " ", name).strip().title()[:40] or str(full)[:40]


def resolve_admin(text: str) -> str | None:
    """Convierte lo que escribió el usuario ("banco de chile", "itau") en el nombre corto."""
    n = norm(text)
    if not n:
        return None
    if n in ADMIN_ALIASES:
        return ADMIN_ALIASES[n]
    for _, short in _ADMIN_SHORT:
        if norm(short) == n or norm(short).startswith(n):
            return short
    for alias, short in ADMIN_ALIASES.items():
        if len(alias) > 3 and alias in n:
            return short
    return None


def download_day(day: dt.date) -> bytes | None:
    """Baja el Excel de un día (todas las administradoras). None si ese día no tiene datos."""
    params = {
        "admins": "0", "tipofondo": "0", "moneda": "0",
        "dia_select": str(day.day), "mes_peri": str(day.month), "anio_peri": str(day.year),
        "lang": "es", "out": "excel",
    }
    r = httpx.get(URL, params=params, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    content = r.content or b""
    if content[:4] == XLS_MAGIC:
        return content
    text = content[:3000].decode("latin-1", "ignore")
    if "No se encuentran datos" in text:
        return None  # ese día la CMF no publicó datos
    snippet = re.sub(r"<[^>]+>", " ", text)
    snippet = re.sub(r"\s+", " ", snippet).strip()[:160]
    raise RuntimeError(f"la CMF devolvió una página inesperada (HTTP {r.status_code}): {snippet or 'vacía'}")


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_xls(content: bytes) -> list[dict]:
    """Lee el Excel de la CMF y devuelve una fila por serie."""
    import xlrd

    book = xlrd.open_workbook(file_contents=content, encoding_override="latin-1")
    sh = book.sheet_by_index(0)
    header_row = None
    for i in range(min(sh.nrows, 30)):
        if "RUN" in [str(c).strip() for c in sh.row_values(i)]:
            header_row = i
            break
    if header_row is None:
        raise ValueError("Formato inesperado del Excel de la CMF (no encontré la columna RUN)")

    rows = []
    for i in range(header_row + 1, sh.nrows):
        r = sh.row_values(i)
        if len(r) < 9:
            continue
        name, run, tipo, admin, serie, moneda, patrimonio, participes, valor = r[:9]
        run = str(run).strip()
        valor = _num(valor)
        if not run or not re.match(r"^\d{3,6}-[\dkK]$", run) or not valor:
            continue
        try:
            tipo = int(float(tipo))
        except (TypeError, ValueError):
            tipo = None
        part = _num(participes)
        rows.append({
            "name": re.sub(r"\s+", " ", str(name)).strip()[:120],
            "run": run.upper(),
            "tipo": tipo,
            "admin": admin_short(admin),
            "serie": str(serie).strip().upper()[:20] or "UNICA",
            "moneda": str(moneda).strip().title()[:10],
            "patrimonio": _num(patrimonio),
            "participes": int(part) if part is not None else None,
            "valor_cuota": valor,
        })
    return rows


_MESES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
          "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12}


def parse_date(content: bytes) -> dt.date:
    """Fecha del archivo, desde la línea «Fecha : 31 DE OCTUBRE DE 2026» del encabezado."""
    import xlrd

    sh = xlrd.open_workbook(file_contents=content, encoding_override="latin-1").sheet_by_index(0)
    for i in range(min(sh.nrows, 15)):
        cell = str(sh.cell_value(i, 0))
        m = re.search(r"FECHA\s*:\s*(\d{1,2})\s+DE\s+([A-ZÁÉÍÓÚ]+)\s+DE\s+(\d{4})", cell.upper())
        if m and m.group(2) in _MESES:
            return dt.date(int(m.group(3)), _MESES[m.group(2)], int(m.group(1)))
    raise ValueError("No encontré la fecha en el Excel (¿es el export diario de la CMF?)")


def fetch_day(day: dt.date) -> list[dict] | None:
    """Descarga y lee un día. None si ese día no tiene datos publicados."""
    content = download_day(day)
    if content is None:
        return None
    return parse_xls(content)
