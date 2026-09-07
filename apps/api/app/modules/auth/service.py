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

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis_client import require_redis
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.core.tasks import send_verification_email
from app.modules.auth.verification import (
    PROPOSITO_VERIFICACION_CORREO,
    consume_token,
    generate_token,
)
from app.shared.errors import AuthenticationError, ValidationDomainError
from app.shared.identifiers import new_uuid7

CLAVE_ACTIVO = "refresh:activo:{}"
CLAVE_USADO = "refresh:usado:{}"
CLAVE_FAMILIA = "refresh:familia:{}"

PWNED_PASSWORDS_URL = "https://api.pwnedpasswords.com/range/{prefijo}"

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Usuario validado durante el login."""

    id: uuid.UUID
    email: str
    first_name: str | None
    last_name: str | None
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
                "SELECT u.id, u.email, u.first_name, u.last_name, u.password_hash, "
                "       u.is_active, u.is_superadmin "
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
    if not fila[5] or not verify_password(password, fila[4]):
        raise credenciales_invalidas

    return AuthenticatedUser(
        id=fila[0], email=fila[1], first_name=fila[2], last_name=fila[3], is_superadmin=fila[6]
    )


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
                "SELECT u.id, u.email, u.first_name, u.last_name, u.is_superadmin "
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

    usuario = AuthenticatedUser(
        id=fila[0], email=fila[1], first_name=fila[2], last_name=fila[3], is_superadmin=fila[4]
    )
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


async def _password_filtrada(password: str) -> bool:
    """Comprueba la contraseña contra HaveIBeenPwned con k-anonymity.

    Solo viaja el prefijo de 5 caracteres del hash SHA-1; la contraseña en claro nunca
    sale del proceso. **Fail-open**: si el servicio no responde, el registro continúa
    y se registra un aviso — no es un control de sesión crítico como el refresh token.
    """
    huella = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()  # noqa: S324
    prefijo, sufijo = huella[:5], huella[5:]
    try:
        async with httpx.AsyncClient(timeout=3.0) as cliente:
            respuesta = await cliente.get(PWNED_PASSWORDS_URL.format(prefijo=prefijo))
            respuesta.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Servicio de contraseñas filtradas no disponible; se continúa (fail-open).")
        return False
    for linea in respuesta.text.splitlines():
        candidato, _, _ = linea.partition(":")
        if candidato == sufijo:
            return True
    return False


async def register_user(session: AsyncSession, *, email: str, password: str) -> None:
    """Registra una cuenta y encola el correo de verificación.

    Siempre se comporta igual exista o no la cuenta ya: la respuesta al llamador no
    debe permitir averiguar qué correos están registrados. La visibilidad normal de
    `users` bajo RLS exige compartir organización con quien pregunta, algo que no
    existe todavía en el registro; por eso la búsqueda y la creación usan las
    funciones `SECURITY DEFINER` de alcance mínimo `app_find_user_by_email` y
    `app_create_unverified_user`, en vez de exponer la tabla sin contexto.

    El hash de la contraseña se calcula **siempre**, exista ya la cuenta o no: es el
    coste dominante de la petición (Argon2id es deliberadamente lento) y, si solo se
    calculara al crear la cuenta, el tiempo de respuesta delataría por sí mismo si el
    correo ya estaba registrado — el mismo motivo por el que `authenticate()` verifica
    un hash ficticio cuando el usuario no existe.
    """
    if await _password_filtrada(password):
        raise ValidationDomainError(
            "Esta contraseña aparece en filtraciones conocidas. Elige otra."
        )

    password_hash = hash_password(password)

    existente = (
        await session.execute(
            text("SELECT id FROM app_find_user_by_email(:email)"), {"email": email}
        )
    ).first()
    if existente is not None:
        return

    user_id = new_uuid7()
    try:
        await session.execute(
            text("SELECT app_create_unverified_user(:id, :email, :hash)"),
            {
                "id": user_id,
                "email": email,
                "hash": password_hash,
            },
        )
    except IntegrityError:
        # Condición de carrera con otro registro simultáneo del mismo correo: el
        # `UNIQUE` de la base de datos es la única fuente de verdad. Misma respuesta.
        return

    token = await generate_token(PROPOSITO_VERIFICACION_CORREO, user_id)
    await send_verification_email.kiq(email, token)


async def verify_email(session: AsyncSession, *, token: str) -> uuid.UUID:
    """Verifica un token, marca el correo como verificado y devuelve el `user_id`.

    El llamador usa el id para emitir el token puente sin organización (fase 2:
    autoservicio de creación de organizaciones).
    """
    user_id = await consume_token(PROPOSITO_VERIFICACION_CORREO, token)
    if user_id is None:
        raise ValidationDomainError("El enlace de verificación no es válido o ha caducado.")
    await session.execute(text("SELECT app_verify_user_email(:id)"), {"id": user_id})
    return user_id


async def resend_verification(session: AsyncSession, *, email: str) -> None:
    """Reencola el correo de verificación si la cuenta existe y no está verificada.

    Misma respuesta siempre, se cumpla o no la condición: no revela qué correos
    existen ni cuáles ya están verificados.
    """
    fila = (
        await session.execute(
            text("SELECT id, email_verified_at FROM app_find_user_by_email(:email)"),
            {"email": email},
        )
    ).first()
    if fila is not None and fila[1] is None:
        token = await generate_token(PROPOSITO_VERIFICACION_CORREO, fila[0])
        await send_verification_email.kiq(email, token)
