"""Etapa 3: páginas del panel."""


def test_paginas_redirigen_sin_sesion(app):
    c = app.test_client()
    for path in ("/panel/", "/panel/inversiones", "/panel/gastos", "/panel/ajustes"):
        r = c.get(path)
        assert r.status_code == 302 and r.headers["Location"].endswith("/panel/acceso")


def test_acceso_muestra_login_de_desarrollo(app):
    html = app.test_client().get("/panel/acceso").get_data(as_text=True)
    assert 'id="dev-login"' in html


def test_paginas_con_sesion(client):
    for path, marker in (("/panel/", "Tu plata, de un vistazo"), ("/panel/inversiones", "Top 3 ganadoras"),
                         ("/panel/gastos", "Registrar un gasto"), ("/panel/ajustes", "Personalidad del bot")):
        r = client.get(path)
        assert r.status_code == 200, path
        html = r.get_data(as_text=True)
        assert marker in html and "panel.js" in html and "panel.css" in html
        assert 'aria-current="page"' in html


def test_archivos_estaticos(client):
    for f in ("panel.css", "panel.js", "finmate-icon-white.png"):
        assert client.get("/panel/static/" + f).status_code == 200
