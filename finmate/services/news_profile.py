"""Perfil de noticias de cada usuario: aprende qué le importa a partir de sus notas 1-3.

Cómo funciona
-------------
Cada noticia que Finmate manda lleva una invitación a calificarla:
  3 = muy relevante, 2 = algo, 1 = poco.

Una noticia se describe con varias "claves":
  sym:NVDA          la empresa (si es de un activo)
  tema:tasas        uno o dos temas (tasas y Fed, resultados, IA, Chile…)
  tipo:activo       de qué fuente viene (noticias de tus activos, mercado,
                    resultados, dato macro)

Cada nota se suma a todas las claves de la noticia. Para una noticia nueva se
estima su nivel juntando lo aprendido de sus claves, partiendo de un supuesto
inicial de "3" que pesa como PRIOR_WEIGHT notas: así una sola nota no cambia
todo de golpe y el perfil se arma de a poco. Las notas viejas pesan un poco
menos (DECAY), para que el perfil siga los cambios de gustos.

Qué pasa con cada nivel (el usuario lo puede cambiar en el panel):
  3 → se manda por el chat durante la jornada.
  2 → va en el resumen de inicio o cierre de jornada.
  1 → no es blanco o negro: al principio sigue apareciendo en el resumen,
      cada vez menos, y solo deja de aparecer cuando hay suficientes notas que
      confirman que no le interesa (DISCARD_EVIDENCE). Igual se la muestra si
      la pide.
Sin notas suficientes todo sigue como antes (nivel 3).
"""

import datetime as dt
import hashlib
import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Parámetros del aprendizaje ──────────────────────────────────────────
PRIOR_SCORE = 3.0          # sin datos, una noticia cuenta como "muy relevante" (lo de siempre)
PRIOR_WEIGHT = 4.0         # cuántas notas vale ese supuesto inicial
DECAY = 0.97               # cada nota nueva en una clave le resta 3% de peso a las anteriores
CUT_3 = 2.4                # estimado ≥ 2,4 → nivel 3
CUT_2 = 1.6                # estimado ≥ 1,6 → nivel 2; menos → nivel 1
DISCARD_EVIDENCE = 12.0    # notas (ponderadas) necesarias para dar un tema por "no relevante"
DISCARD_SCORE = 1.4        # …con un estimado bajo esto
TIPO_MAX_N = 3.0           # el "tipo" (p. ej. noticias del mercado) empuja, pero solo no basta para bajar un tema
KEY_PRIOR_WEIGHT = 2.0     # para mostrar una clave sola en el panel (una noticia junta 2-3 claves)
KEY_WEIGHT = {"sym": 1.0, "tema": 0.8, "tipo": 0.4}

REF_MAX = 80               # noticias recordadas por usuario para poder calificarlas
DIGEST_MAX = 30
RATE_WINDOW_H = 48         # se puede calificar con "1/2/3" hasta 48 h después
BRIEF_CODES = "abcdefgh"

LEVEL_TEXT = {3: "muy relevante", 2: "algo relevante", 1: "poco relevante"}
DISPLAY_OPTIONS = {
    "level3": ("chat", "resumen"),
    "level2": ("resumen", "chat", "pedido"),
    "level1": ("gradual", "resumen", "pedido"),
}
DISPLAY_DEFAULTS = {"level3": "chat", "level2": "resumen", "level1": "gradual"}

KIND_LABELS = {
    "activo": "Noticias de tus activos",
    "mercado": "Noticias generales del mercado",
    "resultados": "Resultados de empresas",
    "macro": "Datos macroeconómicos",
}

RATE_FOOTER = "¿Qué tan relevante fue? Responde 1, 2 o 3 (3 = muy relevante)."
RATE_MARKER = "Responde 1, 2 o 3"
BUTTONS = (("1", "1 · Poco"), ("2", "2 · Algo"), ("3", "3 · Mucho"))

