"""Tokens de un solo uso para verificación de correo, cambio de correo y recuperación.

Reutiliza el patrón de Redis+TTL de los refresh tokens: token opaco, de él solo se
guarda su huella, y «un solo uso» se implementa borrando la clave al consumirla
(`GETDEL`, atómico: evita una carrera entre comprobar y borrar). Cada token lleva su
**propósito** en la clave, así que un token de verificación de correo nunca sirve para
otro fin, aunque el cambio de correo y la recuperación de contraseña compartan el
mismo mecanismo.

El valor guardado es una cadena arbitraria, no necesariamente un `user_id`: el cambio
de correo necesita llevar también el correo nuevo (`"{user_id}:{correo_nuevo}"`), así
que cada llamador decide cómo codificar y decodificar su propio payload.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from app.core.redis_client import require_redis

TTL_TOKEN = timedelta(hours=24)

PROPOSITO_VERIFICACION_CORREO = "email_verify"
PROPOSITO_CAMBIO_CORREO = "email_change"
PROPOSITO_RECUPERAR_CONTRASENA = "password_reset"
# Fase 3 del PRD (inscripción de asistentes). Payload: el `id` de la inscripción.
PROPOSITO_VERIFICACION_INSCRIPCION = "registration_email_verify"
# Fase 3 del PRD, fase 3 de trabajo (aprobación y lista de espera). Payload: el
# `id` de la inscripción promovida. TTL variable, igual a la ventana de
# promoción configurada — nunca `TTL_TOKEN`, ver `generate_token`.
PROPOSITO_PROMOCION_LISTA_ESPERA = "waitlist_promotion_confirm"
# Fase 3 del PRD, fase 4 de trabajo (autocancelación). Payload: el `id` de la
# inscripción. Se genera de nuevo cada vez que se encola un email que ofrece
# cancelar (confirmación, lista de espera, promoción) — nunca una sola vez —
# así que pueden coexistir varios tokens válidos para la misma inscripción.
PROPOSITO_CANCELACION_INSCRIPCION = "registration_cancel"

_CLAVE = "verify:{proposito}:{huella}"


def _huella(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def generate_token(proposito: str, payload: str, *, ttl: timedelta = TTL_TOKEN) -> str:
    """Genera y guarda un token opaco de un solo uso para el propósito indicado.

    `ttl` por defecto son las 24h de siempre; la promoción de lista de espera
    pasa su propia ventana, configurable por `settings`, en vez de reutilizar
    esta constante.
    """
    token = secrets.token_urlsafe(32)
    redis = await require_redis()
    await redis.set(
        _CLAVE.format(proposito=proposito, huella=_huella(token)),
        payload,
        ex=ttl,
    )
    return token


async def consume_token(proposito: str, token: str) -> str | None:
    """Consume el token si existe y no ha caducado. `None` si no es válido."""
    redis = await require_redis()
    clave = _CLAVE.format(proposito=proposito, huella=_huella(token))
    bruto = await redis.getdel(clave)
    return str(bruto) if bruto is not None else None
