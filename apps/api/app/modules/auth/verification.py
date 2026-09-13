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
# Fase 1 del plan de invitaciones. Payload: el `id` de la fila en
# `organization_invitations`. Propósito separado de
# `PROPOSITO_RECUPERAR_CONTRASENA` a propósito (hallazgo S-1 del red-team): el
# enlace de invitación fija contraseña igual que el de recuperación, así que
# si compartieran propósito, un token de invitación emitido para un correo
# ajeno sería un restablecimiento de contraseña de una cuenta existente —
# secuestro de cuenta. TTL propio de 7 días (no `TTL_TOKEN`): una invitación
# se acepta con menos urgencia que verificar un correo recién registrado.
PROPOSITO_INVITACION = "invitacion"
TTL_INVITACION = timedelta(days=7)

_CLAVE = "verify:{proposito}:{huella}"


def _huella(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_fingerprint(token: str) -> str:
    """Huella pública de un token, para que un llamador la guarde y pueda
    invalidar una generación anterior sin guardar el token en ningún sitio.

    Es la misma huella que ya viaja en la clave de Redis (`_CLAVE`), expuesta
    porque `invitations_service` (fase 1 del plan de invitaciones) necesita
    revocar el token anterior al reenviar, y solo conserva su huella —igual
    que `users.password_hash` no es la contraseña, esto no es el token.
    """
    return _huella(token)


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


async def revoke_by_fingerprint(proposito: str, fingerprint: str) -> None:
    """Borra la clave de un token por su huella, sin necesitar el token.

    Reenviar una invitación (`invitations_service.resend_invitation`) tiene
    que invalidar el enlace anterior, y para entonces ya no se tiene el token
    en claro — solo su huella, guardada en `organization_invitations.token_hash`.
    No falla si la clave ya no existe (caducada o usada).
    """
    redis = await require_redis()
    await redis.delete(_CLAVE.format(proposito=proposito, huella=fingerprint))


async def peek_token(proposito: str, token: str) -> str | None:
    """Como `consume_token`, pero sin borrar la clave.

    `/mi-entrada` (fase 4 del PRD) reutiliza el token de autocancelación para
    volver a mostrar el QR — mirarlo no debe invalidar el enlace de cancelar
    que llegó en el mismo correo, así que no puede usar `GETDEL`.
    """
    redis = await require_redis()
    clave = _CLAVE.format(proposito=proposito, huella=_huella(token))
    bruto = await redis.get(clave)
    return str(bruto) if bruto is not None else None
