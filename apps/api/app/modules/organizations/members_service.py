"""Alta y consulta de miembros de la organización."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, text
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


async def find_user_id_by_email(session: AsyncSession, email: str) -> uuid.UUID | None:
    """Busca el `id` de una persona por correo sin depender de que RLS la haga visible.

    `select(User).where(User.email == ...)` bajo RLS solo ve a quien comparte
    organización con el actor (`tenant_users`, `0003_politicas_rls`) — pero el
    caso real de esta función es precisamente alguien que **no** la comparte
    todavía: un ponente que ya dio una charla en otra organización, o
    cualquiera a quien se invita por primera vez a esta. Reutiliza la misma
    función `SECURITY DEFINER` que ya resuelve este problema para
    `forgot_password` (`auth/service.py`, `0004_correo_y_verificacion`), en
    vez de dar `BYPASSRLS` al rol de la API.

    El resto del alta no necesita leer la fila de `users`: una FK hacia un
    `id` que existe se valida en Postgres sin pasar por RLS de la tabla
    referenciada, así que basta con el identificador para insertar la
    membresía o la invitación.
    """
    fila = (
        await session.execute(
            text("SELECT id FROM app_find_user_by_email(:email)"), {"email": email}
        )
    ).first()
    return fila[0] if fila is not None else None


async def validar_rol_para_conceder(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_permissions: set[Permission],
    role_id: uuid.UUID,
) -> tuple[Role, set[Permission]]:
    """Resuelve el rol y aplica las reglas anti-escalada, sin tocar la membresía.

    Compartido entre `add_member` y `invitations_service.create_invitation`
    (fase 1 del plan de invitaciones): una invitación no puede escalar
    privilegios por un camino distinto del alta directa — `ensure_can_grant` y
    `ensure_not_self_escalation` tienen que protegerla igual.
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
    return rol, permisos_rol


async def add_member(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_permissions: set[Permission],
    email: str,
    first_name: str | None,
    last_name: str | None,
    role_id: uuid.UUID,
    profile_data: dict[str, Any] | None,
) -> OrganizationMember:
    """Da de alta a una persona en la organización con un rol.

    Crea el usuario si el correo no existe todavía: en la fase 0 no hay flujo de
    invitación por correo, así que la cuenta queda sin contraseña hasta que se
    defina una.

    `first_name`/`last_name` aceptan `None` desde la fase 1 del plan de
    invitaciones: quien invita por correo a alguien sin cuenta no sabe cómo se
    llama (lo completa la persona al aceptar). La pantalla de alta manual
    sigue exigiéndolos porque su esquema (`MemberCreate`) los declara
    obligatorios; la opcionalidad es de este camino compartido, no de ese
    formulario.
    """
    rol, permisos_rol = await validar_rol_para_conceder(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        actor_permissions=actor_permissions,
        role_id=role_id,
    )

    correo = email.strip().lower()
    usuario_id = await find_user_id_by_email(session, correo)
    if usuario_id is None:
        nuevo = User(
            email=correo,
            first_name=first_name.strip() if first_name else None,
            last_name=last_name.strip() if last_name else None,
            is_active=True,
        )
        session.add(nuevo)
        await session.flush()
        usuario_id = nuevo.id

    ensure_not_self_escalation(
        actor_id=actor_id,
        target_user_id=usuario_id,
        permisos_nuevos=permisos_rol,
        permisos_actor=actor_permissions,
    )

    existente = await session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == usuario_id,
            OrganizationMember.role_id == rol.id,
        )
    )
    if existente is not None:
        raise ConflictError("Esa persona ya tiene ese rol en la organización.")

    datos = validate_profile_data(list(rol.profile_fields), profile_data)

    miembro = OrganizationMember(
        organization_id=organization_id,
        user_id=usuario_id,
        role_id=rol.id,
        profile_data=datos,
    )
    session.add(miembro)
    await session.flush()
    return miembro
