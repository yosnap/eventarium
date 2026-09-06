"""Lógica de autenticación: credenciales y ciclo de vida del refresh token.

Modelo de refresh tokens (rotación con detección de reutilización):

- Cada login abre una *familia*. Cada refresh emite un token nuevo y retira el
  anterior, dejándolo marcado como «ya usado».
- Si llega un token que consta como ya usado, se asume robo: se revoca la familia
  entera, no solo ese token.
- Todo el estado vive en Redis con TTL. Si Redis no responde, se responde 503; nunca
  se acepta un token sin poder comprobar su revocación.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis_client import require_redis
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
)
from app.shared.errors import AuthenticationError

CLAVE_ACTIVO = "refresh:activo:{}"
CLAVE_USADO = "refresh:usado:{}"
CLAVE_FAMILIA = "refresh:familia:{}"


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Usuario validado durante el login."""

    id: uuid.UUID
    email: str
    full_name: str
    is_superadmin: bool


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    """Par de tokens emitidos."""

    access_token: str
    refresh_token: str
    expires_in: int


def _ttl_refresh() -> timedelta:
    return timedelta(days=get_settings().refresh_token_ttl_days)


async def authenticate(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    organization_id: uuid.UUID,
) -> AuthenticatedUser:
    """Valida credenciales contra un usuario que pertenezca a la organización.

    La consulta exige membresía: un usuario existente en otra organización no puede
    entrar por este host. El mensaje de error es el mismo tanto si el correo no
    existe como si la contraseña es incorrecta, para no revelar qué correos hay.
    """
    fila = (
        await session.execute(
            text(
                "SELECT u.id, u.email, u.full_name, u.password_hash, u.is_active, u.is_superadmin "
                "FROM users u "
                "WHERE lower(u.email) = lower(:email) "
                "  AND EXISTS (SELECT 1 FROM organization_members m "
                "              WHERE m.user_id = u.id AND m.organization_id = :org_id)"
            ),
            {"email": email, "org_id": organization_id},
        )
    ).first()

    credenciales_invalidas = AuthenticationError("Credenciales no válidas.")
    if fila is None:
        # Se verifica igualmente un hash ficticio para no filtrar por tiempo de respuesta.
        verify_password(password, None)
        raise credenciales_invalidas
    if not fila[4] or not verify_password(password, fila[3]):
        raise credenciales_invalidas

    return AuthenticatedUser(id=fila[0], email=fila[1], full_name=fila[2], is_superadmin=fila[5])


async def issue_tokens(
    usuario: AuthenticatedUser,
    organization_id: uuid.UUID,
    *,
    family_id: str | None = None,
) -> IssuedTokens:
    """Emite access + refresh y registra el refresh en su familia."""
    settings = get_settings()
    redis = await require_redis()

    familia = family_id or uuid.uuid4().hex
    refresh = generate_refresh_token()
    huella = hash_refresh_token(refresh)
    ttl = _ttl_refresh()

    datos = json.dumps(
        {
            "user_id": str(usuario.id),
            "org_id": str(organization_id),
            "family": familia,
        }
    )
    async with redis.pipeline(transaction=True) as tuberia:
        tuberia.set(CLAVE_ACTIVO.format(huella), datos, ex=ttl)
        tuberia.sadd(CLAVE_FAMILIA.format(familia), huella)
        tuberia.expire(CLAVE_FAMILIA.format(familia), ttl)
        await tuberia.execute()

    return IssuedTokens(
        access_token=create_access_token(
            usuario.id, organization_id, is_superadmin=usuario.is_superadmin
        ),
        refresh_token=refresh,
        expires_in=settings.access_token_ttl_minutes * 60,
    )


async def _revoke_family(familia: str) -> None:
    """Invalida todos los refresh tokens de una familia."""
    redis = await require_redis()
    clave = CLAVE_FAMILIA.format(familia)
    huellas: set[str] = await redis.smembers(clave)  # type: ignore[misc]
    async with redis.pipeline(transaction=True) as tuberia:
        for huella in huellas:
            tuberia.delete(CLAVE_ACTIVO.format(huella))
            tuberia.delete(CLAVE_USADO.format(huella))
        tuberia.delete(clave)
        await tuberia.execute()


async def rotate_refresh_token(
    session: AsyncSession, refresh_token: str
) -> tuple[IssuedTokens, uuid.UUID]:
    """Consume un refresh token y emite uno nuevo de la misma familia.

    Devuelve los tokens y la organización a la que pertenecen.
    """
    redis = await require_redis()
    huella = hash_refresh_token(refresh_token)

    bruto = await redis.get(CLAVE_ACTIVO.format(huella))
    if bruto is None:
        # ¿Es un token ya rotado? Entonces alguien está reutilizando uno robado.
        familia_usada = await redis.get(CLAVE_USADO.format(huella))
        if familia_usada:
            await _revoke_family(familia_usada)
            raise AuthenticationError(
                "Sesión invalidada por reutilización de un token. Vuelve a iniciar sesión."
            )
        raise AuthenticationError("La sesión ha caducado. Vuelve a iniciar sesión.")

    datos = json.loads(bruto)
    user_id = uuid.UUID(datos["user_id"])
    organization_id = uuid.UUID(datos["org_id"])
    familia = str(datos["family"])

    fila = (
        await session.execute(
            text(
                "SELECT u.id, u.email, u.full_name, u.is_superadmin "
                "FROM users u "
                "WHERE u.id = :id AND u.is_active "
                "  AND EXISTS (SELECT 1 FROM organization_members m "
                "              WHERE m.user_id = u.id AND m.organization_id = :org_id)"
            ),
            {"id": user_id, "org_id": organization_id},
        )
    ).first()
    if fila is None:
        await _revoke_family(familia)
        raise AuthenticationError("El usuario ya no tiene acceso a esta organización.")

    ttl = _ttl_refresh()
    async with redis.pipeline(transaction=True) as tuberia:
        tuberia.delete(CLAVE_ACTIVO.format(huella))
        tuberia.set(CLAVE_USADO.format(huella), familia, ex=ttl)
        await tuberia.execute()

    usuario = AuthenticatedUser(id=fila[0], email=fila[1], full_name=fila[2], is_superadmin=fila[3])
    tokens = await issue_tokens(usuario, organization_id, family_id=familia)
    return tokens, organization_id


async def revoke_refresh_token(refresh_token: str) -> None:
    """Cierra la sesión revocando la familia completa del token."""
    redis = await require_redis()
    huella = hash_refresh_token(refresh_token)
    bruto = await redis.get(CLAVE_ACTIVO.format(huella))
    if bruto is not None:
        await _revoke_family(str(json.loads(bruto)["family"]))
        return
    familia_usada = await redis.get(CLAVE_USADO.format(huella))
    if familia_usada:
        await _revoke_family(familia_usada)
