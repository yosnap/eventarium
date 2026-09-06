"""Acceso a datos de organizaciones y membresías.

Los repositorios filtran siempre por `organization_id` de forma explícita. RLS es la
red de seguridad, no el filtro principal: si algún día una política se relaja, el
código sigue siendo correcto.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.modules.organizations.models import (
    Organization,
    OrganizationBranding,
    OrganizationMember,
)
from app.modules.roles.models import Role
from app.modules.users.models import User


async def get_organization(
    session: AsyncSession, organization_id: uuid.UUID
) -> Organization | None:
    resultado: Organization | None = await session.scalar(
        select(Organization).where(Organization.id == organization_id)
    )
    return resultado


async def get_branding(
    session: AsyncSession, organization_id: uuid.UUID
) -> OrganizationBranding | None:
    resultado: OrganizationBranding | None = await session.scalar(
        select(OrganizationBranding).where(OrganizationBranding.organization_id == organization_id)
    )
    return resultado


def members_query(organization_id: uuid.UUID) -> Select[Any]:
    """Miembros con su usuario y su rol, ya filtrados por organización."""
    return (
        select(OrganizationMember, User, Role)
        .join(User, User.id == OrganizationMember.user_id)
        .join(Role, Role.id == OrganizationMember.role_id)
        .where(OrganizationMember.organization_id == organization_id)
        .order_by(User.full_name, User.email)
    )


async def count_members(session: AsyncSession, organization_id: uuid.UUID) -> int:
    total = await session.scalar(
        select(func.count())
        .select_from(OrganizationMember)
        .where(OrganizationMember.organization_id == organization_id)
    )
    return int(total or 0)


async def get_member(
    session: AsyncSession, organization_id: uuid.UUID, member_id: uuid.UUID
) -> OrganizationMember | None:
    resultado: OrganizationMember | None = await session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == organization_id,
        )
    )
    return resultado


async def user_role_keys(
    session: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> set[str]:
    """Claves de los roles que tiene una persona en la organización."""
    filas = await session.scalars(
        select(Role.key)
        .join(OrganizationMember, OrganizationMember.role_id == Role.id)
        .where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
    )
    return set(filas)


async def unsafe_select_all(session: AsyncSession, modelo: type[Base]) -> list[Any]:
    """Lee una tabla **sin** filtrar por organización.

    Existe solo para los tests de aislamiento: demuestra que, aunque el repositorio
    olvide el filtro, RLS sigue devolviendo únicamente las filas del tenant activo.
    No debe usarse en código de producción.
    """
    resultado = await session.scalars(select(modelo))
    return list(resultado)
