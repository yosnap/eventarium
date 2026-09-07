"""Alta y consulta de miembros de la organización."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.modules.organizations.models import OrganizationMember
from app.modules.organizations.repository import user_role_keys
from app.modules.roles.authorization import (
    ensure_can_grant,
    ensure_can_manage_role,
    ensure_not_self_escalation,
)
from app.modules.roles.models import Role, RolePermission
from app.modules.users.models import User
from app.shared.dynamic_fields import validate_profile_data
from app.shared.errors import ConflictError, NotFoundError


async def _role_permissions(session: AsyncSession, role: Role) -> set[Permission]:
    filas = await session.scalars(
        select(RolePermission.permission).where(RolePermission.role_id == role.id)
    )
    permisos: set[Permission] = set()
    for valor in filas:
        try:
            permisos.add(Permission(valor))
        except ValueError:
            continue
    return permisos


async def add_member(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_permissions: set[Permission],
    email: str,
    first_name: str,
    last_name: str,
    role_id: uuid.UUID,
    profile_data: dict[str, Any] | None,
) -> OrganizationMember:
    """Da de alta a una persona en la organización con un rol.

    Crea el usuario si el correo no existe todavía: en la fase 0 no hay flujo de
    invitación por correo, así que la cuenta queda sin contraseña hasta que se
    defina una.
    """
    rol = await session.scalar(
        select(Role).where(Role.id == role_id, Role.organization_id == organization_id)
    )
    if rol is None:
        raise NotFoundError("El rol indicado no existe en esta organización.")

    permisos_rol = await _role_permissions(session, rol)
    claves_actor = await user_role_keys(session, organization_id, actor_id)

    ensure_can_manage_role(
        actor_role_keys=claves_actor, role_key=rol.key, es_rol_de_sistema=rol.is_system
    )
    ensure_can_grant(actor_permissions, permisos_rol)

    correo = email.strip().lower()
    usuario = await session.scalar(select(User).where(User.email == correo))
    if usuario is None:
        usuario = User(
            email=correo,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            is_active=True,
        )
        session.add(usuario)
        await session.flush()

    ensure_not_self_escalation(
        actor_id=actor_id,
        target_user_id=usuario.id,
        permisos_nuevos=permisos_rol,
        permisos_actor=actor_permissions,
    )

    existente = await session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == usuario.id,
            OrganizationMember.role_id == rol.id,
        )
    )
    if existente is not None:
        raise ConflictError("Esa persona ya tiene ese rol en la organización.")

    datos = validate_profile_data(list(rol.profile_fields), profile_data)

    miembro = OrganizationMember(
        organization_id=organization_id,
        user_id=usuario.id,
        role_id=rol.id,
        profile_data=datos,
    )
    session.add(miembro)
    await session.flush()
    return miembro
