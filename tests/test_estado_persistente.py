"""Los avisos no se repiten tras un reinicio y los precios en vivo raros se confirman."""
import os


class FakeMessenger:
    def __init__(self):
        self.sent = []

    def send_message(self, to, body):
        self.sent.append((to, body))
        return True

    def send_template(self, to, name, variables=None):
        self.sent.append((to, f"TEMPLATE {variables}"))
        return True


def test_estado_se_guarda_en_la_base_y_sobrevive_sin_archivo(tmp_path):
    from finmate.db.state_store import load_json, save_json

    key = str(tmp_path / "algo_state.json")
    save_json(key, {"x": 1})
    assert not os.path.exists(key)          # quedó en la base, no en disco
    assert load_json(key, {}) == {"x": 1}


def test_estado_migra_archivo_viejo(tmp_path):
    import json
    from finmate.db.state_store import load_json

    key = str(tmp_path / "viejo.json")
    with open(key, "w", encoding="utf-8") as f:
        json.dump({"y": 2}, f)
    assert load_json(key, {}) == {"y": 2}
    os.remove(key)                           # tras el reinicio el archivo ya no está
    assert load_json(key, {}) == {"y": 2}


def test_alerta_watchlist_no_se_repite_tras_reinicio(tmp_path, monkeypatch):
    from finmate.alerts import watchlist_alerts as wa

    state_file = str(tmp_path / "wl_reinicio.json")
    monkeypatch.setattr(wa, "STATE_FILE", state_file)
    monkeypatch.setattr(wa, "TEMPLATE_WATCHLIST_ALERT", "")
    monkeypatch.setattr(wa, "get_all_watchlist_entries", lambda: [(4242, "whatsapp:+1", "MSFT")])
    quote = lambda s: {"price": 500.0, "change_pct": 7.0, "is_closed": False}
    m = FakeMessenger()
    assert wa.check_watchlist_alerts(m, quote_fn=quote) == 1
    if os.path.exists(state_file):           # "reinicio": el disco del servidor se borra
        os.remove(state_file)
    assert wa.check_watchlist_alerts(m, quote_fn=quote) == 0
    assert len(m.sent) == 1


def test_movimiento_extremo_en_vivo_no_confirmado_no_avisa(tmp_path, monkeypatch):
    from finmate.alerts import watchlist_alerts as wa

    monkeypatch.setattr(wa, "STATE_FILE", str(tmp_path / "wl_extremo.json"))
    monkeypatch.setattr(wa, "TEMPLATE_WATCHLIST_ALERT", "")
    monkeypatch.setattr(wa, "get_all_watchlist_entries", lambda: [(4343, "whatsapp:+2", "NVDA")])
    monkeypatch.setattr(wa, "_get_finnhub_quote",
                        lambda client, s: {"price": 186.0, "change_pct": 1.2, "is_closed": False})
    live = lambda s: {"price": 250.0, "change_pct": 34.6, "is_closed": False}
    m = FakeMessenger()
    assert wa.check_watchlist_alerts(m, quote_fn=live) == 0
    assert m.sent == []


def test_movimiento_extremo_confirmado_avisa_con_dato_normal(tmp_path, monkeypatch):
    from finmate.alerts import watchlist_alerts as wa

    monkeypatch.setattr(wa, "STATE_FILE", str(tmp_path / "wl_extremo_ok.json"))
    monkeypatch.setattr(wa, "TEMPLATE_WATCHLIST_ALERT", "")
    monkeypatch.setattr(wa, "get_all_watchlist_entries", lambda: [(4444, "whatsapp:+3", "XYZ")])
    monkeypatch.setattr(wa, "_get_finnhub_quote",
                        lambda client, s: {"price": 13.0, "change_pct": 30.0, "is_closed": False})
    live = lambda s: {"price": 13.1, "change_pct": 31.0, "is_closed": False}
    m = FakeMessenger()
    assert wa.check_watchlist_alerts(m, quote_fn=live) == 1
    assert "30" in m.sent[0][1]
