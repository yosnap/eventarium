"""Tokens de un solo uso para verificación de correo.

Reutiliza el patrón de Redis+TTL de los refresh tokens: token opaco, de él solo se
guarda su huella, y «un solo uso» se implementa borrando la clave al consumirla
(`GETDEL`, atómico: evita una carrera entre comprobar y borrar). Cada token lleva su
**propósito** en la clave, así que un token de verificación de correo nunca sirve para
otro fin, aunque una fase posterior (cambio de correo, recuperación de contraseña)
comparta el mismo mecanismo.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta

from app.core.redis_client import require_redis

TTL_TOKEN = timedelta(hours=24)

PROPOSITO_VERIFICACION_CORREO = "email_verify"

_CLAVE = "verify:{proposito}:{huella}"


def _huella(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def generate_token(proposito: str, user_id: uuid.UUID) -> str:
    """Genera y guarda un token opaco de un solo uso para el propósito indicado."""
    token = secrets.token_urlsafe(32)
    redis = await require_redis()
    await redis.set(
        _CLAVE.format(proposito=proposito, huella=_huella(token)),
        str(user_id),
        ex=TTL_TOKEN,
    )
    return token


async def consume_token(proposito: str, token: str) -> uuid.UUID | None:
    """Consume el token si existe y no ha caducado. `None` si no es válido."""
    redis = await require_redis()
    clave = _CLAVE.format(proposito=proposito, huella=_huella(token))
    bruto = await redis.getdel(clave)
    if bruto is None:
        return None
    return uuid.UUID(bruto)