# ── Temas: palabras clave (titulares de Finnhub vienen en inglés) ───────
THEMES = (
    ("tasas", "Tasas y bancos centrales", ("fed", "fomc", "powell", "rate cut", "rate hike", "interest rate",
                                            "rates", "treasury", "yields", "bond", "central bank", "tasa", "tpm")),
    ("inflacion", "Inflación", ("inflation", "cpi", "pce", "consumer prices", "inflación", "ipc")),
    ("empleo", "Empleo", ("jobs", "payroll", "unemployment", "jobless", "labor market", "hiring", "layoff",
                          "layoffs", "empleo", "desempleo")),
    ("resultados", "Resultados y proyecciones", ("earnings", "quarterly", "revenue", "eps", "guidance", "profit",
                                                 "results", "beats", "misses", "forecast", "outlook", "resultados")),
    ("analistas", "Opiniones de analistas", ("upgrade", "downgrade", "price target", "analyst", "overweight",
                                             "underweight", "outperform", "buy rating", "sell rating", "neutral rating")),
    ("fusiones", "Fusiones y adquisiciones", ("merger", "acquisition", "acquire", "acquires", "buyout", "takeover",
                                              "deal to buy", "stake", "adquisición", "fusión")),
    ("regulacion", "Regulación y juicios", ("regulator", "antitrust", "sec", "ftc", "doj", "lawsuit", "court",
                                            "probe", "investigation", "fine", "fined", "settlement", "ban")),
    ("comercio", "Aranceles y comercio", ("tariff", "tariffs", "trade war", "export control", "export controls",
                                          "sanctions", "arancel", "aranceles")),
    ("geopolitica", "Geopolítica", ("war", "ukraine", "russia", "israel", "iran", "election", "conflict",
                                    "taiwan", "guerra")),
    ("ia_tecnologia", "IA y tecnología", ("ai", "artificial intelligence", "chip", "chips", "semiconductor",
                                          "gpu", "data center", "cloud", "software", "openai")),
    ("energia", "Petróleo y energía", ("oil", "crude", "opec", "natural gas", "energy", "brent", "petróleo")),
    ("cripto", "Cripto", ("bitcoin", "crypto", "ethereum", "btc", "blockchain", "stablecoin")),
    ("dividendos", "Dividendos y recompras", ("dividend", "buyback", "repurchase", "stock split")),
    ("producto", "Productos y lanzamientos", ("launch", "launches", "unveil", "unveils", "new product", "iphone")),
    ("chile", "Chile", ("chile", "chilean", "ipsa", "codelco", "copper", "cobre", "sqm", "falabella", "latam")),
)
THEME_LABELS = {k: label for k, label, _ in THEMES}
THEME_LABELS["general"] = "Mercado en general"
_THEME_RX = [(k, re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.I)) for k, _l, words in THEMES]


def classify(headline: str, summary: str = "") -> list:
    """Hasta dos temas, primero los que aparecen en el titular."""
    head, body = headline or "", summary or ""
    found = [k for k, rx in _THEME_RX if rx.search(head)]
    found += [k for k, rx in _THEME_RX if k not in found and rx.search(body)]
    return found[:2] or ["general"]


def news_id(item: dict) -> str:
    norm = re.sub(r"[^a-z0-9]+", "", (item.get("headline") or "").lower())[:90]
    return hashlib.sha1(f"{item.get('kind')}|{item.get('symbol') or ''}|{norm}".encode()).hexdigest()[:10]


def item_keys(item: dict) -> list:
    """[(clave, etiqueta, peso)] de una noticia."""
    keys = []
    sym = (item.get("symbol") or "").upper()
    if sym:
        keys.append((f"sym:{sym}", sym, KEY_WEIGHT["sym"]))
    themes = item.get("themes") or classify(item.get("headline", ""), item.get("summary", ""))
    for t in themes:
        keys.append((f"tema:{t}", THEME_LABELS.get(t, t), KEY_WEIGHT["tema"] / len(themes)))
    kind = item.get("kind") or "mercado"
    keys.append((f"tipo:{kind}", KIND_LABELS.get(kind, kind), KEY_WEIGHT["tipo"]))
    return keys


def make_item(kind: str, headline: str, summary: str = "", symbol: str = "", url: str = "",
              source: str = "", text: str = "") -> dict:
    """Noticia normalizada. `text` es el mensaje ya formateado (si existe)."""
    it = {"kind": kind, "headline": (headline or "").strip(), "summary": (summary or "")[:400],
          "symbol": (symbol or "").upper(), "url": url or "", "source": source or "", "text": text or ""}
    it["themes"] = classify(it["headline"], it["summary"])
    it["id"] = news_id(it)
    return it


# ── Base de datos ───────────────────────────────────────────────────────

