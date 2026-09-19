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
from enum import StrEnum

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import set_organization_context
from app.core.permissions import Permission
from app.core.security import hash_password
from app.modules.auth.verification import (
    PROPOSITO_INVITACION,
    TTL_INVITACION,
    generate_token,
    peek_token,
    revoke_by_fingerprint,
    token_fingerprint,
)
from app.modules.organizations import members_service
from app.modules.organizations.invitations_models import OrganizationInvitation
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.roles.models import Role
from app.modules.users.models import User
from app.shared.dynamic_fields import validate_profile_data
from app.shared.errors import ConflictError, NotFoundError, ValidationDomainError

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

    if event_id is not None:
        # Antes de cualquier rama: un `organizer` no puede invitar a un
        # evento ajeno, tenga o no cuenta ya la persona invitada.
        await _validar_evento(session, organization_id=organization_id, event_id=event_id)

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
            enforce_required_profile_fields=False,
        )
        # Fase 3: si la invitación nace de un evento, quien ya tenía cuenta
        # entra también en su roster de inmediato — no hay «aceptar» que
        # esperar en esta rama, así que las dos altas van juntas aquí.
        await _add_to_event_roster_if_needed(
            session,
            organization_id=organization_id,
            event_id=event_id,
            organization_member_id=miembro.id,
        )
        return InvitationResult(member=miembro, invitation=None, token=None)

    rol, _permisos_rol = await members_service.validar_rol_para_conceder(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        actor_permissions=actor_permissions,
        role_id=role_id,
    )

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


async def _add_to_event_roster_if_needed(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID | None,
    organization_member_id: uuid.UUID,
) -> None:
    """Alta idempotente en `event_members` (fase 3): sin `event_id`, no hace nada.

    Import local, no a nivel de módulo: `events.service` ya importa
    `organizations.repository`, así que lo contrario a nivel de módulo
    formaría un ciclo entre los dos paquetes.

    `UNIQUE(event_id, organization_member_id)` (`events/models.py:270-272`)
    ya lo impediría a nivel de base de datos, pero comprobarlo antes evita el
    viaje a la base que solo serviría para descartar el error.
    """
    if event_id is None:
        return
    from app.modules.events import repository as events_repository
    from app.modules.events.models import EventMember

    existente = await events_repository.get_event_member_by_organization_member(
        session, organization_id, event_id, organization_member_id
    )
    if existente is not None:
        return
    session.add(
        EventMember(
            event_id=event_id,
            organization_id=organization_id,
            organization_member_id=organization_member_id,
        )
    )
    await session.flush()


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
    """Marca la invitación como revocada.

    A diferencia de `resend_invitation`, esto **no** borra la clave de Redis:
    el token sigue resolviendo al `id` de la invitación mientras dure su TTL
    natural, y es justo lo que permite que la pantalla pública (fase 2)
    distinga «esta invitación ha sido revocada» de «este enlace no es válido»
    en vez de dar el mismo mensaje genérico a los dos casos. No es un riesgo:
    `accept_invitation` exige `estado_efectivo() == "pendiente"` antes de
    tocar nada, así que una invitación revocada no puede aceptarse encuentre
    o no su token en Redis.
    """
    invitacion = await _get_pending_invitation(
        session, organization_id=organization_id, invitation_id=invitation_id
    )
    invitacion.estado = "revocada"
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


# --- Pantalla pública de aceptación (fase 2) -------------------------------


class InvitationTokenState(StrEnum):
    """Por qué un token no sirve, para dar tres mensajes distintos (fase 2).

    Deliberadamente sin distinguir «no existe» de «caducó de verdad hace
    tiempo»: en los dos casos el token ya no está en Redis y no hay ningún
    `id` de invitación al que asomarse — es la misma limitación que ya acepta
    el resto del proyecto para `verify-email`/`reset-password`. Lo que sí se
    distingue, porque la fila de invitación **sigue siendo alcanzable**
    mientras el token no haya caducado por sí solo, es `revocada` y
    `aceptada` frente a `invalida`.
    """

    VALIDA = "valida"
    INVALIDA = "invalida"
    CADUCADA = "caducada"
    REVOCADA = "revocada"
    ACEPTADA = "aceptada"


