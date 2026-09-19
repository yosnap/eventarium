"""Geocodificación de direcciones con Nominatim (OpenStreetMap).

Gratuito y sin API key, a cambio de una política de uso estricta: cabecera
`User-Agent` identificando la aplicación y como máximo 1 petición por segundo
desde este proceso — ver https://operations.osmfoundation.org/policies/nominatim/.
El espaciado se aplica con un `asyncio.Lock` a nivel de módulo, así que toda
llamada concurrente dentro del mismo proceso queda serializada y respeta el
mínimo, sin necesitar un limitador más sofisticado (colas, tokens, etc.) para
el volumen esperado de altas/ediciones de sedes.

Fail-open, mismo patrón que `auth.service._password_filtrada`: un fallo de red
o de parseo nunca debe bloquear guardar una sede o un evento, solo implica que
no se podrá mostrar el mapa hasta la siguiente edición de la dirección.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "Eventarium/1.0 (contacto: soporte@eventarium.example)"
INTERVALO_MINIMO_SEGUNDOS = 1.0

_lock = asyncio.Lock()
_ultima_llamada: float = 0.0


async def _esperar_turno() -> None:
    """Fuerza al menos `INTERVALO_MINIMO_SEGUNDOS` entre el final de una llamada
    y el inicio de la siguiente, serializando las llamadas concurrentes con un
    `asyncio.Lock` para que el espaciado se cumpla también bajo concurrencia."""
    global _ultima_llamada
    async with _lock:
        transcurrido = time.monotonic() - _ultima_llamada
        restante = INTERVALO_MINIMO_SEGUNDOS - transcurrido
        if restante > 0:
            await asyncio.sleep(restante)
        _ultima_llamada = time.monotonic()


async def geocode_address(address: str) -> tuple[float, float] | None:
    """Geocodifica `address` con Nominatim y devuelve `(latitud, longitud)`.

    Devuelve `None` si la dirección no se pudo geocodificar (sin resultados,
    fallo de red, respuesta inesperada) — nunca lanza. Función pura: no toca
    base de datos, cachear el resultado es responsabilidad de quien la llama.
    """
    if not address.strip():
        return None

    await _esperar_turno()

    try:
        async with httpx.AsyncClient(timeout=5.0) as cliente:
            respuesta = await cliente.get(
                NOMINATIM_URL,
                params={"format": "json", "q": address, "limit": 1},
                headers={"User-Agent": USER_AGENT},
            )
            respuesta.raise_for_status()
            resultados = respuesta.json()
    except httpx.HTTPError:
        logger.warning("Nominatim no disponible al geocodificar; se continúa (fail-open).")
        return None
    except ValueError:
        logger.warning("Respuesta de Nominatim no es JSON válido; se continúa (fail-open).")
        return None

    if not resultados:
        return None

    try:
        primero = resultados[0]
        return (float(primero["lat"]), float(primero["lon"]))
    except (KeyError, TypeError, ValueError):
        logger.warning("Respuesta de Nominatim con forma inesperada; se continúa (fail-open).")
        return None