def _prefs(user_id: int, keys: Optional[list] = None) -> dict:
    from finmate.db.models import NewsPreference, get_session

    session = get_session()
    try:
        q = session.query(NewsPreference).filter_by(user_id=user_id)
        if keys is not None:
            q = q.filter(NewsPreference.key.in_(list(keys)))
        return {r.key: {"label": r.label, "sum": r.score_sum, "n": r.weight_n, "ratings": r.ratings,
                        "manual": r.manual_level, "updated_at": r.updated_at} for r in q.all()}
    finally:
        session.close()


def get_display(user_id: int) -> dict:
    from finmate.db.models import NewsDisplaySettings, get_session

    out = dict(DISPLAY_DEFAULTS)
    try:
        session = get_session()
        try:
            row = session.query(NewsDisplaySettings).filter_by(user_id=user_id).one_or_none()
            if row is not None:
                for k in DISPLAY_DEFAULTS:
                    v = getattr(row, k)
                    if v in DISPLAY_OPTIONS[k]:
                        out[k] = v
        finally:
            session.close()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Perfil de noticias: no pude leer la configuración de {user_id}: {e}")
    return out


def set_display(user_id: int, **values) -> dict:
    from finmate.db.models import NewsDisplaySettings, get_session

    for k, v in values.items():
        if k not in DISPLAY_OPTIONS:
            raise ValueError(f"Opción desconocida: {k}.")
        if v is not None and v not in DISPLAY_OPTIONS[k]:
            raise ValueError(f"Para {k} elige entre: {', '.join(DISPLAY_OPTIONS[k])}.")
    session = get_session()
    try:
        row = session.query(NewsDisplaySettings).filter_by(user_id=user_id).one_or_none()
        if row is None:
            row = NewsDisplaySettings(user_id=user_id)
            session.add(row)
        for k, v in values.items():
            if v is not None:
                setattr(row, k, v)
        session.commit()
    finally:
        session.close()
    return get_display(user_id)


# ── Estimación ──────────────────────────────────────────────────────────

def _level(score: float) -> int:
    return 3 if score >= CUT_3 else (2 if score >= CUT_2 else 1)


def estimate(user_id: int, item_or_keys) -> dict:
    """{"score", "evidence", "level", "manual", "discarded"} para una noticia."""
    keys = item_or_keys if isinstance(item_or_keys, list) else item_keys(item_or_keys)
    try:
        prefs = _prefs(user_id, [k for k, _l, _w in keys])
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Perfil de noticias: sin base ({type(e).__name__}); uso el nivel por defecto.")
        prefs = {}
    num, den = PRIOR_SCORE * PRIOR_WEIGHT, PRIOR_WEIGHT
    for k, _label, w in keys:
        p = prefs.get(k)
        if p and p["n"] > 0:
            n, total = p["n"], p["sum"]
            if k.startswith("tipo:") and n > TIPO_MAX_N:      # mismo promedio, menos peso
                total, n = total * TIPO_MAX_N / n, TIPO_MAX_N
            num += w * total
            den += w * n
    score = num / den
    evidence = den - PRIOR_WEIGHT
    manual = None
    for prefix in ("sym:", "tema:", "tipo:"):          # lo más específico manda
        for k, _label, _w in keys:
            if k.startswith(prefix) and (prefs.get(k) or {}).get("manual"):
                manual = manual or prefs[k]["manual"]
    level = manual or _level(score)
    discarded = manual is None and evidence >= DISCARD_EVIDENCE and score < DISCARD_SCORE
    return {"score": round(score, 3), "evidence": round(evidence, 2), "level": level,
            "manual": manual, "discarded": discarded}


def _show_probability(est: dict) -> float:
    """Para nivel 1 "gradual": cada vez menos a medida que el estimado baja."""
    if est["discarded"]:
        return 0.0
    # 100% justo bajo el corte del nivel 2 → 10% al acercarse al descarte (nunca 0 sin confirmar).
    return max(0.1, min(1.0, (est["score"] - DISCARD_SCORE) / (CUT_2 - DISCARD_SCORE)))


