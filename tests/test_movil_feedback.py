"""Panel en celular (pestañas abajo + deslizar) y pestaña de Feedback."""
from tests.conftest import H


def test_menu_tiene_cinco_pestanas_con_etiqueta_y_feedback(client):
    html = client.get("/panel/").get_data(as_text=True)
    for label in ("Resumen", "Inversiones", "Gastos", "Ajustes", "Feedback"):
        assert f'<span class="tab-label">{label}</span>' in html
    assert 'class="tab-pill"' in html and "viewport-fit=cover" in html


def test_pagina_feedback(client):
    r = client.get("/panel/feedback")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'id="fb-form"' in html and 'data-page="feedback"' in html
    assert 'aria-current="page"' in html.split('aria-label="Feedback"')[1][:40]


def test_js_y_css_movil():
    js = open("finmate/web/static/panel/panel.js", encoding="utf-8").read()
    css = open("finmate/web/static/panel/panel.css", encoding="utf-8").read()
    assert "function initTabs" in js and "touchmove" in js and "pageFeedback" in js
    assert ".tab-pill" in css and "position: fixed" in css.split("@media (max-width: 760px)")[1]
    assert ".table-wrap { position: relative;" in css  # evita que la tabla estire la página en el celular


def _sync(fb, monkeypatch, sink):
    monkeypatch.setattr(fb, "send_email", lambda subject, body, fields: sink.append((subject, body, fields)) or True)
    real = fb.guardar_y_enviar
    monkeypatch.setattr(fb, "guardar_y_enviar", lambda *a, **k: real(*a, **{**k, "background": False}))
    fb._recent.clear()


def test_feedback_se_guarda_y_envia(client, monkeypatch):
    from finmate.services import feedback as fb
    from finmate.db.models import Feedback, get_session

    sent = []
    _sync(fb, monkeypatch, sent)
    r = client.post("/api/feedback", json={"tipo": "idea", "rating": 5, "message": "Me encantaría un resumen los lunes", "contact": True}, headers=H())
    assert r.status_code == 201, r.get_json()
    subject, body, fields = sent[0]
    assert "Idea" in subject and "5/5" in subject and "resumen los lunes" in body and "+569" in body
    s = get_session()
    row = s.get(Feedback, r.get_json()["id"]); s.close()
    assert row.tipo == "idea" and row.rating == 5 and row.emailed is True and row.contact_ok is True


def test_feedback_sin_contacto_no_comparte_numero(client, monkeypatch):
    from finmate.services import feedback as fb

    sent = []
    _sync(fb, monkeypatch, sent)
    client.post("/api/feedback", json={"tipo": "problema", "message": "El gráfico no carga en mi celular"}, headers=H())
    assert "+569" not in sent[0][1] and "no autorizó contacto" in sent[0][1]


def test_feedback_validaciones_y_limite(client, monkeypatch):
    from finmate.services import feedback as fb

    _sync(fb, monkeypatch, [])
    assert client.post("/api/feedback", json={"tipo": "x", "message": "hola hola"}, headers=H()).status_code == 400
    assert client.post("/api/feedback", json={"tipo": "idea", "message": "hey"}, headers=H()).status_code == 400
    assert client.post("/api/feedback", json={"tipo": "idea", "message": "hola hola", "rating": 9}, headers=H()).status_code == 400
    codes = [client.post("/api/feedback", json={"tipo": "otro", "message": f"mensaje número {i}"}, headers=H()).status_code for i in range(6)]
    assert codes[:5] == [201] * 5 and codes[5] == 429


def test_formsubmit_usa_alias_y_origen(monkeypatch):
    from finmate.services import feedback as fb
    from config import settings

    calls = {}

    class R:
        content = b'{"success":"true"}'
        def raise_for_status(self): pass
        def json(self): return {"success": "true"}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.update(url=url, json=json, headers=headers); return R()

    monkeypatch.setattr(fb.httpx, "post", fake_post)
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "FEEDBACK_FORMSUBMIT_ID", "")
    assert fb.send_email("asunto", "cuerpo", {"mensaje": "x"}) is True
    assert calls["url"].endswith("/ajax/claude.heymate@gmail.com") and calls["json"]["_subject"] == "asunto"
    monkeypatch.setattr(settings, "FEEDBACK_FORMSUBMIT_ID", "abc123alias")
    fb.send_email("a", "b", {})
    assert calls["url"].endswith("/ajax/abc123alias")


def test_iconos_para_pantalla_de_inicio(client, app):
    import json
    html = client.get("/panel/").get_data(as_text=True)
    assert 'rel="apple-touch-icon"' in html and "apple-touch-icon.png" in html
    assert 'rel="manifest"' in html and 'apple-mobile-web-app-title" content="Finmate"' in html
    acceso = app.test_client().get("/panel/acceso").get_data(as_text=True)
    assert 'rel="apple-touch-icon"' in acceso
    m = app.test_client().get("/panel/static/manifest.json")
    assert m.status_code == 200
    data = json.loads(m.get_data(as_text=True))
    assert data["name"] == "Finmate" and data["display"] == "standalone"
    assert data["start_url"].startswith(data["scope"])  # si no, iOS abre Safari
    assert 'apple-mobile-web-app-capable" content="yes"' in html
    assert 'status-bar-style" content="default"' in html and "viewport-fit=cover" in acceso
    for icon in data["icons"]:
        assert app.test_client().get(icon["src"]).status_code == 200, icon["src"]


def test_todas_las_pestanas_en_la_misma_pagina(client):
    """Para que deslizar sea continuo, cada página trae las 5 pestañas lado a lado."""
    for path, page in (("/panel/", "resumen"), ("/panel/gastos", "gastos"), ("/panel/feedback", "feedback")):
        html = client.get(path).get_data(as_text=True)
        for p in ("resumen", "inversiones", "gastos", "ajustes", "feedback"):
            assert f'data-pane="{p}"' in html
        assert f'class="pane active" data-pane="{page}"' in html
        assert html.count('id="fb-form"') == 1  # sin ids duplicados
    js = open("finmate/web/static/panel/panel.js", encoding="utf-8").read()
    assert "history.pushState" in js and "translate3d" in js


def test_sin_zoom_barra_que_se_esconde_y_texto_feedback(client):
    html = client.get("/panel/feedback").get_data(as_text=True)
    assert "maximum-scale=1, user-scalable=no" in html
    assert "Cada idea que nos cuentas" in html and "Qué pasa con tu mensaje" not in html
    js = open("finmate/web/static/panel/panel.js", encoding="utf-8").read()
    css = open("finmate/web/static/panel/panel.css", encoding="utf-8").read()
    assert "gesturestart" in js and "rail-hidden" in js and ".rail.rail-hidden" in css
    mobile = css.split("@media (max-width: 760px)")[-1]
    assert "font-size: 16px" in mobile  # iOS no hace zoom al tocar un campo


def test_gastos_tabla_comparativa_y_categorias(client):
    html = client.get("/panel/gastos").get_data(as_text=True)
    assert 'id="g-cmp"' in html and "Lst Mth" in html and 'id="g-ytd"' in html and 'id="g-prev"' not in html
    assert 'id="c-form"' in html and "Solo cambian en tu cuenta" in html
