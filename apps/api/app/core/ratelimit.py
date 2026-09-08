"""Límites de peticiones sobre Redis.

Ventana fija con `INCR` + `EXPIRE`: la primera petición de la ventana crea la clave y
le pone caducidad, y las siguientes solo incrementan. Basta para frenar fuerza bruta
contra el login y no necesita estructuras de datos adicionales.

La identificación del cliente usa la IP real solo cuando la petición llega por un
proxy de confianza; si no, cualquiera podría rotar `X-Forwarded-For` y saltarse el
límite. Se combina con el host para que el límite por organización sea independiente.

Fail-closed: si Redis no responde no se puede contar, así que se rechaza con 503 en
lugar de dejar pasar la petición sin control.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, Request

from app.core.redis_client import require_redis
from app.core.tenant import extract_host, is_trusted_proxy
from app.shared.errors import DomainError

# Límites iniciales (peticiones por minuto).
LOGIN_POR_IP = 5
LOGIN_POR_HOST = 20
REFRESH_POR_IP = 30
PUBLICO_POR_IP = 120
# El registro es de un solo uso por persona: algo más permisivo que el login.
REGISTRO_POR_IP = 10
# El reenvío es reutilizable y encola correo: más estricto, además de exigir Turnstile.
REENVIO_VERIFICACION_POR_IP = 3
# El token tiene 256 bits de entropía (no es adivinable), pero el endpoint sigue
# necesitando un tope propio para no quedar como el único público sin ninguno.
VERIFICACION_CORREO_POR_IP = 20
# Creación de organización: de un solo uso legítimo por persona, como el registro.
CREAR_ORGANIZACION_POR_IP = 10
# check-slug es solo ayuda de UX (debounce en el cliente), pero necesita su propio
# tope: sin Turnstile ni cuenta detrás, es el candidato más fácil a escaneo.
CHECK_SLUG_POR_IP = 30
# Mismo riesgo de *email bombing* que el reenvío de verificación: reutilizable y
# encola correo, con Turnstile obligatorio delante.
FORGOT_PASSWORD_POR_IP = 3
# El token tiene 256 bits de entropía, pero el endpoint necesita su propio tope, igual
# que verify-email.
RESET_PASSWORD_POR_IP = 20
# Inscripción a un evento: de un solo uso legítimo por persona y evento, como el
# registro de cuentas.
INSCRIPCION_POR_IP = 10
# Mismo razonamiento que verify-email: el token tiene entropía de sobra, pero el
# endpoint necesita su propio tope por ser público.
VERIFICACION_INSCRIPCION_POR_IP = 20
# Confirmación de una promoción de lista de espera: mismo razonamiento que
# verify-email, token con entropía de sobra pero tope propio por ser público.
CONFIRMACION_PROMOCION_POR_IP = 20
# Autocancelación: mismo razonamiento que confirm-waitlist-promotion.
CANCELACION_INSCRIPCION_POR_IP = 20
# `/mi-entrada` (fase 4 del PRD): a diferencia de verify/cancel, es un enlace
# pensado para volver a visitarlo varias veces, no de un solo uso — mismo
# tope que el resto de endpoints públicos con token de sobra entropía.
MI_ENTRADA_POR_IP = 20

VENTANA_SEGUNDOS = 60


class TooManyRequestsError(DomainError):
    status_code = 429
    title = "Demasiadas peticiones"


def client_ip(request: Request) -> str:
    """IP real del cliente, teniendo en cuenta el proxy de confianza."""
    directa = request.client.host if request.client else "desconocida"
    if is_trusted_proxy(directa):
        reenviada = request.headers.get("x-forwarded-for")
        if reenviada:
            return reenviada.split(",")[0].strip()
    return directa


def identify_by_ip(request: Request) -> str:
    return f"ip:{client_ip(request)}"


def identify_by_host(request: Request) -> str:
    return f"host:{extract_host(request)}"


async def _consumir(clave: str, veces: int, segundos: int) -> None:
    redis = await require_redis()
    async with redis.pipeline(transaction=True) as tuberia:
        tuberia.incr(clave)
        tuberia.expire(clave, segundos, nx=True)
        resultado = await tuberia.execute()

    consumidas = int(resultado[0])
    if consumidas > veces:
        restante = await redis.ttl(clave)
        raise TooManyRequestsError(
            "Has superado el límite de peticiones. Inténtalo de nuevo en unos instantes.",
            extra={"retry_after": max(1, restante)},
        )


def _limite(
    nombre: str,
    identificador: Callable[[Request], str],
    veces: int,
    segundos: int,
) -> Callable[[Request], Awaitable[None]]:
    async def dependencia(request: Request) -> None:
        await _consumir(f"ratelimit:{nombre}:{identificador(request)}", veces, segundos)

    return dependencia


# `Depends(...)` devuelve un marcador de FastAPI que no es utilizable como anotación
# de tipo, así que estas fábricas se declaran como `Any`.
def limit_per_ip(nombre: str, veces: int, segundos: int = VENTANA_SEGUNDOS) -> Any:
    """Límite por IP de origen."""
    return Depends(_limite(nombre, identify_by_ip, veces, segundos))


def limit_per_host(nombre: str, veces: int, segundos: int = VENTANA_SEGUNDOS) -> Any:
    """Límite por host, es decir por organización."""
    return Depends(_limite(nombre, identify_by_host, veces, segundos))
