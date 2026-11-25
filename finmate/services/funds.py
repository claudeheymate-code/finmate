"""Fondos mutuos chilenos: guardar los datos de la CMF y consultarlos.

- `refresh()` (job diario): baja los días publicados que falten y limpia lo viejo.
- `backfill()` (una vez): baja el cierre de cada uno de los últimos 13 meses,
  para poder calcular rentabilidad de 1 mes, del año y de 12 meses desde el
  primer día.
- Consultas: `search`, `fund_series`, `get_series`, `ranking`, y lo que sigue
  cada usuario (`follow`, `unfollow`, `my_funds`).

Retención: últimos KEEP_DAILY_DAYS días completos + el último día disponible de
cada mes anterior (≈ 2.900 filas por fecha guardada).

Rentabilidad = variación del valor cuota entre dos fechas. Igual que en la
CMF, es nominal y no corrige repartos de dividendos de algunas series.
"""
from __future__ import annotations

import calendar
import datetime as dt
import logging
import threading
import time

from sqlalchemy import delete, func, select

from finmate.data_sources import cmf_fondos
from finmate.db.models import FollowedFund, FundQuote, User, get_session
from finmate.db.state_store import load_json, save_json

logger = logging.getLogger(__name__)

KEEP_DAILY_DAYS = 45
EMPTY_KEY = "cmf:empty_days"        # días que la CMF respondió sin datos (no volver a bajarlos)
BACKFILL_KEY = "cmf:backfill_done"
LAST_RUN_KEY = "cmf:last_refresh"
MIN_PATRIMONIO_RANKING = 1000       # millones: deja fuera series muy chicas del ranking
MIN_PARTICIPES_RANKING = 30

_lock = threading.Lock()
_snap_cache: dict = {}              # date -> {(run, serie): row}
_dates_cache: dict = {"at": 0.0, "dates": []}


# ---------------------------------------------------------------- guardar
def _today() -> dt.date:
    try:
        from zoneinfo import ZoneInfo

        from config.settings import TIMEZONE

        return dt.datetime.now(ZoneInfo(TIMEZONE or "America/Santiago")).date()
    except Exception:  # noqa: BLE001
        return dt.date.today()


def stored_dates(fresh: bool = False) -> list[dt.date]:
    """Fechas guardadas, de la más nueva a la más antigua (cache 5 min)."""
    if not fresh and time.time() - _dates_cache["at"] < 300:
        return _dates_cache["dates"]
    s = get_session()
    try:
        dates = [d for (d,) in s.execute(select(FundQuote.date).distinct().order_by(FundQuote.date.desc()))]
    finally:
        s.close()
    _dates_cache.update(at=time.time(), dates=dates)
    return dates


def _invalidate() -> None:
    _snap_cache.clear()
    _dates_cache["at"] = 0.0


def store_day(day: dt.date, rows: list[dict]) -> int:
    """Guarda (o reemplaza) todas las series de un día."""
    if not rows:
        return 0
    seen, clean = set(), []
    for r in rows:
        k = (r["run"], r["serie"])
        if k in seen:
            continue
        seen.add(k)
        clean.append({**{c: r.get(c) for c in ("run", "serie", "name", "admin", "tipo", "moneda",
                                                "valor_cuota", "patrimonio", "participes")}, "date": day})
    s = get_session()
    try:
        s.execute(delete(FundQuote).where(FundQuote.date == day))
        s.bulk_insert_mappings(FundQuote, clean)
        s.commit()
    finally:
        s.close()
    _invalidate()
    return len(clean)


def prune() -> int:
    """Borra fechas viejas que no son el último día guardado de su mes."""
    dates = stored_dates(fresh=True)
    if not dates:
        return 0
    cutoff = _today() - dt.timedelta(days=KEEP_DAILY_DAYS)
    month_last: dict = {}
    for d in dates:
        key = (d.year, d.month)
        month_last[key] = max(month_last.get(key, d), d)
    drop = [d for d in dates if d < cutoff and month_last[(d.year, d.month)] != d]
    if not drop:
        return 0
    s = get_session()
    try:
        s.execute(delete(FundQuote).where(FundQuote.date.in_(drop)))
        s.commit()
    finally:
        s.close()
    _invalidate()
    return len(drop)


