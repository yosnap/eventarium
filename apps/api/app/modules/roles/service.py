"""Servicios de roles: creación, edición y borrado con reglas anti-escalada."""

from __future__ import annotations

import uuid
from typing import NamedTuple

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.database import maintenance_session
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


class _AuditoriaPermisosPendiente(NamedTuple):
    role_key: str
    permissions_before: list[str]
    permissions_after: list[str]


async def _registrar_cambio_de_permisos(
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    role_id: uuid.UUID,
    role_key: str,
    permissions_before: list[str],
    permissions_after: list[str],
) -> None:
    """Escribe en `audit_log` el cambio de permisos de un rol.

    Se ejecuta como `BackgroundTask` (Starlette la corre tras enviar la
    respuesta, y por tanto tras el `commit` real de la transacción principal
    que ocurre al salir de la dependencia `get_db` — mismo patrón que el
    borrado de objetos huérfanos en `events/router.py:upload_cover`). Si la
    petición fallase más tarde (p. ej. `profile_fields` inválidos) y la
    transacción principal revirtiera el cambio de permisos, esta función
    nunca llegaría a encolarse: la auditoría no puede sobrevivir a un
    rollback del cambio que describe.
    """
    async with maintenance_session() as auditoria:
        await registrar_auditoria(
            auditoria,
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            action="role.permissions_changed",
            entity_type="role",
            entity_id=str(role_id),
            detail={
                "role_key": role_key,
                "permissions_before": permissions_before,
                "permissions_after": permissions_after,
            },
        )


async def update_role(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    role_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    actor_role_keys: set[str],
    actor_permissions: set[Permission],
    datos: RoleUpdate,
    background_tasks: BackgroundTasks,
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

    auditoria_permisos_pendiente: _AuditoriaPermisosPendiente | None = None
    if datos.permissions is not None:
        permisos_anteriores = sorted(p.permission for p in rol.permissions)
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
        # No se escribe la auditoría aquí: se difiere hasta el final de la
        # función (ver `_registrar_cambio_de_permisos`) para no persistirla si
        # una validación posterior en esta misma petición (p. ej.
        # `profile_fields`) aborta la transacción.
        auditoria_permisos_pendiente = _AuditoriaPermisosPendiente(
            role_key=rol.key,
            permissions_before=permisos_anteriores,
            permissions_after=sorted(p.value for p in permisos),
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

    if auditoria_permisos_pendiente is not None:
        background_tasks.add_task(
            _registrar_cambio_de_permisos,
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            role_id=rol.id,
            role_key=auditoria_permisos_pendiente.role_key,
            permissions_before=auditoria_permisos_pendiente.permissions_before,
            permissions_after=auditoria_permisos_pendiente.permissions_after,
        )

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
