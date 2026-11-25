"""Fondos mutuos chilenos (CMF): lectura del Excel, guardado, rentabilidad,
búsqueda por banco, ranking, tools del bot y API del panel."""
import datetime as dt
import os

import pytest

from tests.conftest import H

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "cmf_fondos_muestra.xls")
TODAY = dt.date(2026, 11, 25)


@pytest.fixture
def funds_db(monkeypatch):
    """Tablas de fondos vacías, 'hoy' fijo y 4 fechas guardadas a partir de la muestra real."""
    from finmate.data_sources import cmf_fondos
    from finmate.db.models import FollowedFund, FundQuote, get_session
    from finmate.db.state_store import save_json
    from finmate.services import funds

    s = get_session()
    s.query(FundQuote).delete()
    s.query(FollowedFund).delete()
    s.commit()
    s.close()
    save_json(funds.EMPTY_KEY, [])
    save_json(funds.BACKFILL_KEY, None)
    funds._invalidate()
    monkeypatch.setattr(funds, "_today", lambda: TODAY)
    monkeypatch.setattr(funds.time, "sleep", lambda *_: None)

    rows = cmf_fondos.parse_xls(open(FIXTURE, "rb").read())
    for day, factor in [(dt.date(2026, 11, 24), 1.0), (dt.date(2026, 11, 23), 0.99),
                        (dt.date(2026, 10, 24), 0.95), (dt.date(2025, 12, 31), 0.90),
                        (dt.date(2025, 11, 24), 0.80)]:
        funds.store_day(day, [dict(r, valor_cuota=r["valor_cuota"] * factor) for r in rows])
    return funds


def test_parse_excel_real_de_la_cmf():
    from finmate.data_sources import cmf_fondos

    rows = cmf_fondos.parse_xls(open(FIXTURE, "rb").read())
    assert len(rows) == 10
    enfoque = [r for r in rows if r["run"] == "8723-8"]
    assert {r["serie"] for r in enfoque} >= {"A", "APV"}
    a = next(r for r in enfoque if r["serie"] == "A")
    assert a["admin"] == "LarrainVial" and a["tipo"] == 6 and a["valor_cuota"] == pytest.approx(3708.9828)
    assert {r["admin"] for r in rows} == {"LarrainVial", "Principal"}


def test_nombres_de_bancos():
    from finmate.data_sources.cmf_fondos import admin_short, resolve_admin

    assert resolve_admin("banco de chile") == "Banchile"
    assert resolve_admin("Itau") == "Itaú"
    assert resolve_admin("scotiabank") == "Scotia"
    assert resolve_admin("BancoEstado") == "BancoEstado"
    assert resolve_admin("algo raro") is None
    assert admin_short("BCI ASSET MANAGEMENT ADMINISTRADORA  GENERAL DE FONDOS S.A.") == "BCI"


def test_dia_sin_datos_devuelve_none(monkeypatch):
    from finmate.data_sources import cmf_fondos

    class R:
        status_code = 200
        content = b"<html>No se encuentran datos</html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(cmf_fondos.httpx, "get", lambda *a, **k: R())
    assert cmf_fondos.download_day(dt.date(2026, 11, 22)) is None


def test_rentabilidades_por_plazo(funds_db):
    s = funds_db.get_series("8723-8", "A")
    assert s["name"] == "ENFOQUE" and s["date"] == "2026-11-24"
    assert s["r_1d"] == pytest.approx(1.01, abs=0.01)
    assert s["r_1m"] == pytest.approx(5.26, abs=0.01)     # vs 24-oct
    assert s["r_ytd"] == pytest.approx(11.11, abs=0.01)   # vs 31-dic
    assert s["r_12m"] == pytest.approx(25.0, abs=0.01)    # vs 24-nov del año pasado


def test_busqueda_por_nombre_y_por_banco(funds_db):
    assert [f["name"] for f in funds_db.search("enfoque")] == ["ENFOQUE"]
    by_admin = funds_db.search("", admin="larrain vial")
    assert {f["admin"] for f in by_admin} == {"LarrainVial"} and len(by_admin) == 2
    assert {f["admin"] for f in funds_db.search("fondos de larrainvial")} == {"LarrainVial"}
    assert {f["run"] for f in funds_db.search("", tipo=6)} == {"8723-8"}
    assert funds_db.search("no existe este fondo") == []
    names = {a["name"] for a in funds_db.admins()}
    assert names == {"LarrainVial", "Principal"}


def test_ranking_una_serie_por_fondo(funds_db, monkeypatch):
    monkeypatch.setattr(funds_db, "MIN_PATRIMONIO_RANKING", 0)
    monkeypatch.setattr(funds_db, "MIN_PARTICIPES_RANKING", 0)
    rows = funds_db.ranking("12m")
    assert len({r["run"] for r in rows}) == len(rows) == 3


def test_limpieza_conserva_fin_de_mes(funds_db):
    from finmate.data_sources import cmf_fondos

    rows = cmf_fondos.parse_xls(open(FIXTURE, "rb").read())
    funds_db.store_day(dt.date(2025, 12, 15), rows)   # día suelto viejo: se borra
    funds_db.prune()
    dates = funds_db.stored_dates(fresh=True)
    assert dt.date(2025, 12, 15) not in dates
    assert dt.date(2025, 12, 31) in dates and dt.date(2025, 11, 24) in dates