def _empty_days() -> set:
    return set(load_json(EMPTY_KEY, []) or [])


def _mark_empty(day: dt.date) -> None:
    days = _empty_days()
    days.add(day.isoformat())
    keep = sorted(days)[-120:]
    save_json(EMPTY_KEY, keep)


def _fetch_and_store(day: dt.date) -> int | None:
    """Baja un día y lo guarda. None = la CMF no tiene datos para ese día."""
    rows = cmf_fondos.fetch_day(day)
    if not rows:
        # Solo se marca vacío si ya pasaron 3 días (la CMF publica con retraso)
        if (_today() - day).days > 3:
            _mark_empty(day)
        return None
    return store_day(day, rows)


def refresh(days_back: int = 7) -> dict:
    """Job diario: baja los días recientes que falten (la CMF publica con 1 día de retraso)."""
    with _lock:
        have = set(stored_dates(fresh=True))
        empty = _empty_days()
        today = _today()
        added, checked = [], 0
        for i in range(1, days_back + 1):
            day = today - dt.timedelta(days=i)
            if day in have or day.isoformat() in empty:
                continue
            checked += 1
            try:
                n = _fetch_and_store(day)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"CMF: no pude bajar {day}: {e}")
                break
            if n:
                added.append(day.isoformat())
            time.sleep(1)
        pruned = prune()
        save_json(LAST_RUN_KEY, {"at": dt.datetime.utcnow().isoformat(timespec="seconds"),
                                 "added": added, "checked": checked})
        if added:
            logger.info(f"CMF fondos: guardé {len(added)} día(s): {', '.join(added)}")
        return {"added": added, "checked": checked, "pruned": pruned}


def _month_end_targets(months: int = 13) -> list[dt.date]:
    today = _today()
    y, m = today.year, today.month
    out = []
    for _ in range(months):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(dt.date(y, m, calendar.monthrange(y, m)[1]))
    return out


def backfill(months: int = 13, force: bool = False) -> dict:
    """Una vez: guarda el cierre de cada uno de los últimos meses (para 1m / año / 12m)."""
    if not force and load_json(BACKFILL_KEY, None):
        return {"skipped": True}
    with _lock:
        have = set(stored_dates(fresh=True))
        added = []
        for target in _month_end_targets(months):
            for back in range(0, 5):  # si el último día no tiene datos, prueba días anteriores
                day = target - dt.timedelta(days=back)
                if day in have:
                    break
                try:
                    n = _fetch_and_store(day)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"CMF backfill: error en {day}: {e}")
                    return {"added": added, "error": str(e)[:200]}
                time.sleep(1.5)
                if n:
                    added.append(day.isoformat())
                    break
        save_json(BACKFILL_KEY, {"at": dt.datetime.utcnow().isoformat(timespec="seconds"), "added": added})
        return {"added": added}


def status() -> dict:
    dates = stored_dates()
    return {
        "latest": dates[0].isoformat() if dates else None,
        "dates": len(dates),
        "oldest": dates[-1].isoformat() if dates else None,
        "last_refresh": load_json(LAST_RUN_KEY, None),
        "backfill": load_json(BACKFILL_KEY, None),
    }


# ---------------------------------------------------------------- consultar
def _snapshot(day: dt.date) -> dict:
    if day in _snap_cache:
        return _snap_cache[day]
    s = get_session()
    try:
        rows = s.execute(select(FundQuote).where(FundQuote.date == day)).scalars().all()
        snap = {(r.run, r.serie): {
            "run": r.run, "serie": r.serie, "name": r.name, "admin": r.admin, "tipo": r.tipo,
            "moneda": r.moneda, "valor_cuota": r.valor_cuota, "patrimonio": r.patrimonio,
            "participes": r.participes} for r in rows}
    finally:
        s.close()
    if len(_snap_cache) > 8:
        _snap_cache.clear()
    _snap_cache[day] = snap
    return snap


