"""Fechas y horas en la zona horaria de cada evento, para los correos.

Los instantes se guardan en UTC; a la persona hay que darle la hora de su
evento. Una zona que `zoneinfo` no conoce (datos antiguos, anteriores a la
validación) no rompe el envío: se usa la zona por defecto y se registra.

El formato sigue el idioma del texto (el del contexto si no se indica otro):
`18/11/2026 18:30` en español y `11/18/2026 6:30 PM` en inglés. Se construye a
mano y no con `strftime("%p")` ni `locale.setlocale`: ambos dependen del
idioma del sistema del servidor, no del de quien lee el correo.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.locale import Locale, idioma_actual

logger = logging.getLogger(__name__)

ZONA_POR_DEFECTO = "Europe/Madrid"


def zona(nombre: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(nombre or ZONA_POR_DEFECTO)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Zona horaria desconocida %r: se usa %s.", nombre, ZONA_POR_DEFECTO)
        return ZoneInfo(ZONA_POR_DEFECTO)


def fecha(dia: date, locale: Locale | None = None) -> str:
    """«21/10/2026» en español, «10/21/2026» en inglés."""
    if (locale or idioma_actual()) == "en-US":
        return f"{dia.month:02d}/{dia.day:02d}/{dia.year}"
    return f"{dia.day:02d}/{dia.month:02d}/{dia.year}"


def fecha_y_hora(instante: datetime, nombre_zona: str | None, locale: Locale | None = None) -> str:
    """«21/10/2026 18:00» (o «10/21/2026 6:00 PM» en inglés), en la zona del evento."""
    local = instante.astimezone(zona(nombre_zona))
    destino = locale or idioma_actual()
    if destino == "en-US":
        hora = local.hour % 12 or 12
        sufijo = "AM" if local.hour < 12 else "PM"
        return f"{fecha(local.date(), destino)} {hora}:{local.minute:02d} {sufijo}"
    return f"{fecha(local.date(), destino)} {local.hour:02d}:{local.minute:02d}"
