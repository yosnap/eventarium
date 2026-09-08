"""Endpoints de roles."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Response, status

from app.core.deps import CurrentUserDep, DbDep, PermissionsDep, require_permission
from app.core.permissions import Permission
from app.modules.organizations.repository import user_role_keys
from app.modules.roles import service
from app.modules.roles.models import Role
from app.modules.roles.schemas import (
    ProfileFieldResponse,
    RoleCreate,
    RoleResponse,
    RoleUpdate,
)

router = APIRouter(prefix="/roles", tags=["roles"])


def _to_response(rol: Role) -> RoleResponse:
    return RoleResponse(
        id=str(rol.id),
        key=rol.key,
        name=rol.name,
        description=rol.description,
        is_system=rol.is_system,
        system_template_key=rol.system_template_key,
        permissions=[Permission(p.permission) for p in rol.permissions],
        profile_fields=[
            ProfileFieldResponse(
                id=str(campo.id),
                key=campo.key,
                label=campo.label,
                field_type=campo.field_type,
                options=campo.options,
                is_required=campo.is_required,
                is_locked=campo.is_locked,
                sort_order=campo.sort_order,
            )
            for campo in rol.profile_fields
        ],
    )


@router.get(
    "",
    summary="Listar roles",
    response_model=list[RoleResponse],
    dependencies=[require_permission(Permission.ROLES_READ)],
)
async def list_roles(usuario: CurrentUserDep, session: DbDep) -> list[RoleResponse]:
    roles = await service.list_roles(session, usuario.organization_id)
    return [_to_response(rol) for rol in roles]


@router.post(
    "",
    summary="Crear un rol",
    description=(
        "Crea un rol propio de la organización, opcionalmente clonando una plantilla "
        "del sistema. No se pueden conceder permisos que el actor no posea."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=RoleResponse,
    dependencies=[require_permission(Permission.ROLES_WRITE)],
)
async def create_role(
    datos: RoleCreate, usuario: CurrentUserDep, session: DbDep, permisos: PermissionsDep
) -> RoleResponse:
    rol = await service.create_role(
        session,
        organization_id=usuario.organization_id,
        actor_role_keys=await user_role_keys(session, usuario.organization_id, usuario.id),
        actor_permissions=permisos,
        datos=datos,
    )
    return _to_response(rol)


@router.get(
    "/{role_id}",
    summary="Obtener un rol",
    response_model=RoleResponse,
    dependencies=[require_permission(Permission.ROLES_READ)],
)
async def get_role(role_id: uuid.UUID, usuario: CurrentUserDep, session: DbDep) -> RoleResponse:
    return _to_response(await service.get_role(session, usuario.organization_id, role_id))


@router.patch(
    "/{role_id}",
    summary="Actualizar un rol",
    response_model=RoleResponse,
    dependencies=[require_permission(Permission.ROLES_WRITE)],
)
async def update_role(
    role_id: uuid.UUID,
    datos: RoleUpdate,
    usuario: CurrentUserDep,
    session: DbDep,
    permisos: PermissionsDep,
    background_tasks: BackgroundTasks,
) -> RoleResponse:
    rol = await service.update_role(
        session,
        organization_id=usuario.organization_id,
        role_id=role_id,
        actor_user_id=usuario.id,
        actor_role_keys=await user_role_keys(session, usuario.organization_id, usuario.id),
        actor_permissions=permisos,
        datos=datos,
        background_tasks=background_tasks,
    )
    return _to_response(rol)


@router.delete(
    "/{role_id}",
    summary="Eliminar un rol",
    description="Solo roles creados por la organización; los del sistema devuelven 409.",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission(Permission.ROLES_WRITE)],
)
async def delete_role(role_id: uuid.UUID, usuario: CurrentUserDep, session: DbDep) -> Response:
    await service.delete_role(
        session,
        organization_id=usuario.organization_id,
        role_id=role_id,
        actor_role_keys=await user_role_keys(session, usuario.organization_id, usuario.id),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