def _ref_dates() -> dict:
    """Fechas guardadas que sirven de base para cada plazo."""
    dates = stored_dates()
    if not dates:
        return {}
    latest = dates[0]

    def on_or_before(target):
        return next((d for d in dates if d <= target), None)

    return {
        "latest": latest,
        "1d": dates[1] if len(dates) > 1 else None,
        "1m": on_or_before(latest - dt.timedelta(days=30)),
        "ytd": on_or_before(dt.date(latest.year - 1, 12, 31)),
        "12m": on_or_before(latest - dt.timedelta(days=365)),
    }


def _ret(now, then):
    if not now or not then:
        return None
    return round((now / then - 1) * 100, 2)


def _with_returns(row: dict, refs: dict) -> dict:
    key = (row["run"], row["serie"])
    out = dict(row)
    out["date"] = refs["latest"].isoformat()
    out["tipo_nombre"] = cmf_fondos.TIPOS.get(row.get("tipo"), "")
    for k in ("1d", "1m", "ytd", "12m"):
        d = refs.get(k)
        base = _snapshot(d).get(key) if d else None
        out["r_" + k] = _ret(row["valor_cuota"], base["valor_cuota"]) if base else None
        out["d_" + k] = d.isoformat() if d else None
    return out


def latest_date() -> dt.date | None:
    dates = stored_dates()
    return dates[0] if dates else None


def has_data() -> bool:
    return bool(stored_dates())


def admins() -> list[dict]:
    d = latest_date()
    if not d:
        return []
    count: dict = {}
    for r in _snapshot(d).values():
        count.setdefault(r["admin"], set()).add(r["run"])
    return sorted(({"name": k, "funds": len(v)} for k, v in count.items()), key=lambda x: x["name"])


def search(query: str = "", admin: str | None = None, tipo: int | None = None, limit: int = 12) -> list[dict]:
    """Busca fondos por nombre (y/o administradora). Devuelve un ítem por fondo con sus series."""
    d = latest_date()
    if not d:
        return []
    admin_short = cmf_fondos.resolve_admin(admin) if admin else None
    words = [w for w in cmf_fondos.norm(query).split() if w not in {"fondo", "fondos", "mutuo", "mutuos", "fm", "de", "del", "la", "el"}]
    # Si el texto es justo una administradora ("fondos de Santander"), se usa como filtro
    if words and not admin_short and " ".join(words) in cmf_fondos.ADMIN_ALIASES:
        admin_short, words = cmf_fondos.ADMIN_ALIASES[" ".join(words)], []
    funds: dict = {}
    for r in _snapshot(d).values():
        if admin_short and r["admin"] != admin_short:
            continue
        if tipo and r["tipo"] != tipo:
            continue
        hay = cmf_fondos.norm(r["name"] + " " + r["admin"] + " " + r["run"])
        if words and not all(w in hay for w in words):
            continue
        f = funds.setdefault(r["run"], {"run": r["run"], "name": r["name"], "admin": r["admin"], "tipo": r["tipo"],
                                         "tipo_nombre": cmf_fondos.TIPOS.get(r["tipo"], ""), "moneda": r["moneda"],
                                         "patrimonio": 0.0, "participes": 0, "series": []})
        f["series"].append(r["serie"])
        f["patrimonio"] += r["patrimonio"] or 0
        f["participes"] += r["participes"] or 0

    def score(f):
        exact = cmf_fondos.norm(f["name"]) == " ".join(words)
        return (not exact, -f["patrimonio"])

    out = sorted(funds.values(), key=score)[:limit]
    for f in out:
        f["series"].sort()
        f["patrimonio"] = round(f["patrimonio"], 1)
        f["date"] = d.isoformat()
    return out


def fund_series(run: str) -> list[dict]:
    """Todas las series de un fondo con valor cuota y rentabilidades."""
    refs = _ref_dates()
    if not refs:
        return []
    run = (run or "").strip().upper()
    snap = _snapshot(refs["latest"])
    rows = [r for (rn, _), r in snap.items() if rn == run]
    return sorted((_with_returns(r, refs) for r in rows), key=lambda x: x["serie"])


