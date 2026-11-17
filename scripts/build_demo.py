"""Regenera la versión de prueba pública (docs/demo_panel) desde el panel real.

Renderiza cada pestaña con el servidor de Flask en modo de prueba (SQLite
temporal, acceso de desarrollo) y la convierte en una página estática que usa
demo-api.js como backend simulado. También copia panel.css y panel.js,
ajustando las rutas.

Uso (desde la carpeta del repo):
    python scripts/build_demo.py

No toca demo-api.js (los datos de ejemplo se editan ahí a mano).
"""
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "demo_panel")

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="finmate-demo-"), "demo.db")
os.environ["PANEL_DEV_LOGIN"] = "true"
os.environ["FLASK_SECRET_KEY"] = "demo-build"
os.environ.setdefault("FINNHUB_API_KEY", "demo")
sys.path.insert(0, ROOT)

PAGES = {  # ruta del panel -> archivo de la demo
    "/panel/": "index.html",
    "/panel/inversiones": "inversiones.html",
    "/panel/gastos": "gastos.html",
    "/panel/ajustes": "ajustes.html",
    "/panel/feedback": "feedback.html",
}

BANNER = (
    '<div id="demo-banner" style="position:fixed;left:50%;bottom:calc(92px + env(safe-area-inset-bottom));'
    "transform:translateX(-50%);white-space:nowrap;z-index:9999;background:rgba(20,22,35,.92);color:#fff;"
    "border:1px solid rgba(255,255,255,.18);border-radius:999px;padding:6px 14px;"
    "font:500 12px/1.4 Inter,system-ui,sans-serif;box-shadow:0 6px 24px rgba(0,0,0,.3);display:flex;gap:10px;"
    'align-items:center;max-width:94vw"><span>Versión de prueba · datos de ejemplo</span>'
    '<button type="button" id="demo-reset" style="all:unset;cursor:pointer;text-decoration:underline">'
    "Reiniciar</button></div>"
)


def to_demo(html: str) -> str:
    html = html.replace("/panel/static/", "")
    # Enlaces internos del panel -> archivos de la demo (con o sin #ancla)
    for route, fname in sorted(PAGES.items(), key=lambda kv: -len(kv[0])):
        html = re.sub(r'href="' + re.escape(route) + r'(#[^"]*)?"', lambda m, f=fname: 'href="' + f + (m.group(1) or "") + '"', html)
    html = html.replace('href="/panel/acceso"', 'href="acceso.html"')
    html = re.sub(r"<title>(.*?)</title>", r"<title>\1 · Finmate (prueba)</title>", html, count=1)
    html = html.replace('<script src="panel.js"></script>', '<script src="demo-api.js"></script>\n<script src="panel.js"></script>\n' + BANNER)
    return html


def demo_js(js: str) -> str:
    return js.replace('location.href = "/panel/acceso"', 'location.href = "acceso.html"').replace(
        'location.href = "/panel/";', 'location.href = "index.html";'
    )


def main():
    from main import app

    app.config.update(TESTING=True)
    c = app.test_client()
    acceso = c.get("/panel/acceso").get_data(as_text=True)
    c.post("/api/auth/dev-login", json={"phone": "+56900000000"}, headers={"X-Finmate": "1"})
    for route, fname in PAGES.items():
        r = c.get(route)
        assert r.status_code == 200, (route, r.status_code)
        with open(os.path.join(OUT, fname), "w", encoding="utf-8") as f:
            f.write(to_demo(r.get_data(as_text=True)))
    with open(os.path.join(OUT, "acceso.html"), "w", encoding="utf-8") as f:
        f.write(to_demo(acceso))
    static = os.path.join(ROOT, "finmate", "web", "static", "panel")
    with open(os.path.join(static, "panel.css"), encoding="utf-8") as f:
        css = f.read()
    with open(os.path.join(OUT, "panel.css"), "w", encoding="utf-8") as f:
        f.write(css)
    with open(os.path.join(static, "panel.js"), encoding="utf-8") as f:
        js = f.read()
    with open(os.path.join(OUT, "panel.js"), "w", encoding="utf-8") as f:
        f.write(demo_js(js))
    print("Demo regenerada en", OUT)


if __name__ == "__main__":
    main()