@dataclass(slots=True)
class ResolvedInvitationToken:
    """Lo que la pantalla pública necesita saber de un token, y nada más.

    `organization_name`/`role_name` son deliberadamente los únicos datos de
    negocio que salen de aquí — nunca la lista de miembros ni nada que
    identifique a otras personas (requisito de seguridad del PRD)."""

    state: InvitationTokenState
    invitation: OrganizationInvitation | None = None
    organization_name: str | None = None
    role_name: str | None = None
    account_has_password: bool = False


async def resolve_invitation_token(session: AsyncSession, token: str) -> ResolvedInvitationToken:
    """Resuelve un token de invitación sin consumirlo (`peek_token`).

    No destructivo a propósito: `GET /public/invitations/{token}` se puede
    llamar varias veces (recargar la página) sin gastar el enlace, y
    `accept_invitation` reutiliza esta misma resolución para decidir si hay
    algo que aceptar.

    Fija el contexto RLS de `session` (organización **y** vacía
    `app.user_id`) a partir del propio token — solo para los dos routers
    públicos que la llaman. No debe usarse desde ningún camino autenticado:
    sobrescribiría la organización activa y el usuario de la sesión en curso.
    """
    invitation_id_bruto = await peek_token(PROPOSITO_INVITACION, token)
    if invitation_id_bruto is None:
        return ResolvedInvitationToken(state=InvitationTokenState.INVALIDA)
    try:
        invitation_id = uuid.UUID(invitation_id_bruto)
    except ValueError:
        return ResolvedInvitationToken(state=InvitationTokenState.INVALIDA)

    # Sin dominio por organización (fase 2 del plan de organización sin
    # dominio), el contexto RLS se resuelve desde la propia invitación, no
    # por host (`app_resolve_invitation_organization`, SECURITY DEFINER de
    # alcance mínimo, migración `0032`) — el `id` ya viene autorizado por el
    # propio token de un solo uso.
    organization_id: uuid.UUID | None = await session.scalar(
        text("SELECT app_resolve_invitation_organization(:id)"), {"id": invitation_id}
    )
    await set_organization_context(session, organization_id)

    fila = (
        await session.execute(
            select(OrganizationInvitation, Role, Organization)
            .join(Role, Role.id == OrganizationInvitation.role_id)
            .join(Organization, Organization.id == OrganizationInvitation.organization_id)
            .where(OrganizationInvitation.id == invitation_id)
        )
    ).first()
    if fila is None:
        # O el `id` no existe, o el contexto de arriba no pudo fijarse — RLS
        # ya lo hace invisible, sin filtrar cuál de las dos cosas es
        # (requisito de seguridad del PRD).
        return ResolvedInvitationToken(state=InvitationTokenState.INVALIDA)
    invitacion, rol, organizacion = fila

    estado = estado_efectivo(invitacion)
    if estado == "caducada":
        return ResolvedInvitationToken(state=InvitationTokenState.CADUCADA, invitation=invitacion)
    if estado == "revocada":
        return ResolvedInvitationToken(state=InvitationTokenState.REVOCADA, invitation=invitacion)
    if estado == "aceptada":
        return ResolvedInvitationToken(state=InvitationTokenState.ACEPTADA, invitation=invitacion)

    estado_cuenta = await members_service.find_user_state_by_email(session, invitacion.email)
    tiene_contrasena = estado_cuenta[1] if estado_cuenta is not None else False

    return ResolvedInvitationToken(
        state=InvitationTokenState.VALIDA,
        invitation=invitacion,
        organization_name=organizacion.name,
        role_name=rol.name,
        account_has_password=tiene_contrasena,
    )


def mensaje_de_estado(state: InvitationTokenState) -> str:
    """El texto que lee la persona invitada para cada estado no válido."""
    return _MENSAJE_TOKEN_INVALIDO[state]


_MENSAJE_TOKEN_INVALIDO: dict[InvitationTokenState, str] = {
    InvitationTokenState.INVALIDA: "El enlace de invitación no es válido.",
    InvitationTokenState.CADUCADA: "Esta invitación ha caducado. Pide que te envíen otra.",
    InvitationTokenState.REVOCADA: "Esta invitación ha sido revocada.",
    InvitationTokenState.ACEPTADA: "Esta invitación ya se aceptó.",
    InvitationTokenState.VALIDA: "",  # nunca se usa: rama tratada aparte abajo
}


