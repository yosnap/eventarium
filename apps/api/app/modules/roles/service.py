"""Servicios de roles: creación, edición y borrado con reglas anti-escalada."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.modules.roles.authorization import ensure_can_grant, ensure_can_manage_role
from app.modules.roles.models import Role, RolePermission, RoleProfileField
from app.modules.roles.schemas import ProfileFieldInput, RoleCreate, RoleUpdate
from app.modules.roles.system_roles import TEMPLATES_BY_KEY
from app.shared.errors import ConflictError, NotFoundError, ValidationDomainError


async def list_roles(session: AsyncSession, organization_id: uuid.UUID) -> list[Role]:
    filas = await session.scalars(
        select(Role).where(Role.organization_id == organization_id).order_by(Role.name)
    )
    return list(filas)


async def get_role(session: AsyncSession, organization_id: uuid.UUID, role_id: uuid.UUID) -> Role:
    rol = await session.scalar(
        select(Role).where(Role.id == role_id, Role.organization_id == organization_id)
    )
    if rol is None:
        raise NotFoundError("El rol no existe en esta organización.")
    return rol


def _campos_desde_plantilla(clave: str) -> list[ProfileFieldInput]:
    plantilla = TEMPLATES_BY_KEY.get(clave)
    if plantilla is None:
        raise ValidationDomainError(f"No existe la plantilla de rol «{clave}».")
    return [
        ProfileFieldInput(
            key=campo.key,
            label=campo.label,
            field_type=campo.field_type,
            options=campo.options,
            is_required=campo.is_required,
            sort_order=campo.sort_order,
        )
        for campo in plantilla.profile_fields
    ]


async def create_role(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_role_keys: set[str],
    actor_permissions: set[Permission],
    datos: RoleCreate,
) -> Role:
    """Crea un rol. Nunca puede otorgar más permisos de los que tiene el actor."""
    ensure_can_manage_role(
        actor_role_keys=actor_role_keys, role_key=datos.key, es_rol_de_sistema=False
    )

    permisos = set(datos.permissions)
    campos = list(datos.profile_fields)
    if datos.from_template:
        plantilla = TEMPLATES_BY_KEY.get(datos.from_template)
        if plantilla is None:
            raise ValidationDomainError(f"No existe la plantilla de rol «{datos.from_template}».")
        permisos |= set(plantilla.permissions)
        campos = _campos_desde_plantilla(datos.from_template) + campos

    ensure_can_grant(actor_permissions, permisos)

    existente = await session.scalar(
        select(Role).where(Role.organization_id == organization_id, Role.key == datos.key)
    )
    if existente is not None:
        raise ConflictError(f"Ya existe un rol con la clave «{datos.key}».")

    rol = Role(
        organization_id=organization_id,
        key=datos.key,
        name=datos.name,
        description=datos.description,
        is_system=False,
        system_template_key=datos.from_template,
    )
    session.add(rol)
    await session.flush()

    for permiso in permisos:
        session.add(
            RolePermission(
                role_id=rol.id, permission=permiso.value, organization_id=organization_id
            )
        )
    _añadir_campos(session, rol, organization_id, campos, bloqueados=False)
    await session.flush()
    await session.refresh(rol)
    return rol


def _añadir_campos(
    session: AsyncSession,
    rol: Role,
    organization_id: uuid.UUID,
    campos: list[ProfileFieldInput],
    *,
    bloqueados: bool,
) -> None:
    vistos: set[str] = set()
    for campo in campos:
        if campo.key in vistos:
            raise ValidationDomainError(f"El campo «{campo.key}» está repetido.")
        vistos.add(campo.key)
        session.add(
            RoleProfileField(
                organization_id=organization_id,
                role_id=rol.id,
                key=campo.key,
                label=campo.label,
                field_type=campo.field_type,
                options=campo.options,
                is_required=campo.is_required,
                is_locked=bloqueados,
                sort_order=campo.sort_order,
            )
        )


async def update_role(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    role_id: uuid.UUID,
    actor_role_keys: set[str],
    actor_permissions: set[Permission],
    datos: RoleUpdate,
) -> Role:
    """Actualiza un rol respetando los campos bloqueados de las plantillas."""
    rol = await get_role(session, organization_id, role_id)
    ensure_can_manage_role(
        actor_role_keys=actor_role_keys, role_key=rol.key, es_rol_de_sistema=rol.is_system
    )

    if datos.name is not None:
        rol.name = datos.name
    if datos.description is not None:
        rol.description = datos.description

    if datos.permissions is not None:
        permisos = set(datos.permissions)
        ensure_can_grant(actor_permissions, permisos)
        for actual in list(rol.permissions):
            await session.delete(actual)
        await session.flush()
        for permiso in permisos:
            session.add(
                RolePermission(
                    role_id=rol.id, permission=permiso.value, organization_id=organization_id
                )
            )

    if datos.profile_fields is not None:
        bloqueados = {c.key: c for c in rol.profile_fields if c.is_locked}
        entrantes = {c.key: c for c in datos.profile_fields}
        faltan = sorted(set(bloqueados) - set(entrantes))
        if faltan:
            raise ConflictError(
                "No se pueden eliminar campos predefinidos del rol.",
                extra={"campos_bloqueados": faltan},
            )
        for campo_actual in list(rol.profile_fields):
            await session.delete(campo_actual)
        await session.flush()
        for campo in datos.profile_fields:
            session.add(
                RoleProfileField(
                    organization_id=organization_id,
                    role_id=rol.id,
                    key=campo.key,
                    label=campo.label,
                    field_type=campo.field_type,
                    options=campo.options,
                    is_required=campo.is_required,
                    is_locked=campo.key in bloqueados,
                    sort_order=campo.sort_order,
                )
            )

    await session.flush()
    await session.refresh(rol)
    return rol


async def delete_role(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    role_id: uuid.UUID,
    actor_role_keys: set[str],
) -> None:
    """Borra un rol a medida. Los roles del sistema no se pueden borrar."""
    rol = await get_role(session, organization_id, role_id)
    ensure_can_manage_role(
        actor_role_keys=actor_role_keys, role_key=rol.key, es_rol_de_sistema=rol.is_system
    )
    if rol.is_system:
        raise ConflictError("Los roles del sistema no se pueden eliminar.")
    await session.delete(rol)
    await session.flush()
