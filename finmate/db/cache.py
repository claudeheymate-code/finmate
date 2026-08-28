"""
Finmate - Cache liviano sobre Redis (Fase 0).

Uso: evitar golpear las APIs financieras con requests repetidos en
segundos cuando varios mensajes piden lo mismo. No es almacenamiento de
negocio (eso vive en Postgres) — si Redis no está configurado o falla,
el agente sigue funcionando, solo que sin cache.
"""
import logging

import redis

from config.settings import REDIS_URL

logger = logging.getLogger(__name__)

_redis_client = None
if REDIS_URL:
    try:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
    except Exception as e:
        logger.error(f"No se pudo inicializar el cliente de Redis, se sigue sin cache: {e}")
        _redis_client = None
else:
    logger.info("REDIS_URL no configurada — el agente funciona sin cache.")


def cached(key: str, ttl_seconds: int, compute) -> str:
    """Devuelve el valor cacheado en `key`, o lo calcula con `compute()` y lo guarda."""
    if _redis_client is None:
        return compute()
    try:
        value = _redis_client.get(key)
        if value is not None:
            return value
        value = compute()
        _redis_client.setex(key, ttl_seconds, value)
        return value
    except Exception as e:
        logger.error(f"Error usando Redis cache ({key}), se calcula sin cache: {e}")
        return compute()
