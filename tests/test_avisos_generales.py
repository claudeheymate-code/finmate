"""Avisos generales (resultados, macro, noticias, resumen semanal) según lo que elige cada usuario."""
import itertools

_n = itertools.count(1)


def _user(**settings):
    from finmate.db.repository import get_or_create_user
    from finmate.db.settings_repo import set_notification_settings

    u = get_or_create_user(f"whatsapp:+5698800{next(_n):04d}")
    if settings:
        set_notification_settings(u.id, **settings)
    return u


def test_por_defecto_solo_resultados_de_mis_activos_y_resumen():
    from finmate.db.repository import add_to_watchlist
    from finmate.db.settings_repo import recipients_for

    u = _user()
    add_to_watchlist(u.id, "ZZQX")
    assert u.phone in recipients_for("earnings", "ZZQX")
    assert u.phone not in recipients_for("earnings", "OTRA")
    assert u.phone in recipients_for("weekly")
    assert u.phone not in recipients_for("macro")
    assert u.phone not in recipients_for("market_news")


def test_cada_usuario_elige():
    from finmate.db.settings_repo import recipients_for

    todo = _user(earnings_alerts="all", macro_alerts=True, market_news_alerts=True)
    nada = _user(earnings_alerts="off", weekly_summary_enabled=False)
    assert todo.phone in recipients_for("earnings", "CUALQUIERA")
    assert todo.phone in recipients_for("macro") and todo.phone in recipients_for("market_news")
    assert nada.phone not in recipients_for("earnings", "CUALQUIERA")
    assert nada.phone not in recipients_for("weekly")


def test_motor_manda_solo_a_quien_lo_pidio(monkeypatch):
    from finmate.alerts import engine as eng

    sent = []
    e = eng.AlertEngine.__new__(eng.AlertEngine)

    class M:
        def broadcast(self, msg, recipients=None):
            sent.append(list(recipients or []))

    e.messenger = M()
    monkeypatch.setattr(eng, "TEMPLATE_MARKET_NOTIFY", "")
    e._broadcast_or_queue("hola", "Dato macroeconómico", [])
    assert sent == []                      # nadie lo pidió: no se manda a la lista fija
    e._broadcast_or_queue("hola", "Dato macroeconómico", ["whatsapp:+1"])
    assert sent == [["whatsapp:+1"]]


def test_migracion_de_la_lista_fija_una_sola_vez():
    from finmate.db.news_repo import get_news_topics
    from finmate.db.settings_repo import get_notification_settings, migrate_legacy_recipients, set_notification_settings
    from finmate.db.state_store import save_json

    save_json("migration:legacy_recipients", {})
    u = _user()
    assert migrate_legacy_recipients([u.phone, "whatsapp:+10000000000"]) == 1
    s = get_notification_settings(u.id)
    assert s["earnings_alerts"] == "all" and s["macro_alerts"] and s["market_news_alerts"]
    assert ("podcast", "primer_click") in get_news_topics(u.id)
    # Si después el usuario apaga algo, la migración no lo vuelve a prender.
    set_notification_settings(u.id, macro_alerts=False)
    assert migrate_legacy_recipients([u.phone]) == 0
    assert get_notification_settings(u.id)["macro_alerts"] is False
