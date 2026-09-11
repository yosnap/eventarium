"""Sesiones de impersonación: entrada, salida y su revocación.

Un administrador de la plataforma puede entrar a la cuenta de una persona para
ver lo que ella ve (reproducir una incidencia). La sesión es de **solo
lectura** y tiene su propia caducidad, más corta que una normal.

La revocación vive en Redis y no en el token: un access token es un JWT sin
estado, así que «salir» no puede invalidarlo por sí solo. Se guarda una clave
por sesión (`impersonacion:{jti}`) que `get_token_claims` consulta en cada
petición; al salir se borra, y el token deja de valer de inmediato sin esperar
a su `exp`.

El valor de la clave guarda quién suplanta y el id de sesión, para que la
salida pueda registrar la misma sesión que la entrada (y así emparejar ambas
en la auditoría).
"""

from __future__ import annotations

import json
import uuid

from app.core.redis_client import get_redis

#: Prefijo de la clave de sesión activa.
_PREFIJO = "impersonacion:"


def _clave(jti: str) -> str:
    return f"{_PREFIJO}{jti}"


async def abrir_sesion(
    *, jti: str, admin_id: uuid.UUID, session_id: str, segundos: int
) -> None:
    """Marca una sesión de impersonación como activa durante `segundos`."""
    await get_redis().set(
        _clave(jti),
        json.dumps({"admin": str(admin_id), "sesion": session_id}),
        ex=segundos,
    )


async def sesion_activa(jti: str) -> bool:
    """Indica si la sesión de impersonación sigue viva.

    Un token sin clave asociada (porque se salió, o porque la clave caducó
    antes que el token) se considera revocado: fail-closed.
    """
    return bool(await get_redis().exists(_clave(jti)))


async def datos_de_sesion(jti: str) -> dict[str, str] | None:
    """Quién suplanta y con qué id de sesión, o `None` si ya no está activa."""
    crudo = await get_redis().get(_clave(jti))
    if crudo is None:
        return None
    valor: dict[str, str] = json.loads(crudo)
    return valor


async def cerrar_sesion(jti: str) -> None:
    """Revoca una sesión de impersonación de inmediato."""
    await get_redis().delete(_clave(jti))
