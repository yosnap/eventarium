"""Invitar a una persona a la organización.

Fase 1 del plan de invitaciones (plan.md): activa el mecanismo que
`add_member` ya tenía sin usar (cuenta sin contraseña, `members_service.py`)
y le añade estado, caducidad, reenvío y revocación.

**Las dos reglas duras de seguridad** (hallazgo S-1 del red-team):

- Un correo **con** cuenta existente nunca emite token: se añade la
  membresía directamente, por el mismo `add_member` que usa el alta manual.
- Un correo **sin** cuenta crea la fila de invitación y una cuenta sin
  contraseña, pero **nunca** la membresía — esa se crea al aceptar (fase 2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.modules.auth.verification import (
    PROPOSITO_INVITACION,
    TTL_INVITACION,
    generate_token,
    revoke_by_fingerprint,
    token_fingerprint,
)
from app.modules.organizations import members_service
from app.modules.organizations.invitations_models import OrganizationInvitation
from app.modules.organizations.models import OrganizationMember
from app.modules.users.models import User
from app.shared.errors import ConflictError, NotFoundError

# Se concede solo en la plantilla `ORGANIZER` (fase 0) y en `OWNER` vía
# `tuple(Permission)` — nunca en `MEMBERS_WRITE`: si bastara `members:write`,
# cualquier `organizer` gestionaría invitaciones y el caso «un voluntario
# gestiona invitaciones sin más» no se distinguiría del alta directa.
REQUIRED_PERMISSION = Permission.INVITATIONS_MANAGE


@dataclass(slots=True)
class InvitationResult:
    """Resultado de crear o reenviar una invitación.

    `token` viaja en claro solo hasta el correo (fase 2, `send_invitation_email`);
    la capa de esquemas/router no lo expone jamás en una respuesta HTTP. Es
    `None` cuando el correo ya tenía cuenta: esa rama no emite ningún token
    (regla A.2).
    """

    member: OrganizationMember | None
    invitation: OrganizationInvitation | None
    token: str | None


def estado_efectivo(invitacion: OrganizationInvitation, *, ahora: datetime | None = None) -> str:
    """El estado tal y como se muestra, no el que guarda la fila.

    `estado` solo guarda lo que no se deduce (`pendiente`, `aceptada`,
    `revocada`); una fila `pendiente` cuya `expires_at` ya pasó se muestra
    `caducada` sin escribirlo — dos fuentes de verdad para el mismo hecho es
    el bug que esto evita.
    """
    ahora = ahora or datetime.now(UTC)
    if invitacion.estado == "pendiente" and invitacion.expires_at < ahora:
        return "caducada"
    return invitacion.estado


async def create_invitation(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_permissions: set[Permission],
    email: str,
    role_id: uuid.UUID,
    event_id: uuid.UUID | None = None,
) -> InvitationResult:
    """Invita a una persona, o la añade directamente si ya tiene cuenta."""
    correo = email.strip().lower()
    # `find_user_id_by_email`, no `select(User)`: RLS solo hace visible a
    # quien comparte organización con el actor, y el caso que importa aquí es
    # justo el contrario — alguien con cuenta en otra organización, o sin
    # ninguna todavía.
    usuario_id_existente = await members_service.find_user_id_by_email(session, correo)

    if usuario_id_existente is not None:
        # Correo con cuenta → nunca se emite token (S-1): se añade
        # directamente por el mismo camino que el alta manual, con las
        # mismas comprobaciones anti-escalada.
        miembro = await members_service.add_member(
            session,
            organization_id=organization_id,
            actor_id=actor_id,
            actor_permissions=actor_permissions,
            email=correo,
            first_name=None,
            last_name=None,
            role_id=role_id,
            profile_data={},
        )
        return InvitationResult(member=miembro, invitation=None, token=None)

    rol, _permisos_rol = await members_service.validar_rol_para_conceder(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        actor_permissions=actor_permissions,
        role_id=role_id,
    )

    if event_id is not None:
        await _validar_evento(session, organization_id=organization_id, event_id=event_id)

    # Correo sin cuenta → cuenta sin contraseña (lo que `add_member` ya hacía)
    # más la invitación como estado. Sin membresía todavía: esa nace al
    # aceptar (fase 2), no aquí.
    usuario = User(email=correo, is_active=True)
    session.add(usuario)
    await session.flush()

    invitacion = OrganizationInvitation(
        organization_id=organization_id,
        email=correo,
        role_id=rol.id,
        event_id=event_id,
        estado="pendiente",
        expires_at=datetime.now(UTC) + TTL_INVITACION,
        invited_by_user_id=actor_id,
    )
    session.add(invitacion)
    await session.flush()

    # El token no se guarda en ninguna columna: va a Redis, con el `id` de la
    # invitación como payload. Solo su huella queda en `token_hash`, para
    # poder revocarlo si se reenvía.
    token = await generate_token(PROPOSITO_INVITACION, str(invitacion.id), ttl=TTL_INVITACION)
    invitacion.token_hash = token_fingerprint(token)
    await session.flush()

    return InvitationResult(member=None, invitation=invitacion, token=token)


async def _validar_evento(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID
) -> None:
    """El evento tiene que ser de esta organización (fase 3)."""
    from app.modules.events.models import Event

    evento = await session.scalar(
        select(Event).where(Event.id == event_id, Event.organization_id == organization_id)
    )
    if evento is None:
        raise NotFoundError("El evento indicado no existe en esta organización.")


async def _get_pending_invitation(
    session: AsyncSession, *, organization_id: uuid.UUID, invitation_id: uuid.UUID
) -> OrganizationInvitation:
    invitacion = await session.scalar(
        select(OrganizationInvitation).where(
            OrganizationInvitation.id == invitation_id,
            OrganizationInvitation.organization_id == organization_id,
        )
    )
    if invitacion is None:
        raise NotFoundError("La invitación indicada no existe en esta organización.")
    if estado_efectivo(invitacion) != "pendiente":
        raise ConflictError("Esta invitación ya no está pendiente.")
    return invitacion


async def revoke_invitation(
    session: AsyncSession, *, organization_id: uuid.UUID, invitation_id: uuid.UUID
) -> OrganizationInvitation:
    invitacion = await _get_pending_invitation(
        session, organization_id=organization_id, invitation_id=invitation_id
    )
    if invitacion.token_hash is not None:
        await revoke_by_fingerprint(PROPOSITO_INVITACION, invitacion.token_hash)
    invitacion.estado = "revocada"
    invitacion.token_hash = None
    await session.flush()
    return invitacion


async def resend_invitation(
    session: AsyncSession, *, organization_id: uuid.UUID, invitation_id: uuid.UUID
) -> tuple[OrganizationInvitation, str]:
    """Emite un token nuevo, alarga la caducidad e invalida el anterior.

    El token viejo no puede reconstruirse desde la fila (esa es la garantía
    de guardar solo la huella), pero la huella sí basta para borrar su clave
    de Redis por su nombre exacto: es lo que hace `revoke_by_fingerprint`.

    A diferencia de `create_invitation`, siempre hay invitación y token: no
    hay rama «ya tiene cuenta» al reenviar, así que devuelve la pareja
    directamente en vez de reutilizar `InvitationResult`.
    """
    invitacion = await _get_pending_invitation(
        session, organization_id=organization_id, invitation_id=invitation_id
    )
    if invitacion.token_hash is not None:
        await revoke_by_fingerprint(PROPOSITO_INVITACION, invitacion.token_hash)

    invitacion.expires_at = datetime.now(UTC) + TTL_INVITACION
    token = await generate_token(PROPOSITO_INVITACION, str(invitacion.id), ttl=TTL_INVITACION)
    invitacion.token_hash = token_fingerprint(token)
    await session.flush()

    return invitacion, token
