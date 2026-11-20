import json, os, re, shutil
ROOT = os.path.expanduser("~/mnt/Finmate")
OUT = os.path.join(ROOT, "docs", "demo_panel")
os.makedirs(OUT, exist_ok=True)
cap = json.load(open(os.path.expanduser("~/demo/capture.json"), encoding="utf-8"))
api = cap["api"]
today = cap["today"]
y, m = map(int, today.split("-")[:2])
pm_key = [k for k in api if k.startswith("/finanzas/movimientos?")][0]

positions = [{k: p[k] for k in ("symbol", "quantity", "avg_cost", "asset_class", "sector")}
             for p in api["/portafolio"]["json"]["positions"]]
prices = {p["symbol"]: [p["price"], p["change_pct"]] for p in api["/portafolio"]["json"]["positions"]}
for w in api["/watchlist"]["json"]["items"]:
    prices[w["symbol"]] = [w["price"], w["change_pct"]]
# precios ilustrativos para poder agregar otros activos comunes en la demo
extra = {"AMZN": [231.40, -0.66, "Consumo"], "GOOGL": [262.15, 0.92, "Tecnología"], "META": [698.30, 1.41, "Tecnología"],
         "NFLX": [1124.50, -0.38, "Comunicaciones"], "SPY": [668.20, 0.21, "Índice amplio"], "QQQ": [598.75, 0.44, "Índice amplio"],
         "VOO": [614.10, 0.20, "Índice amplio"], "AGG": [99.40, 0.08, "Bonos"], "IEF": [96.20, 0.10, "Bonos"],
         "V": [351.90, 0.33, "Financiero"], "WMT": [104.25, -0.12, "Consumo"], "DIS": [112.60, 0.57, "Comunicaciones"],
         "AMD": [238.90, 3.12, "Tecnología"], "NVDA": [186.64, 2.78, "Tecnología"]}
sectors = {k: v[2] for k, v in extra.items()}
for k, v in extra.items():
    prices.setdefault(k, v[:2])
txs = api[pm_key]["json"]["items"] + api["/finanzas/movimientos"]["json"]["items"]
seed = {
    "today": today,
    "feedbackTo": "claude.heymate@gmail.com",
    "prices": prices,
    "sectors": sectors,
    "bondEtfs": ["TLT", "IEF", "SHY", "BND", "AGG", "LQD", "HYG", "JNK", "TIP", "BIL", "SGOV", "GOVT", "MUB", "EMB", "BNDX"],
    "broadEtfs": ["SPY", "VOO", "IVV", "VTI", "QQQ", "QQQM", "DIA", "IWM", "VT", "VXUS", "VEA", "VWO"],
    "categories": api["/finanzas/categorias"]["json"]["categories"],
    "catalogo": api["/seguimientos"]["json"]["catalogo"],
    "state": {
        "logged": False,
        "positions": positions,
        "watchlist": [{"symbol": w["symbol"], "note": w["note"]} for w in api["/watchlist"]["json"]["items"]],
        "txs": txs,
        "nextId": max(t["id"] for t in txs) + 1,
        "personalidad": api["/personalidad"]["json"],
        "temas": api["/seguimientos"]["json"]["temas"],
        "indicadores": [i["code"] for i in api["/seguimientos"]["json"]["indicadores"]],
        "avisos": api["/avisos"]["json"],
        "phone": "+56900000000",
    },
}
demo_js = open(os.path.expanduser("~/demo/demo-api.template.js"), encoding="utf-8").read()
open(os.path.join(OUT, "demo-api.js"), "w", encoding="utf-8").write(
    demo_js.replace("/*SEED*/null", json.dumps(seed, ensure_ascii=False)))

pages = {"acceso": "acceso.html", "resumen": "index.html", "inversiones": "inversiones.html",
         "gastos": "gastos.html", "ajustes": "ajustes.html", "feedback": "feedback.html"}
BANNER = ('<div id="demo-banner" style="position:fixed;left:50%;bottom:calc(92px + env(safe-area-inset-bottom));transform:translateX(-50%);white-space:nowrap;z-index:9999;'
          'background:rgba(20,22,35,.92);color:#fff;border:1px solid rgba(255,255,255,.18);border-radius:999px;'
          'padding:6px 14px;font:500 12px/1.4 Inter,system-ui,sans-serif;box-shadow:0 6px 24px rgba(0,0,0,.3);'
          'display:flex;gap:10px;align-items:center;max-width:94vw">'
          '<span>Versión de prueba · datos de ejemplo</span>'
          '<button type="button" id="demo-reset" style="all:unset;cursor:pointer;text-decoration:underline">Reiniciar</button></div>')

def fix_links(html):
    html = html.replace("/panel/static/", "")
    def repl(mo):
        path, frag = mo.group(2), mo.group(3) or ""
        target = {"/panel/": "index.html", "/panel": "index.html", "/panel/inversiones": "inversiones.html",
                  "/panel/gastos": "gastos.html", "/panel/ajustes": "ajustes.html", "/panel/feedback": "feedback.html", "/panel/acceso": "acceso.html"}.get(path)
        return f'{mo.group(1)}="{target}{frag}"' if target else mo.group(0)
    return re.sub(r'(href|action)="(/panel/?[a-z]*)(#[a-z]+)?"', repl, html)

for name, fname in pages.items():
    html = fix_links(cap["pages"][name])
    html = html.replace('<script src="panel.js"></script>', '<script src="demo-api.js"></script>\n<script src="panel.js"></script>')
    assert "demo-api.js" in html, name
    html = html.replace("+5695 •••• 1465", "+5690 •••• 0000")
    html = html.replace("</body>", BANNER + "\n</body>")
    html = re.sub(r"<title>(.*?)</title>", r"<title>\1 · Finmate (prueba)</title>", html, count=1)
    open(os.path.join(OUT, fname), "w", encoding="utf-8").write(html)

js = open(os.path.join(ROOT, "finmate/web/static/panel/panel.js"), encoding="utf-8").read()
js = js.replace('"/panel/acceso"', '"acceso.html"').replace('location.href = "/panel/"', 'location.href = "index.html"')
assert "/panel/" not in js, [l for l in js.splitlines() if "/panel/" in l]
open(os.path.join(OUT, "panel.js"), "w", encoding="utf-8").write(js)
shutil.copy(os.path.join(ROOT, "finmate/web/static/panel/panel.css"), OUT)
shutil.copy(os.path.join(ROOT, "finmate/web/static/panel/finmate-icon.png"), OUT)
shutil.copy(os.path.join(ROOT, "finmate/web/static/panel/i18n.js"), OUT)
for icon in ("apple-touch-icon.png", "favicon-32.png", "favicon-48.png", "icon-192.png", "icon-512.png", "icon-maskable-512.png"):
    shutil.copy(os.path.join(ROOT, "finmate/web/static/panel", icon), OUT)
# Manifest propio de la demo: rutas relativas (GitHub Pages sirve en /finmate/demo_panel/)
man = json.load(open(os.path.join(ROOT, "finmate/web/static/panel/manifest.json"), encoding="utf-8"))
# Alcance = todo el sitio (/finmate/), así la portada /finmate/ y el panel
# quedan dentro de la "app" y iOS no muestra Safari al navegar entre ellos.
man["id"] = "/finmate/"; man["start_url"] = "/finmate/demo_panel/index.html"; man["scope"] = "/finmate/"
for ic in man["icons"]:
    ic["src"] = "/finmate/demo_panel/" + ic["src"].rsplit("/", 1)[-1]
json.dump(man, open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(sorted(os.listdir(OUT)))
