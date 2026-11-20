"""Idioma de la app (español / inglés), español sin voseo y tema blanco."""
import re


def test_selector_de_idioma_en_ajustes(client, app):
    html = client.get("/panel/ajustes").get_data(as_text=True)
    assert 'id="idioma"' in html and 'data-lang="es"' in html and 'data-lang="en"' in html
    # i18n.js va en <head>, antes de panel.js, para que no parpadee en español
    head = html.split("</head>")[0]
    assert "i18n.js" in head and html.index("i18n.js") < html.index("panel.js")
    assert "i18n.js" in app.test_client().get("/panel/acceso").get_data(as_text=True)


def test_textos_nuevos_tienen_traduccion():
    js = open("finmate/web/static/panel/i18n.js", encoding="utf-8").read()
    for s in ("Idioma de la app", "Resumen", "Mis gastos", "Pregúntale a Finmate", "Ayúdanos a mejorar Finmate"):
        assert '"' + s + '":' in js, s


def test_panel_sin_voseo():
    voseo = re.compile(r"\b(querés|podés|tenés|seguís|mirá|probá|escribile|preguntale|agregá|cargá|tocá|usá|elegí|"
                       r"contanos|decime|seguí|escribí|agregalo|cargaste)\b", re.I)
    import glob
    files = glob.glob("finmate/web/templates/panel/*.html") + ["finmate/web/static/panel/panel.js", "finmate/web/api.py"]
    for f in files:
        found = voseo.findall(open(f, encoding="utf-8").read())
        assert not found, (f, found)


def test_tema_blanco():
    import json
    css = open("finmate/web/static/panel/panel.css", encoding="utf-8").read()
    assert "--bg: #FFFFFF" in css
    man = json.load(open("finmate/web/static/panel/manifest.json", encoding="utf-8"))
    assert man["background_color"] == "#FFFFFF" and man["theme_color"] == "#FFFFFF"
    from PIL import Image
    ic = Image.open("finmate/web/static/panel/icon-512.png").convert("RGB")
    assert ic.getpixel((4, 4)) == (255, 255, 255)  # ícono de pantalla de inicio con fondo blanco
