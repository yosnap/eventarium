"""Endpoints del usuario autenticado."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import CurrentUserDep, DbDep, PermissionsDep
from app.core.permissions import Permission
from app.modules.organizations.repository import user_role_keys
from app.modules.users.schemas import CurrentUserResponse

router = APIRouter(prefix="/users", tags=["usuarios"])


@router.get(
    "/me",
    summary="Usuario autenticado",
    description="Devuelve el usuario, sus roles y sus permisos en la organización actual.",
    response_model=CurrentUserResponse,
)
async def get_me(
    usuario: CurrentUserDep, session: DbDep, permisos: PermissionsDep
) -> CurrentUserResponse:
    claves = await user_role_keys(session, usuario.organization_id, usuario.id)
    return CurrentUserResponse(
        id=str(usuario.id),
        email=usuario.email,
        full_name=usuario.full_name,
        is_superadmin=usuario.is_superadmin,
        organization_id=str(usuario.organization_id),
        roles=sorted(claves),
        permissions=sorted(Permission(p) for p in permisos),
    )