def get_series(run: str, serie: str) -> dict | None:
    refs = _ref_dates()
    if not refs:
        return None
    r = _snapshot(refs["latest"]).get(((run or "").strip().upper(), (serie or "").strip().upper()))
    return _with_returns(r, refs) if r else None


def ranking(period: str = "12m", tipo: int | None = None, moneda: str | None = None,
            admin: str | None = None, limit: int = 10, worst: bool = False) -> list[dict]:
    """Mejores (o peores) series en un plazo, dejando fuera las muy chicas."""
    refs = _ref_dates()
    if not refs or not refs.get(period):
        return []
    base = _snapshot(refs[period])
    admin_short = cmf_fondos.resolve_admin(admin) if admin else None
    out = []
    for key, r in _snapshot(refs["latest"]).items():
        if tipo and r["tipo"] != tipo:
            continue
        if moneda and cmf_fondos.norm(r["moneda"]) != cmf_fondos.norm(moneda):
            continue
        if admin_short and r["admin"] != admin_short:
            continue
        if r["tipo"] == 8:  # solo inversionistas calificados
            continue
        if (r["patrimonio"] or 0) < MIN_PATRIMONIO_RANKING or (r["participes"] or 0) < MIN_PARTICIPES_RANKING:
            continue
        b = base.get(key)
        if not b:
            continue
        out.append((_ret(r["valor_cuota"], b["valor_cuota"]), r))
    out.sort(key=lambda x: x[0], reverse=not worst)
    picked, seen = [], set()
    for _, r in out:  # una serie por fondo, para que el ranking muestre fondos distintos
        if r["run"] in seen:
            continue
        seen.add(r["run"])
        picked.append(r)
        if len(picked) >= limit:
            break
    return [_with_returns(r, refs) for r in picked]


# ---------------------------------------------------------------- por usuario
def follow(user_id: int, run: str, serie: str, cuotas: float | None = None) -> dict:
    run, serie = (run or "").strip().upper(), (serie or "").strip().upper()
    row = get_series(run, serie)
    if has_data() and not row:
        raise ValueError(f"No encontré la serie {serie} del fondo {run} en la CMF.")
    s = get_session()
    try:
        f = s.query(FollowedFund).filter_by(user_id=user_id, run=run, serie=serie).one_or_none()
        if f is None:
            f = FollowedFund(user_id=user_id, run=run, serie=serie)
            s.add(f)
        if cuotas is not None:
            f.cuotas = float(cuotas) if cuotas > 0 else None
        s.commit()
    finally:
        s.close()
    return row or {"run": run, "serie": serie}


def unfollow(user_id: int, run: str, serie: str | None = None) -> int:
    s = get_session()
    try:
        q = s.query(FollowedFund).filter_by(user_id=user_id, run=(run or "").strip().upper())
        if serie:
            q = q.filter_by(serie=serie.strip().upper())
        n = q.delete()
        s.commit()
        return n
    finally:
        s.close()


def my_funds(user_id: int) -> list[dict]:
    s = get_session()
    try:
        rows = s.query(FollowedFund).filter_by(user_id=user_id).order_by(FollowedFund.created_at).all()
        follows = [(f.run, f.serie, f.cuotas) for f in rows]
    finally:
        s.close()
    out = []
    for run, serie, cuotas in follows:
        d = get_series(run, serie) or {"run": run, "serie": serie, "name": run, "admin": "", "valor_cuota": None}
        d["cuotas"] = cuotas
        d["valor"] = round(cuotas * d["valor_cuota"], 0) if cuotas and d.get("valor_cuota") else None
        out.append(d)
    return out


def followers_count() -> int:
    s = get_session()
    try:
        return s.execute(select(func.count(func.distinct(FollowedFund.user_id)))).scalar() or 0
    finally:
        s.close()


def user_ids_following() -> list[int]:
    s = get_session()
    try:
        return [u for (u,) in s.execute(select(FollowedFund.user_id).distinct().join(User, User.id == FollowedFund.user_id))]
    finally:
        s.close()