def _coin(user_id: int, nid: str) -> float:
    """Número fijo entre 0 y 1 por usuario y noticia (mismo resultado si se repite)."""
    return int(hashlib.sha1(f"{user_id}:{nid}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def route(user_id: int, item: dict, in_workday: bool = True) -> dict:
    """Decide qué hacer con una noticia: {"action": "chat"|"resumen"|"pedido", "level", ...}."""
    est = estimate(user_id, item)
    disp = get_display(user_id)
    level = est["level"]
    if level == 3:
        action = disp["level3"]
    elif level == 2:
        action = disp["level2"]
    else:
        mode = disp["level1"]
        if mode == "pedido":
            action = "pedido"
        elif mode == "resumen":
            action = "resumen"
        elif est["manual"] == 1:
            action = "pedido"              # el usuario lo fijó en 1: no hay nada que confirmar
        else:
            action = "resumen" if _coin(user_id, item["id"]) < _show_probability(est) else "pedido"
    if action == "chat" and not in_workday:
        action = "resumen"                 # fuera de la jornada va al resumen siguiente
    return dict(est, action=action)


# ── Noticias enviadas (para poder calificarlas) ─────────────────────────

def _kv(key, default):
    from finmate.db.state_store import load_json

    return load_json(key, default)


def _kv_save(key, value):
    from finmate.db.state_store import save_json

    save_json(key, value)


def _now() -> str:
    return dt.datetime.utcnow().isoformat(timespec="seconds")


def remember(user_id: int, item: dict, where: str) -> None:
    """Guarda la noticia para poder asociarle la nota que llegue después."""
    refs = _kv(f"newsref:{user_id}", {}) or {}
    refs[item["id"]] = {"keys": [[k, l, w] for k, l, w in item_keys(item)], "headline": item["headline"][:200],
                        "symbol": item.get("symbol", ""), "at": _now(), "where": where}
    if len(refs) > REF_MAX:
        for k in sorted(refs, key=lambda k: refs[k]["at"])[: len(refs) - REF_MAX]:
            del refs[k]
    _kv_save(f"newsref:{user_id}", refs)
    if where == "chat":
        _kv_save(f"newslast:{user_id}", {"id": item["id"], "at": _now()})


def chat_text(item: dict) -> str:
    """El mensaje de la noticia + la invitación a calificarla."""
    body = (item.get("text") or "").strip() or _default_text(item)
    return f"{body}\n\n{RATE_FOOTER}"


def _default_text(item: dict) -> str:
    head = f"📰 {item['symbol']}: {item['headline']}" if item.get("symbol") else f"📰 {item['headline']}"
    lines = [head]
    if item.get("source"):
        lines.append(f"Fuente: {item['source']}")
    if item.get("url"):
        lines.append(item["url"])
    return "\n".join(lines)


def send_to_chat(user_id: int, phone: str, item: dict, messenger) -> bool:
    """Manda la noticia por WhatsApp con botones 1-2-3 (o el texto, si no se puede)."""
    from config.settings import TEMPLATE_MARKET_NOTIFY

    text = chat_text(item)
    if TEMPLATE_MARKET_NOTIFY:
        from finmate.alerts.pending import queue_pending

        queue_pending(phone, text)
        ok = messenger.send_template(phone, TEMPLATE_MARKET_NOTIFY,
                                     {"1": KIND_LABELS.get(item.get("kind"), "Noticia de mercado")})
    elif hasattr(messenger, "send_buttons"):
        body = (item.get("text") or "").strip() or _default_text(item)
        ok = messenger.send_buttons(phone, body + "\n\n¿Qué tan relevante fue?",
                                    [(f"rate:{item['id']}:{n}", t) for n, t in BUTTONS], fallback=text)
    else:
        ok = messenger.send_message(phone, text)
    if ok:
        remember(user_id, item, "chat")
        try:
            from finmate.db.repository import save_turn

            save_turn(user_id, "assistant", text)
        except Exception:  # noqa: BLE001
            pass
    return bool(ok)


def push_digest(user_id: int, item: dict, level: int) -> None:
    items = _kv(f"digest:{user_id}", []) or []
    if any(d.get("id") == item["id"] for d in items):
        return
    items.append({"id": item["id"], "headline": item["headline"][:220], "symbol": item.get("symbol", ""),
                  "kind": item.get("kind"), "source": item.get("source", ""), "level": level, "at": _now()})
    _kv_save(f"digest:{user_id}", items[-DIGEST_MAX:])
    remember(user_id, item, "resumen")


def pop_digest(user_id: int) -> list:
    items = _kv(f"digest:{user_id}", []) or []
    if items:
        _kv_save(f"digest:{user_id}", [])
    return items


def deliver(user_id: int, phone: str, item: dict, messenger, in_workday: bool = True,
            chat_allowed: bool = True) -> str:
    """Punto único para los motores de avisos. Devuelve "chat", "resumen" o "pedido".
    `chat_allowed=False` (p. ej. se llegó al máximo diario) manda al resumen lo que iba al chat."""
    r = route(user_id, item, in_workday=in_workday)
    action = r["action"]
    if action == "chat" and not chat_allowed:
        action = "resumen"
    if action == "chat":
        try:
            from finmate.services.workday import can_message

            if not can_message(user_id):        # ventana de 24 h cerrada: va al resumen en vez de perderse
                action = "resumen"
        except Exception:  # noqa: BLE001
            pass
    if action == "chat":
        if send_to_chat(user_id, phone, item, messenger):
            return "chat"
        action = "resumen"
    if action == "resumen":
        push_digest(user_id, item, r["level"])
        return "resumen"
    remember(user_id, item, "pedido")
    return "pedido"


def assign_brief_codes(user_id: int, items: list) -> list:
    """Letras a), b)… para calificar las noticias del resumen."""
    items = sorted(items, key=lambda d: (-(d.get("level") or 2), d.get("at") or ""))[: len(BRIEF_CODES)]
    codes = {}
    for code, it in zip(BRIEF_CODES, items):
        it["code"] = code
        codes[code] = it["id"]
    _kv_save(f"briefcodes:{user_id}", {"codes": codes, "at": _now()})
    return items


# ── Calificar ───────────────────────────────────────────────────────────

def record_rating(user_id: int, nid: str, rating: int) -> Optional[dict]:
    """Suma la nota a cada clave de la noticia. Devuelve el antes/después o None si no se encontró."""
    from finmate.db.models import NewsPreference, NewsRating, get_session

    rating = int(rating)
    if rating not in (1, 2, 3):
        raise ValueError("La nota va de 1 a 3.")
    ref = (_kv(f"newsref:{user_id}", {}) or {}).get(nid)
    if not ref:
        return None
    keys = [tuple(k) for k in ref["keys"]]
    before = estimate(user_id, keys)
    session = get_session()
    try:
        for k, label, _w in keys:
            row = session.query(NewsPreference).filter_by(user_id=user_id, key=k).one_or_none()
            if row is None:
                row = NewsPreference(user_id=user_id, key=k, label=label, score_sum=0.0, weight_n=0.0, ratings=0)
                session.add(row)
            row.score_sum = (row.score_sum or 0.0) * DECAY + rating
            row.weight_n = (row.weight_n or 0.0) * DECAY + 1.0
            row.ratings = (row.ratings or 0) + 1
            row.label = label
        session.add(NewsRating(user_id=user_id, news_id=nid, rating=rating, keys=json.dumps([k for k, _l, _w in keys]),
                               headline=ref.get("headline", "")[:300]))
        session.commit()
    finally:
        session.close()
    after = estimate(user_id, keys)
    return {"before": before, "after": after, "headline": ref.get("headline", ""), "symbol": ref.get("symbol", ""),
            "labels": [l for _k, l, _w in keys]}


_DEST_TEXT = {"chat": "te seguirán llegando por el chat", "resumen": "irán en tu resumen de jornada",
              "pedido": "solo te las muestro si me preguntas"}


def _ack(rating: int, res: dict, user_id: int) -> str:
    before, after = res["before"], res["after"]
    disp = get_display(user_id)
    if after["level"] == 3:
        dest = disp["level3"]
    elif after["level"] == 2:
        dest = disp["level2"]
    else:
        dest = "pedido" if after["discarded"] or disp["level1"] == "pedido" else "resumen"
    what = res["symbol"] or (res["labels"][0] if res["labels"] else "este tema")
    line = f"Anotado: {rating} ({LEVEL_TEXT[rating]})."
    if after["level"] != before["level"]:
        if dest == "resumen" and after["level"] == 1:
            return f"{line} Noticias como esta de {what} irán apareciendo cada vez menos en tu resumen."
        return f"{line} Desde ahora, noticias como esta de {what} {_DEST_TEXT[dest]}."
    if rating == 1 and after["level"] == 1 and after["discarded"]:
        return f"{line} Ya me quedó claro que esto no te interesa: no te lo mostraré, salvo que me preguntes."
    if rating < before["level"]:
        return f"{line} Voy ajustando de a poco: con unas notas más así, estas noticias bajarán de prioridad."
    return f"{line} Lo tengo en cuenta para tu perfil de noticias."


_RX_SINGLE = re.compile(r"^\s*([123])\s*(?:[-·.]\s*\w+)?\s*[.!]?\s*$")
_RX_CODES = re.compile(r"\b([a-h])\s*[-:=)]?\s*([123])\b", re.I)


def try_handle_rating(user_id: int, text: str, last_assistant: str = "") -> Optional[str]:
    """Si el mensaje es una nota ("3", "a3 b1"), la registra y devuelve la respuesta.
    Si no lo es, devuelve None y el mensaje sigue al agente."""
    t = (text or "").strip()
    if not t or len(t) > 60:
        return None
    try:
        # Notas del resumen: "a3", "b 1", "a3 c2"
        coded = _RX_CODES.findall(t)
        leftover = _RX_CODES.sub("", t).strip(" ,.;y")
        if coded and not leftover:
            data = _kv(f"briefcodes:{user_id}", {}) or {}
            codes = data.get("codes") or {}
            fresh = data.get("at") and dt.datetime.fromisoformat(data["at"]) > dt.datetime.utcnow() - dt.timedelta(hours=RATE_WINDOW_H)
            if codes and fresh:
                done = []
                for code, n in coded:
                    nid = codes.get(code.lower())
                    if nid and record_rating(user_id, nid, int(n)):
                        done.append(f"{code.lower()}{n}")
                if done:
                    return (f"Anotado ({', '.join(done)}). Con esto voy afinando qué noticias te muestro y dónde. "
                            "Puedes revisar y cambiar tu perfil en Ajustes → Tus noticias.")
            return None
        # Nota suelta "3": solo si lo último que mandé fue una noticia para calificar
        m = _RX_SINGLE.match(t)
        if not m or RATE_MARKER not in (last_assistant or "") and "Qué tan relevante" not in (last_assistant or ""):
            return None
        last = _kv(f"newslast:{user_id}", {}) or {}
        if not last.get("id"):
            return None
        if dt.datetime.fromisoformat(last["at"]) < dt.datetime.utcnow() - dt.timedelta(hours=RATE_WINDOW_H):
            return None
        rating = int(m.group(1))
        res = record_rating(user_id, last["id"], rating)
        return _ack(rating, res, user_id) if res else None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Perfil de noticias: no pude registrar la nota de {user_id}: {e}")
        return None


def rate_from_button(user_id: int, button_id: str) -> Optional[str]:
    """Botones 1-2-3 de WhatsApp: id "rate:<noticia>:<nota>"."""
    try:
        _p, nid, n = button_id.split(":", 2)
        res = record_rating(user_id, nid, int(n))
        return _ack(int(n), res, user_id) if res else "Esa noticia ya es antigua, pero gracias: las próximas sí las voy anotando."
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Perfil de noticias: botón inválido {button_id!r}: {e}")
        return None


# ── Perfil para el panel y para el agente ───────────────────────────────

def profile(user_id: int) -> list:
    """Lo aprendido, clave por clave, de lo más a lo menos relevante."""
    out = []
    for k, p in _prefs(user_id).items():
        total, n = p["sum"], p["n"]
        if k.startswith("tipo:") and n > TIPO_MAX_N:          # igual que en estimate(): el tipo pesa poco
            total, n = total * TIPO_MAX_N / n, TIPO_MAX_N
        score = (PRIOR_SCORE * KEY_PRIOR_WEIGHT + total) / (KEY_PRIOR_WEIGHT + n)
        discarded = p["manual"] is None and n >= DISCARD_EVIDENCE / 2 and score < DISCARD_SCORE
        level = p["manual"] or _level(score)
        if p["manual"]:
            status = "fijado"
        elif discarded:
            status = "descartado"
        elif p["n"] < 3:
            status = "aprendiendo"
        else:
            status = "estable"
        out.append({"key": k, "group": k.split(":", 1)[0], "label": p["label"], "score": round(score, 2),
                    "level": level, "ratings": p["ratings"], "manual": p["manual"], "status": status})
    out.sort(key=lambda x: (-x["level"], -x["score"], x["label"]))
    return out


def set_manual(user_id: int, key: str, level: Optional[int]) -> list:
    from finmate.db.models import NewsPreference, get_session

    if level is not None and int(level) not in (1, 2, 3):
        raise ValueError("El nivel va de 1 a 3 (o automático).")
    group = key.split(":", 1)[0]
    if group not in KEY_WEIGHT or ":" not in key:
        raise ValueError("Tema desconocido.")
    session = get_session()
    try:
        row = session.query(NewsPreference).filter_by(user_id=user_id, key=key).one_or_none()
        if row is None:
            label = key.split(":", 1)[1]
            label = THEME_LABELS.get(label) or KIND_LABELS.get(label) or label.upper()
            row = NewsPreference(user_id=user_id, key=key, label=label, score_sum=0.0, weight_n=0.0, ratings=0)
            session.add(row)
        row.manual_level = int(level) if level is not None else None
        session.commit()
    finally:
        session.close()
    return profile(user_id)


def reset_key(user_id: int, key: str) -> list:
    from finmate.db.models import NewsPreference, get_session

    session = get_session()
    try:
        session.query(NewsPreference).filter_by(user_id=user_id, key=key).delete()
        session.commit()
    finally:
        session.close()
    return profile(user_id)


def known_topics() -> list:
    """Temas que se pueden fijar desde el panel aunque todavía no tengan notas."""
    return ([{"key": f"tema:{k}", "label": l} for k, l, _w in THEMES] +
            [{"key": f"tipo:{k}", "label": l} for k, l in KIND_LABELS.items()])


def find_key(text: str) -> Optional[str]:
    """Para el chat: "cripto" → tema:cripto, "NVDA" → sym:NVDA."""
    t = (text or "").strip()
    low = t.lower()
    for k, label, words in THEMES:
        if low in (k, label.lower()) or low in words or (len(low) > 3 and low in label.lower()):
            return f"tema:{k}"
    for k, label in KIND_LABELS.items():
        if low in (k, label.lower()):
            return f"tipo:{k}"
    if re.fullmatch(r"[A-Za-z.\-]{1,10}", t):
        return f"sym:{t.upper()}"
    return None


def profile_text(user_id: int) -> str:
    rows = profile(user_id)
    disp = get_display(user_id)
    head = ("Así ordeno tus noticias: nivel 3 por el chat" if disp["level3"] == "chat" else "Nivel 3 en el resumen")
    head += (", nivel 2 en el resumen" if disp["level2"] == "resumen" else
             ", nivel 2 por el chat" if disp["level2"] == "chat" else ", nivel 2 solo si me preguntas")
    head += (", nivel 1 cada vez menos hasta confirmar que no te interesa." if disp["level1"] == "gradual" else
             ", nivel 1 en el resumen." if disp["level1"] == "resumen" else ", nivel 1 solo si me preguntas.")
    if not rows:
        return head + "\nTodavía no tengo notas tuyas: por ahora todo te llega como antes."
    lines = [head, ""]
    for r in rows[:20]:
        extra = {"fijado": " (fijado por ti)", "descartado": " (ya no te lo muestro)",
                 "aprendiendo": " (aprendiendo)"}.get(r["status"], "")
        lines.append(f"• {r['label']}: nivel {r['level']}{extra}, {r['ratings']} nota(s)")
    return "\n".join(lines)


def tool_get_news_profile(user_id: int, _input: dict = None) -> str:
    return profile_text(user_id)


def tool_set_news_preference(user_id: int, tool_input: dict) -> str:
    topic = (tool_input.get("topic") or "").strip()
    level = tool_input.get("level")
    key = find_key(topic)
    if not key:
        return f"No reconocí el tema '{topic}'. Puede ser un ticker (NVDA) o un tema: " + \
               ", ".join(l for _k, l, _w in THEMES) + "."
    if level in (None, "auto", "automatico", "automático", 0):
        set_manual(user_id, key, None)
        return f"Listo: {key.split(':', 1)[1]} vuelve a modo automático (aprendo de tus notas)."
    set_manual(user_id, key, int(level))
    return f"Listo: fijé {key.split(':', 1)[1]} en nivel {int(level)} ({LEVEL_TEXT[int(level)]})."
