"""
Estado persistente de los avisos (dedup, colas) guardado en la base de datos.

Antes cada módulo guardaba su estado en un archivo JSON dentro del servidor.
En Railway ese disco se borra en cada redeploy, así que tras un reinicio el
bot "olvidaba" qué ya había avisado y repetía alertas (23 nov 2026: la misma
alerta de NVDA llegó 7 veces). Ahora el JSON vive en la tabla `kv_state`.

Si no hay base de datos configurada (o falla), se usa el archivo de siempre,
así el comportamiento en desarrollo y en tests sin DATABASE_URL no cambia.
La clave es el mismo nombre de archivo que usaba cada módulo; la primera vez
que se lee una clave que no está en la base, se importa el archivo si existe.
"""
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _db_load(key: str):
    try:
        from finmate.db.models import KVState, get_session

        session = get_session()
    except Exception:
        return None, False
    try:
        row = session.get(KVState, key)
        return (json.loads(row.value) if row else None), True
    except Exception as e:
        logger.error(f"No pude leer el estado '{key}' de la base: {e}")
        return None, False
    finally:
        session.close()


def _db_save(key: str, data: Any) -> bool:
    try:
        from finmate.db.models import KVState, get_session

        session = get_session()
    except Exception:
        return False
    try:
        value = json.dumps(data, ensure_ascii=False)
        row = session.get(KVState, key)
        if row is None:
            session.add(KVState(key=key, value=value))
        else:
            row.value = value
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"No pude guardar el estado '{key}' en la base: {e}")
        return False
    finally:
        session.close()


def _file_load(path: str):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def load_json(key: str, default: Any) -> Any:
    """Estado guardado bajo `key`, o `default` si no hay nada."""
    data, db_ok = _db_load(key)
    if data is not None:
        return data
    data = _file_load(key)
    if data is not None:
        if db_ok:
            _db_save(key, data)  # migra el archivo viejo a la base
        return data
    return default


def save_json(key: str, data: Any) -> None:
    """Guarda en la base; si no hay base o falla, en el archivo."""
    if _db_save(key, data):
        return
    try:
        with open(key, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        logger.error(f"No pude guardar el estado '{key}': {e}")
