"""Endpoints del directorio de usuarios de plataforma.

Fase 1-2 de `plans/260916-0810-usuarios-y-permisos-plataforma/`. Lectura
(`GET`) accesible a `require_platform_staff` (`superadmin` o `soporte`);
escritura sensible (desactivar, cambiar rol de plataforma) exclusiva de
`require_superadmin` — `soporte` nunca alcanza estos dos últimos endpoints.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.deps import CurrentUser, get_maintenance_db, require_platform_staff, require_superadmin
from app.modules.admin import users_service
from app.modules.admin.users_schemas import (
    PlatformRoleUpdate,
    PlatformUserActionResult,
    PlatformUserDetail,
    PlatformUserOrganization,
    PlatformUserSummary,
)
from app.modules.auth.service import revoke_all_families
from app.shared.errors import NotFoundError
from app.shared.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/admin/users", tags=["administración"])

MaintenanceDb = Annotated[AsyncSession, Depends(get_maintenance_db)]
PlatformStaff = Annotated[CurrentUser, Depends(require_platform_staff)]
Superadmin = Annotated[CurrentUser, Depends(require_superadmin)]


@router.get(
    "",
    summary="Listar el directorio de usuarios de la instalación",
    description=(
        "Toda persona con cuenta (organizador, asistente con cuenta, o "
        "ambos), filtrable por organización, rol de plataforma y "
        "búsqueda en email/nombre. Accesible a `soporte`, no solo a "
        "`superadmin`."
    ),
    response_model=Page[PlatformUserSummary],
)
async def list_users(
    _: PlatformStaff,
    session: MaintenanceDb,
    paginacion: Annotated[PageParams, Depends(page_params)],
    q: str | None = None,
    organization_id: uuid.UUID | None = None,
    platform_role: str | None = None,
) -> Page[PlatformUserSummary]:
    filas, total = await users_service.listar_usuarios(
        session,
        q=q,
        organization_id=organization_id,
        platform_role=platform_role,
        limit=paginacion.limit,
        offset=paginacion.offset,
    )
    return Page[PlatformUserSummary](
        items=[
            PlatformUserSummary(
                id=str(usuario.id),
                email=usuario.email,
                first_name=usuario.first_name,
                last_name=usuario.last_name,
                is_active=usuario.is_active,
                platform_role=usuario.platform_role,
                created_at=usuario.created_at,
                organization_names=nombres_organizaciones,
            )
            for usuario, nombres_organizaciones in filas
        ],
        total=total,
        limit=paginacion.limit,
        offset=paginacion.offset,
    )


@router.get(
    "/{user_id}",
    summary="Ver el detalle de un usuario",
    description=(
        "Organizaciones en las que participa y con qué rol, nº de "
        "inscripciones como asistente, rol de plataforma y preferencia de "
        "notificaciones (solo lectura: la persona la activa sobre sí misma "
        "desde su perfil, nunca se escribe aquí). Accesible a `soporte`."
    ),
)
async def get_user(
    user_id: uuid.UUID,
    _: PlatformStaff,
    session: MaintenanceDb,
) -> PlatformUserDetail:
    resultado = await users_service.obtener_usuario(session, user_id)
    if resultado is None:
        raise NotFoundError("El usuario no existe.")
    usuario, organizaciones, nº_inscripciones = resultado
    return PlatformUserDetail(
        id=str(usuario.id),
        email=usuario.email,
        first_name=usuario.first_name,
        last_name=usuario.last_name,
        is_active=usuario.is_active,
        platform_role=usuario.platform_role,
        notify_similar_events=usuario.notify_similar_events,
        created_at=usuario.created_at,
        organizations=[
            PlatformUserOrganization(
                organization_id=str(organizacion.id),
                organization_name=organizacion.name,
                role_name=rol.name,
            )
            for organizacion, rol in organizaciones
        ],
        registrations_count=nº_inscripciones,
    )


@router.post(
    "/{user_id}/deactivate",
    summary="Desactivar un usuario (borrado suave)",
    description=(
        "`is_active = false` y anonimización de nombre/avatar; el email se "
        "mantiene. No toca sus organizaciones ni sus inscripciones. Revoca "
        "todas sus sesiones activas. Exclusivo de `superadmin`; rechaza la "
        "propia cuenta como objetivo."
    ),
)
async def deactivate_user(
    user_id: uuid.UUID,
    superadmin: Superadmin,
    session: MaintenanceDb,
) -> PlatformUserActionResult:
    usuario = await users_service.desactivar_usuario(session, actor_id=superadmin.id, user_id=user_id)
    await revoke_all_families(usuario.id)
    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=None,
        action="user.deactivate",
        entity_type="user",
        entity_id=str(usuario.id),
        subject_user_id=usuario.id,
    )
    return PlatformUserActionResult(
        id=str(usuario.id),
        email=usuario.email,
        first_name=usuario.first_name,
        last_name=usuario.last_name,
        is_active=usuario.is_active,
        platform_role=usuario.platform_role,
    )


@router.put(
    "/{user_id}/platform-role",
    summary="Asignar o retirar el rol de plataforma soporte",
    description=(
        "`platform_role: 'soporte' | null`. Nunca acepta `'superadmin'` — "
        "ese poder sigue siendo exclusivamente `is_superadmin`. Exclusivo "
        "de `superadmin`; rechaza el propio rol como objetivo."
    ),
)
async def update_platform_role(
    user_id: uuid.UUID,
    datos: PlatformRoleUpdate,
    superadmin: Superadmin,
    session: MaintenanceDb,
) -> PlatformUserActionResult:
    usuario, rol_anterior = await users_service.actualizar_rol_de_plataforma(
        session, actor_id=superadmin.id, user_id=user_id, nuevo_rol=datos.platform_role
    )
    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=None,
        action="user.platform_role.assign" if datos.platform_role else "user.platform_role.revoke",
        entity_type="user",
        entity_id=str(usuario.id),
        subject_user_id=usuario.id,
        detail={"before": rol_anterior, "after": datos.platform_role},
    )
    return PlatformUserActionResult(
        id=str(usuario.id),
        email=usuario.email,
        first_name=usuario.first_name,
        last_name=usuario.last_name,
        is_active=usuario.is_active,
        platform_role=usuario.platform_role,
    )
