"""
Finmate - Tools de personalidad configurable.

Permiten al usuario ver y cambiar cómo se comporta Finmate (humor, sarcasmo,
frecuencia de chistes, nivel conversador y tono) directamente desde WhatsApp.

Los datos se persisten en DB a través de finmate.db.personality_repo.
Si la DB no está disponible el import falla silenciosamente y las tools
devuelven un mensaje de error amigable.
"""
import logging

logger = logging.getLogger(__name__)

try:
    from finmate.db.personality_repo import get_personality as _get_personality
    from finmate.db.personality_repo import set_personality as _set_personality
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False
    logger.warning("finmate.db.personality_repo no disponible — tools de personalidad deshabilitadas.")


_TONO_VALIDOS = {"profesional", "casual", "amigo"}
_INT_PARAMS = {"humor", "sarcasmo", "frecuencia_chistes", "nivel_conversador"}

_DB_ERROR_MSG = (
    "❌ No pude acceder a tu configuración de personalidad en este momento "
    "(problema de base de datos). Probá de nuevo en unos minutos."
)


def tool_get_personality(user_id: int) -> str:
    """Devuelve la configuración de personalidad actual formateada para WhatsApp."""
    if not _DB_AVAILABLE:
        return _DB_ERROR_MSG

    try:
        p = _get_personality(user_id)
    except Exception as e:
        logger.error(f"Error leyendo personalidad de user_id={user_id}: {e}", exc_info=True)
        return _DB_ERROR_MSG

    tono = p.get("tono", "profesional")
    humor = p.get("humor", 5)
    sarcasmo = p.get("sarcasmo", 3)
    frecuencia = p.get("frecuencia_chistes", 3)
    nivel = p.get("nivel_conversador", 5)

    return (
        "*Tu configuración de Finmate*\n\n"
        f"🎭 Humor: {humor}/10\n"
        f"😏 Sarcasmo: {sarcasmo}/10\n"
        f"😄 Frecuencia de chistes: {frecuencia}/10\n"
        f"💬 Nivel conversador: {nivel}/10\n"
        f"🗣 Tono: {tono}\n\n"
        "Decime qué querés cambiar: ej. \"poneme el tono en amigo\" o \"más humor, más chistes\"."
    )


def tool_set_personality(user_id: int, tool_input: dict) -> str:
    """Valida y guarda uno o más parámetros de personalidad. Devuelve confirmación."""
    if not _DB_AVAILABLE:
        return _DB_ERROR_MSG

    if not tool_input:
        return "⚠️ No me indicaste qué parámetro querés cambiar."

    # Validar
    errors = []
    kwargs = {}

    for key, value in tool_input.items():
        if key in _INT_PARAMS:
            try:
                v = int(value)
            except (TypeError, ValueError):
                errors.append(f"'{key}' debe ser un número entre 1 y 10.")
                continue
            if not (1 <= v <= 10):
                errors.append(f"'{key}' debe estar entre 1 y 10 (recibí {v}).")
                continue
            kwargs[key] = v

        elif key == "tono":
            v = str(value).lower().strip()
            if v not in _TONO_VALIDOS:
                errors.append(f"El tono debe ser 'profesional', 'casual' o 'amigo' (recibí '{value}').")
                continue
            kwargs[key] = v

        else:
            errors.append(f"Parámetro desconocido: '{key}'.")

    if errors:
        return "⚠️ " + " ".join(errors)

    if not kwargs:
        return "⚠️ No hay nada válido para guardar."

    try:
        updated = _set_personality(user_id, **kwargs)
    except Exception as e:
        logger.error(f"Error guardando personalidad de user_id={user_id}: {e}", exc_info=True)
        return _DB_ERROR_MSG

    tono = updated.get("tono", "profesional")
    humor = updated.get("humor", 5)
    sarcasmo = updated.get("sarcasmo", 3)
    frecuencia = updated.get("frecuencia_chistes", 3)
    nivel = updated.get("nivel_conversador", 5)

    changed = ", ".join(
        f"{k}={v}" for k, v in kwargs.items()
    )

    return (
        f"✅ Personalidad actualizada ({changed}).\n\n"
        "*Tu nueva configuración*\n\n"
        f"🎭 Humor: {humor}/10\n"
        f"😏 Sarcasmo: {sarcasmo}/10\n"
        f"😄 Frecuencia de chistes: {frecuencia}/10\n"
        f"💬 Nivel conversador: {nivel}/10\n"
        f"🗣 Tono: {tono}"
    )