async def accept_invitation(
    session: AsyncSession,
    *,
    token: str,
    first_name: str,
    last_name: str,
    password: str,
) -> OrganizationMember:
    """Fija nombre y contraseña, y crea la membresía. Idempotente.

    Aceptar dos veces con el mismo token no duplica la membresía: si la
    invitación ya está `aceptada`, se devuelve la fila existente sin volver a
    tocar la cuenta ni el rol — es justo lo que exige la fase 2 (doble clic,
    recarga tras aceptar).
    """
    resuelto = await resolve_invitation_token(session, token)

    if resuelto.state == InvitationTokenState.ACEPTADA and resuelto.invitation is not None:
        miembro = await session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == resuelto.invitation.organization_id,
                OrganizationMember.user_id == resuelto.invitation.accepted_by_user_id,
                OrganizationMember.role_id == resuelto.invitation.role_id,
            )
        )
        if miembro is not None:
            return miembro
        # La invitación quedó `aceptada` pero la membresía no se encuentra
        # (borrada aparte, p. ej.): no hay nada seguro que reconstruir aquí.
        raise ConflictError("Esta invitación ya se aceptó.")

    if resuelto.state != InvitationTokenState.VALIDA or resuelto.invitation is None:
        raise ValidationDomainError(_MENSAJE_TOKEN_INVALIDO[resuelto.state])

    if resuelto.account_has_password:
        # No debería llegarse aquí (la fase 1 no emite token si el correo ya
        # tenía cuenta): caso anómalo, tratado como error explícito en vez de
        # iniciar sesión por la persona.
        raise ConflictError(
            "Esta cuenta ya tiene contraseña. Inicia sesión con ella en vez de aceptar aquí."
        )

    invitacion = resuelto.invitation

    usuario_id_y_estado = await members_service.find_user_state_by_email(session, invitacion.email)
    if usuario_id_y_estado is None:  # pragma: no cover - `create_invitation` siempre lo crea antes
        raise ConflictError("La cuenta de esta invitación ya no existe.")
    usuario_id, _tiene_contrasena = usuario_id_y_estado

    rol = await session.get(Role, invitacion.role_id)
    if rol is None:  # pragma: no cover - `role_id` es `ON DELETE CASCADE` de esta misma fila
        raise NotFoundError("El rol de esta invitación ya no existe.")

    # `enforce_required=False`: quien acepta no ha rellenado su ficha
    # todavía (bio, titular…), y esta pantalla no se la pide (fase 2 solo
    # pide nombre y contraseña) — un campo obligatorio del rol no puede
    # bloquear la aceptación.
    datos_perfil = validate_profile_data(list(rol.profile_fields), {}, enforce_required=False)

    # Se crea la membresía **antes** de tocar `users`: dentro de la misma
    # transacción, esa fila ya es visible para `tenant_users` (RLS) por la
    # cláusula que comparte organización — sin ella, `app_accept_invited_user`
    # sería la única vía y aun así una lectura ORM posterior seguiría
    # bloqueada. Ver `app/core/database.py`/`0003_politicas_rls.py`.
    miembro = OrganizationMember(
        organization_id=invitacion.organization_id,
        user_id=usuario_id,
        role_id=invitacion.role_id,
        profile_data=datos_perfil,
    )
    session.add(miembro)
    await session.flush()

    # Fase 3: si la invitación nace de un evento, el alta en su roster va en
    # la misma transacción que la membresía — si esto falla, la excepción se
    # propaga y ninguna de las dos queda a medias.
    await _add_to_event_roster_if_needed(
        session,
        organization_id=invitacion.organization_id,
        event_id=invitacion.event_id,
        organization_member_id=miembro.id,
    )

    await session.execute(
        text("SELECT app_accept_invited_user(:id, :hash, :first_name, :last_name)"),
        {
            "id": usuario_id,
            "hash": hash_password(password),
            "first_name": first_name.strip(),
            "last_name": last_name.strip(),
        },
    )

    invitacion.estado = "aceptada"
    invitacion.accepted_at = datetime.now(UTC)
    invitacion.accepted_by_user_id = usuario_id
    await session.flush()

    return miembro
