"""Admin → Fuentes: qué puede leer el bot de cada medio (texto completo, mixto o solo titulares)."""
import pytest

from tests.conftest import H


def test_marca_de_pago():
    from finmate.data_sources.news_content import is_paywalled

    assert is_paywalled('<script type="application/ld+json">{"isAccessibleForFree": "False"}</script>')
    assert is_paywalled('{"isAccessibleForFree":false}')
    assert not is_paywalled('{"isAccessibleForFree": true}')
    assert not is_paywalled("<p>noticia abierta</p>")


def test_el_bot_no_lee_articulos_de_pago(monkeypatch):
    from finmate.data_sources import news_content

    monkeypatch.setattr(news_content, "_cached", lambda key, ttl, fn: fn())
    paid = '<html><script>{"isAccessibleForFree":"false"}</script><article><p>' + "texto " * 400 + "</p></article></html>"
    monkeypatch.setattr(news_content, "_fetch_html", lambda url: paid)
    assert news_content.extract_article("https://www.df.cl/noticia") == ""


def test_clasificacion():
    from finmate.admin.news_access import _classify

    assert _classify(["abierto", "abierto"]) == "completo"
    assert _classify(["abierto", "pago"]) == "mixto"
    assert _classify(["bloqueado", "pago"]) == "titular"
    assert _classify([]) == "titular"


def test_resumen_conocido_y_ordenado():
    from finmate.admin import news_access

    rows = news_access.overview()["rows"]
    by = {r["id"]: r for r in rows}
    assert by["cnbc"]["access"] == "completo" and by["wsj"]["access"] == "titular"
    assert by["bloomberg"]["label"] == "Solo titulares" and by["df"]["access"] == "mixto"
    order = [r["access"] for r in rows]
    assert order == sorted(order, key=lambda a: {"completo": 0, "mixto": 1, "titular": 2}[a])


def test_comprobacion_en_vivo(monkeypatch):
    from finmate.admin import news_access
    from finmate.data_sources import premium_news

    monkeypatch.setattr(premium_news, "fetch_feed", lambda feed, client=None: [{"url": f"https://x/{feed['id']}/{i}"} for i in range(2)])

    def probe(client, url):
        if "/cnbc" in url:
            return "abierto"
        if "/df/" in url:
            return "abierto" if url.endswith("0") else "pago"
        return "bloqueado"

    monkeypatch.setattr(news_access, "_probe_article", probe)
    data = news_access.check()
    assert data["results"]["cnbc"]["access"] == "completo"
    assert data["results"]["df"]["access"] == "mixto"
    assert data["results"]["wsj"]["access"] == "titular"
    ov = news_access.overview()
    assert ov["checked_at"] and {r["id"]: r for r in ov["rows"]}["df"]["articles"] == ["abierto", "pago"]


def test_api_del_admin(app, monkeypatch):
    from config import settings
    from finmate.admin import news_access

    monkeypatch.setattr(settings, "ADMIN_DEV_LOGIN", True)
    c = app.test_client()
    assert c.post("/admin/api/dev-login", json={"email": "claude.heymate@gmail.com"}, headers=H()).status_code == 200
    r = c.get("/admin/api/acceso-medios")
    assert r.status_code == 200 and len(r.get_json()["rows"]) == len(news_access.ACCESS)
    monkeypatch.setattr(news_access, "check", lambda: {})
    assert c.post("/admin/api/acceso-medios/chequear", headers=H()).status_code == 200
    assert c.post("/admin/api/acceso-medios/chequear").status_code == 403
    html = c.get("/admin/fuentes").get_data(as_text=True)
    assert "¿Qué puede leer el bot de cada medio?" in html