def test_refresh_baja_solo_lo_que_falta(funds_db, monkeypatch):
    from finmate.data_sources import cmf_fondos

    rows = cmf_fondos.parse_xls(open(FIXTURE, "rb").read())
    pedidos = []

    def fake_fetch(day):
        pedidos.append(day)
        return None if day.weekday() >= 5 or day < dt.date(2026, 11, 20) else rows

    monkeypatch.setattr(cmf_fondos, "fetch_day", fake_fetch)
    out = funds_db.refresh(days_back=7)
    assert dt.date(2026, 11, 24) not in pedidos and dt.date(2026, 11, 23) not in pedidos  # ya estaban
    assert "2026-11-20" in out["added"]
    assert dt.date(2026, 11, 18).isoformat() in funds_db._empty_days()   # vacío y viejo: no se reintenta
    pedidos.clear()
    funds_db.refresh(days_back=7)
    assert dt.date(2026, 11, 18) not in pedidos


def test_tools_del_bot(funds_db):
    from finmate.agent import tools
    from finmate.db.repository import get_or_create_user

    out = tools.run_tool("search_funds", {"query": "enfoque"})
    assert "ENFOQUE" in out and "Serie *A*" in out and "12m +25,00%" in out
    lista = tools.run_tool("search_funds", {"administradora": "larrainvial"})
    assert "MONETARIO" in lista and "ENFOQUE" in lista
    rank = tools.run_tool("rank_funds", {"periodo": "1m"})
    assert "Mejores fondos en 1 mes" in rank or "historia suficiente" in rank

    uid = get_or_create_user("+56911112222").id
    assert "Listo" in tools.run_tool("follow_fund", {"run": "8723-8", "serie": "A", "cuotas": 100}, user_id=uid)
    mine = tools.run_tool("get_my_funds", {}, user_id=uid)
    assert "ENFOQUE" in mine and "$370.898" in mine
    assert "No encontré" in tools.run_tool("follow_fund", {"run": "8723-8", "serie": "ZZ"}, user_id=uid)
    assert "ya no lo sigo" in tools.run_tool("follow_fund", {"run": "8723-8", "serie": "A", "quitar": True}, user_id=uid)


def test_tools_sin_datos(monkeypatch):
    from finmate.agent import fund_tools
    from finmate.services import funds

    monkeypatch.setattr(funds, "has_data", lambda: False)
    assert "Todavía no tengo" in fund_tools.tool_search_funds({"query": "x"})


def test_api_del_panel(funds_db, client):
    r = client.get("/api/fondos/estado")
    assert r.status_code == 200 and r.get_json()["latest"] == "2026-11-24"
    r = client.get("/api/fondos/buscar?q=monetario")
    assert [f["run"] for f in r.get_json()["items"]] == ["8177-9"]
    r = client.get("/api/fondos/fondo/8177-9")
    assert {x["serie"] for x in r.get_json()["items"]} == {"A", "APV", "APV-AP-APVC"}
    assert client.get("/api/fondos/fondo/xx").status_code == 404

    assert client.post("/api/fondos/mios", json={"run": "8177-9", "serie": "APV"}).status_code == 403  # sin anti-CSRF
    assert client.post("/api/fondos/mios", json={"run": "8177-9", "serie": "APV"}, headers=H()).status_code == 201
    assert client.post("/api/fondos/mios", json={"run": "8177-9", "serie": "APV", "cuotas": 10}, headers=H()).status_code == 201
    mine = client.get("/api/fondos/mios").get_json()["items"]
    assert len(mine) == 1 and mine[0]["cuotas"] == 10 and mine[0]["valor"] == pytest.approx(18636, abs=1)
    assert client.delete("/api/fondos/mios/8177-9/APV", headers=H()).status_code == 200
    assert client.get("/api/fondos/mios").get_json()["items"] == []
    assert client.get("/api/fondos/ranking?periodo=12m").status_code == 200


def test_panel_muestra_la_tarjeta(client):
    html = client.get("/panel/inversiones").get_data(as_text=True)
    assert 'id="fondos"' in html and "Fondos mutuos" in html


def test_fuente_en_el_admin():
    from finmate.admin import sources

    ids = [s["id"] for s in sources.catalog()]
    assert "cmf_fondos" in ids


def test_probar_en_admin_muestra_estado_sin_descargar(funds_db, monkeypatch):
    from finmate.admin import sources
    from finmate.data_sources import cmf_fondos

    monkeypatch.setattr(cmf_fondos, "download_day", lambda d: (_ for _ in ()).throw(AssertionError("no debe bajar")))
    monkeypatch.setattr(funds_db, "start_backfill_thread", lambda: False)
    ok, detail = sources._t_cmf_fondos()
    assert ok and "5 fechas guardadas" in detail and "última 24-11" in detail


def test_pagina_inesperada_es_error_y_no_dia_vacio(monkeypatch):
    from finmate.data_sources import cmf_fondos

    class R:
        status_code = 200
        content = b"<html><body>Acceso temporalmente bloqueado</body></html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(cmf_fondos.httpx, "get", lambda *a, **k: R())
    with pytest.raises(RuntimeError, match="bloqueado"):
        cmf_fondos.download_day(dt.date(2026, 11, 20))


def test_historia_con_error_no_queda_marcada_lista(funds_db, monkeypatch):
    from finmate.data_sources import cmf_fondos
    from finmate.db.state_store import load_json

    monkeypatch.setattr(cmf_fondos, "fetch_day", lambda d: (_ for _ in ()).throw(RuntimeError("bloqueado")))
    out = funds_db.backfill()
    assert "error" in out and not load_json(funds_db.BACKFILL_KEY, None)
    assert load_json(funds_db.PROGRESS_KEY, {}).get("error") == "bloqueado"
