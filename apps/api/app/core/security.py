"""Hash de contraseñas y emisión/verificación de tokens.

- Access token: JWT firmado (HS256), corta vida, viaja en la respuesta JSON y se
  guarda en memoria en el cliente.
- Refresh token: **opaco** (`secrets.token_urlsafe`), viaja en cookie `HttpOnly`.
  De él solo se almacena un hash en Redis, junto a su familia, para poder rotarlo y
  revocar toda la familia si se detecta reutilización.
"""

from __future__ import annotations

import hashlib
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


def create_access_token(
    user_id: uuid.UUID,
    organization_id: uuid.UUID | None,
    *,
    is_superadmin: bool = False,
) -> str:
    """Emite un access token para un usuario en una organización concreta."""
    settings = get_settings()
    ahora = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "org": str(organization_id) if organization_id else None,
        "sa": is_superadmin,
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": int(ahora.timestamp()),
        "exp": int((ahora + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
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
    try:
        return AccessTokenClaims(
            user_id=uuid.UUID(str(payload["sub"])),
            organization_id=uuid.UUID(str(org)) if org else None,
            jti=str(payload.get("jti", "")),
            is_superadmin=bool(payload.get("sa", False)),
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
