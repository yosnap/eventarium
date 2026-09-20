"""Hash de contraseñas y emisión/verificación de tokens.

- Access token: JWT firmado (HS256), corta vida, viaja en la respuesta JSON y se
  guarda en memoria en el cliente.
- Refresh token: **opaco** (`secrets.token_urlsafe`), viaja en cookie `HttpOnly`.
  De él solo se almacena un hash en Redis, junto a su familia, para poder rotarlo y
  revocar toda la familia si se detecta reutilización.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings
from app.shared.errors import AuthenticationError

_hasher = PasswordHasher()

# Política de contraseña del registro público: longitud mínima + composición
# (mayúscula, minúscula, número, carácter especial). El mismo conjunto de caracteres
# especiales que valida el widget del frontend (`shared/ui/password-strength.ts`),
# para que un cliente no acepte una contraseña que el servidor rechazaría después.
PASSWORD_MIN_LENGTH = 8
_PASSWORD_ESPECIAL = re.compile(r'[!@#$%^&*(),.?":{}|<>]')
_PASSWORD_MAYUSCULA = re.compile(r"[A-Z]")
_PASSWORD_MINUSCULA = re.compile(r"[a-z]")
_PASSWORD_NUMERO = re.compile(r"[0-9]")


def password_meets_complexity(password: str) -> bool:
    """Longitud mínima + mayúscula + minúscula + número + carácter especial."""
    return (
        len(password) >= PASSWORD_MIN_LENGTH
        and bool(_PASSWORD_MAYUSCULA.search(password))
        and bool(_PASSWORD_MINUSCULA.search(password))
        and bool(_PASSWORD_NUMERO.search(password))
        and bool(_PASSWORD_ESPECIAL.search(password))
    )


def hash_password(password: str) -> str:
    """Devuelve el hash Argon2id de una contraseña."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Comprueba una contraseña. Un usuario sin hash nunca autentica."""
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Indica si el hash usa parámetros obsoletos."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """Contenido útil de un access token ya verificado."""

    user_id: uuid.UUID
    organization_id: uuid.UUID | None
    jti: str
    is_superadmin: bool
    # Familia del refresh token con el que se emitió este access token. La cookie de
    # refresh tiene `Path=/api/v1/auth`, así que un endpoint fuera de ese prefijo (p.
    # ej. `/users/me/change-password`) nunca la recibe; llevar la familia en el propio
    # access token es lo único que permite a esos endpoints revocar «todas las
    # sesiones salvo la actual» sin depender de la cookie.
    family: str | None = None
    #: Id del administrador que está suplantando a `user_id`, o `None` si el
    #: token es de una sesión normal. Un token con esto puesto **no** debe
    #: valer para los gates de plataforma, ni para escribir (`require_superadmin`
    #: lo comprueba explícitamente: mira la fila de `users`, no este claim, así
    #: que un `sa` heredado del suplantado no basta).
    impersonated_by: uuid.UUID | None = None


def create_access_token(
    user_id: uuid.UUID,
    organization_id: uuid.UUID | None,
    *,
    is_superadmin: bool = False,
    family: str | None = None,
    impersonated_by: uuid.UUID | None = None,
    ttl_minutes: int | None = None,
) -> str:
    """Emite un access token para un usuario en una organización concreta.

    `ttl_minutes` solo lo usa la sesión de impersonación, que tiene que caducar
    antes que una sesión normal: durante una suplantación el token da acceso a
    los datos de otra persona, así que su ventana debe ser la más corta posible.
    """
    settings = get_settings()
    ahora = datetime.now(UTC)
    minutos = ttl_minutes if ttl_minutes is not None else settings.access_token_ttl_minutes
    payload = {
        "sub": str(user_id),
        "org": str(organization_id) if organization_id else None,
        "sa": is_superadmin,
        "fam": family,
        "imp_by": str(impersonated_by) if impersonated_by else None,
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": int(ahora.timestamp()),
        "exp": int((ahora + timedelta(minutes=minutos)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> AccessTokenClaims:
    """Verifica un access token.

    El algoritmo se fija explícitamente en la lista de aceptados: aceptar el
    algoritmo declarado en la cabecera permitiría degradar la firma a `none`.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Token no válido o caducado.") from exc

    if payload.get("type") != "access":
        raise AuthenticationError("Tipo de token incorrecto.")

    org = payload.get("org")
    imp_by = payload.get("imp_by")
    try:
        return AccessTokenClaims(
            user_id=uuid.UUID(str(payload["sub"])),
            organization_id=uuid.UUID(str(org)) if org else None,
            jti=str(payload.get("jti", "")),
            is_superadmin=bool(payload.get("sa", False)),
            family=payload.get("fam") or None,
            impersonated_by=uuid.UUID(str(imp_by)) if imp_by else None,
        )
    except (ValueError, KeyError) as exc:
        raise AuthenticationError("Token con contenido no válido.") from exc


def generate_refresh_token() -> str:
    """Genera un refresh token opaco."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """Hash del refresh token para guardarlo en Redis.

    SHA-256 basta: el token ya es aleatorio de 384 bits, no hay que resistir fuerza
    bruta sobre un secreto de baja entropía como en una contraseña.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_password(longitud: int = 12) -> str:
    """Contraseña aleatoria legible, usada por el seed y el CLI."""
    return secrets.token_urlsafe(longitud)


def hash_email_with_salt(email: str) -> str:
    """Hash **no reversible** de un email, para `audit_log.detail` del borrado
    RGPD de un inscrito (decisión #6 del plan de la fase 5).

    Guardar el email en claro trasladaría la PII de una tabla protegida (RLS +
    cascada de borrado) a `audit_log`, que no tiene retención propia. Un
    `sha256` sin sal sería reversible por diccionario (los emails no tienen
    entropía suficiente); se usa HMAC-SHA256 con `jwt_secret` como clave —ya
    es un secreto de instalación, no expuesto en ningún export— en vez de dar
    de alta un secreto nuevo solo para este uso puntual.
    """
    clave = get_settings().jwt_secret.encode("utf-8")
    return hmac.new(clave, email.strip().lower().encode("utf-8"), hashlib.sha256).hexdigest()
