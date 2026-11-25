"""Imágenes del portafolio (torta, barras, tabla) dibujadas en el servidor y enviadas por WhatsApp."""
import pytest

PNG = b"\x89PNG\r\n\x1a\n"


def _user_with_portfolio(phone):
    from finmate.db.repository import add_or_update_holding, get_or_create_user

    u = get_or_create_user(phone)
    for sym, q, c in (("AAPL", 10, 150.0), ("MSFT", 5, 410.5), ("XOM", 12, 118.0), ("TLT", 25, 92.0), ("NVDA", 8, 95.0)):
        add_or_update_holding(u.id, sym, q, c)
    return u


@pytest.mark.parametrize("kind", ["torta", "torta_clase", "torta_sector", "barras", "tabla"])
def test_dibuja_cada_tipo(kind):
    from finmate.services.charts import render

    u = _user_with_portfolio(f"whatsapp:+5697444{hash(kind) % 10000:04d}")
    png, caption = render(u.id, kind)
    assert png.startswith(PNG) and 10_000 < len(png) < 400_000
    assert "US$" in caption


def test_sin_posiciones_y_tipo_invalido():
    from finmate.db.repository import get_or_create_user
    from finmate.services.charts import render

    u = get_or_create_user("whatsapp:+56974449999")
    with pytest.raises(ValueError, match="No tienes posiciones"):
        render(u.id, "torta")
    with pytest.raises(ValueError, match="desconocido"):
        render(u.id, "radar")


def test_tool_sube_y_manda_la_imagen(monkeypatch):
    from finmate.agent.tools import run_tool
    from finmate.whatsapp import meta_cloud

    u = _user_with_portfolio("whatsapp:+56974440001")
    sent = {}
    monkeypatch.setattr(meta_cloud, "upload_media", lambda content, mime, name: sent.update(size=len(content), mime=mime) or "MEDIA1")
    monkeypatch.setattr(meta_cloud, "send_image", lambda to, mid, caption="": sent.update(to=to, mid=mid, caption=caption) or True)
    out = run_tool("send_portfolio_chart", {"kind": "tabla"}, user_id=u.id)
    assert out.startswith("Imagen enviada")
    assert sent["mid"] == "MEDIA1" and sent["to"] == u.phone and sent["mime"] == "image/png"
    assert "Tus posiciones" in sent["caption"]


def test_tool_avisa_si_whatsapp_falla(monkeypatch):
    from finmate.agent.tools import run_tool
    from finmate.whatsapp import meta_cloud

    u = _user_with_portfolio("whatsapp:+56974440002")
    monkeypatch.setattr(meta_cloud, "upload_media", lambda *a, **k: None)
    assert "No mandé la imagen" in run_tool("send_portfolio_chart", {"kind": "torta"}, user_id=u.id)


def test_payload_de_imagen_para_meta(monkeypatch):
    from finmate.whatsapp import meta_cloud

    seen = {}
    monkeypatch.setattr(meta_cloud, "_post", lambda payload: seen.update(payload) or True)
    assert meta_cloud.send_image("whatsapp:+56911112222", "M1", "hola")
    assert seen["type"] == "image" and seen["image"] == {"id": "M1", "caption": "hola"} and seen["to"] == "56911112222"
