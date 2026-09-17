"""Servicio del directorio de usuarios de plataforma.

Fase 1 de `plans/260916-0810-usuarios-y-permisos-plataforma/`. Corre siempre
bajo `MaintenanceDb` (`app_maintainer`, `BYPASSRLS`) — mismo patrón que el
resto de `admin/`: el directorio es deliberadamente transversal a todas las
organizaciones, no una regresión de RLS (Goals del plan).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.registrations.models import EventRegistration
from app.modules.roles.models import Role
from app.modules.users.models import User
from app.shared.errors import NotFoundError, PermissionDeniedError


async def listar_usuarios(
    session: AsyncSession,
    *,
    q: str | None,
    organization_id: uuid.UUID | None,
    platform_role: str | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[User, str]], int]:
    """Devuelve `(usuario, nombres de sus organizaciones separados por coma)`
    por fila, más el total sin paginar. El filtro por organización se
    resuelve con un `EXISTS`, no un `JOIN`, para no duplicar filas de
    usuario cuando pertenece a varias."""
    condiciones = []
    if q:
        patron = f"%{q}%"
        condiciones.append(
            or_(
                User.email.ilike(patron),
                User.first_name.ilike(patron),
                User.last_name.ilike(patron),
            )
        )
    if platform_role is not None:
        condiciones.append(User.platform_role == platform_role)
    if organization_id is not None:
        condiciones.append(
            User.id.in_(
                select(OrganizationMember.user_id).where(
                    OrganizationMember.organization_id == organization_id
                )
            )
        )

    total = await session.scalar(select(func.count()).select_from(User).where(*condiciones))

    nombres_organizaciones = (
        select(
            OrganizationMember.user_id,
            func.string_agg(Organization.name.distinct(), ", ").label("nombres"),
        )
        .join(Organization, Organization.id == OrganizationMember.organization_id)
        .group_by(OrganizationMember.user_id)
        .subquery()
    )
    filas = (
        await session.execute(
            select(User, func.coalesce(nombres_organizaciones.c.nombres, ""))
            .outerjoin(nombres_organizaciones, nombres_organizaciones.c.user_id == User.id)
            .where(*condiciones)
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [(fila[0], fila[1]) for fila in filas], int(total or 0)


async def obtener_usuario(
    session: AsyncSession, user_id: uuid.UUID
) -> tuple[User, list[tuple[Organization, Role]], int] | None:
    """`None` si no existe. Si existe: el usuario, sus
    `(organización, rol)` y su nº de inscripciones como asistente —todo en
    consultas agregadas, no en un bucle por organización (recomendación del
    predict de este plan)."""
    usuario = await session.get(User, user_id)
    if usuario is None:
        return None

    organizaciones = (
        await session.execute(
            select(Organization, Role)
            .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
            .join(Role, Role.id == OrganizationMember.role_id)
            .where(OrganizationMember.user_id == user_id)
            .order_by(Organization.name)
        )
    ).all()

    nº_inscripciones = await session.scalar(
        select(func.count())
        .select_from(EventRegistration)
        .where(EventRegistration.user_id == user_id)
    )
    return usuario, [(fila[0], fila[1]) for fila in organizaciones], int(nº_inscripciones or 0)


async def desactivar_usuario(
    session: AsyncSession, *, actor_id: uuid.UUID, user_id: uuid.UUID
) -> User:
    """Borrado suave: `is_active = false` + anonimización de nombre/avatar.

    El email se mantiene intacto a propósito (decisión cerrada en la fase 1
    del plan, aplicando la recomendación del predict): hace falta para
    contacto/soporte y para no romper `UniqueConstraint("email")` sin una
    migración de datos aparte. No toca ninguna fila de `EventRegistration`
    (su `email` es una copia propia del formulario, no una referencia a
    `User`; el borrado de inscritos bajo solicitud ya existente,
    `admin_service.borrar_inscrito_por_email`, sigue siendo el mecanismo
    RGPD para eso).
    """
    if actor_id == user_id:
        raise PermissionDeniedError("No puedes desactivar tu propia cuenta.")

    usuario = await session.get(User, user_id)
    if usuario is None:
        raise NotFoundError("El usuario no existe.")

    usuario.is_active = False
    usuario.first_name = None
    usuario.last_name = None
    usuario.avatar_object_key = None
    await session.flush()
    return usuario


async def actualizar_rol_de_plataforma(
    session: AsyncSession, *, actor_id: uuid.UUID, user_id: uuid.UUID, nuevo_rol: str | None
) -> tuple[User, str | None]:
    """Devuelve `(usuario, rol_anterior)` — el rol anterior es para el
    detalle de la auditoría (hallazgo de la fase 2 del plan: reconstruir el
    historial de cambios de un usuario, no solo el estado final)."""
    if actor_id == user_id:
        raise PermissionDeniedError("No puedes retirarte tu propio rol de plataforma.")

    usuario = await session.get(User, user_id)
    if usuario is None:
        raise NotFoundError("El usuario no existe.")

    rol_anterior = usuario.platform_role
    usuario.platform_role = nuevo_rol
    await session.flush()
    return usuario, rol_anterior
