"""Noticias con contenido: Bing RSS, extracción de texto y SEC (HTTP simulado)."""
from finmate.data_sources import news_content as nc

RSS = """<rss><channel><item><title>Nvidia sube 30%</title>
<link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url=https%3a%2f%2fmedio.cl%2fnota-1</link>
<description>Resumen corto</description><pubDate>Mon, 23 Nov 2026 12:00:00 GMT</pubDate>
<News:Source>Medio</News:Source></item></channel></rss>"""

ARTICLE = "<html><body><article><h1>Nvidia sube</h1>" + "<p>Las acciones de Nvidia subieron con fuerza tras el regreso de su fundador a la dirección de la empresa.</p>" * 5 + "</article></body></html>"


class R:
    def __init__(self, text="", status=200, ctype="text/html", data=None):
        self.text, self.status_code, self.headers = text, status, {"content-type": ctype}
        self.content = text.encode()
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_bing_news_saca_link_directo(monkeypatch):
    monkeypatch.setattr(nc.httpx, "get", lambda *a, **k: R(RSS))
    items = nc.bing_news("nvidia test unico 1")
    assert items[0]["url"] == "https://medio.cl/nota-1"
    assert items[0]["source"] == "Medio" and items[0]["title"] == "Nvidia sube 30%"


def test_extrae_texto_del_articulo(monkeypatch):
    monkeypatch.setattr(nc, "_fetch_html", lambda url: ARTICLE)
    text = nc.extract_article("https://medio.cl/nota-unica-2")
    assert "regreso de su fundador" in text


def test_articulo_bloqueado_devuelve_vacio(monkeypatch):
    monkeypatch.setattr(nc, "_fetch_html", lambda url: "")
    assert nc.extract_article("https://medio.cl/pago-3") == ""
    assert nc.extract_article("no-es-url") == ""


def test_tool_noticias_junta_contenido(monkeypatch):
    from finmate.agent import news_content_tools as t

    monkeypatch.setattr(t, "_finnhub_items", lambda s: [])
    monkeypatch.setattr(t.nc, "guardian_search", lambda q: [])
    monkeypatch.setattr(t.nc, "bing_news", lambda q, lang: [
        {"title": f"Nota {lang}", "url": f"https://m.cl/{lang}", "source": "M", "summary": "s", "date": "hoy"}])
    monkeypatch.setattr(t.nc, "extract_article", lambda url: "Texto completo de la nota.")
    out = t.tool_get_news_detail({"query": "nvidia"})
    assert "Texto completo de la nota." in out and "https://m.cl/es" in out and "Nota en" in out


def test_sec_trae_ultimo_8k(monkeypatch):
    def fake_get(url):
        if url.endswith("company_tickers.json"):
            return R(data={"0": {"ticker": "ZZZT", "cik_str": 123}})
        if "submissions" in url:
            return R(data={"filings": {"recent": {
                "form": ["8-K"], "accessionNumber": ["0000-00-1"], "primaryDocument": ["d.htm"],
                "filingDate": ["2026-11-23"], "items": ["5.02"]}}})
        if url.endswith("index.json"):
            return R(data={"directory": {"item": [{"name": "ex99-1.htm"}]}})
        return R(ARTICLE)

    monkeypatch.setattr(nc, "_sec_get", fake_get)
    f = nc.sec_latest_filings("ZZZT")
    assert f[0]["form"] == "8-K" and "regreso de su fundador" in f[0]["text"]
