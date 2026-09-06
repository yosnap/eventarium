"""Cliente Redis compartido por autenticación y rate limiting.

Redis es una dependencia crítica: si no está disponible no se puede comprobar la
revocación de un refresh token ni aplicar límites de peticiones. En ese caso se
responde 503 (fail-closed); nunca se continúa como si el token fuera válido.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.shared.errors import ServiceUnavailableError

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Cliente Redis único (pool interno gestionado por la librería)."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = aioredis.from_url(  # type: ignore[no-untyped-call]
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _client


async def require_redis() -> aioredis.Redis:
    """Devuelve el cliente solo si responde; si no, 503."""
    cliente = get_redis()
    try:
        await cliente.ping()
    except Exception as exc:
        raise ServiceUnavailableError(
            "El servicio de sesiones no está disponible. Inténtalo de nuevo."
        ) from exc
    return cliente


async def redis_healthy() -> bool:
    """Comprobación para el health-check, sin lanzar excepciones."""
    try:
        await get_redis().ping()
        return True
    except Exception:
        return False


async def close_redis() -> None:
    """Cierra el cliente al apagar la aplicación."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
