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
from app.modules.organizations.invitations_models import OrganizationInvitation
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


async def list_members_grouped(
    session: AsyncSession, organization_id: uuid.UUID, *, limit: int, offset: int
) -> list[tuple[User, list[tuple[OrganizationMember, Role]]]]:
    """Una página de **personas** (no de filas de membresía), con todos sus roles.

    Fase 4 del plan de invitaciones: antes se paginaban filas de
    `organization_members`, así que quien tuviera dos roles ocupaba dos
    puestos de la página y aparecía dos veces en la pantalla. Dos consultas,
    no una con `DISTINCT`: la primera pagina personas por su nombre/correo
    (orden estable); Postgres exige que las columnas del `ORDER BY` estén en
    el `SELECT` para combinarlo con `DISTINCT`, y eso obliga a un
    `GROUP BY` tan largo como esta lista de columnas — más simple pedir
    directamente las personas de esta página y, en una segunda consulta sin
    paginar, todas sus filas de membresía (`IN` sobre un puñado de ids).
    """
    personas = list(
        (
            await session.scalars(
                select(User)
                .join(OrganizationMember, OrganizationMember.user_id == User.id)
                .where(OrganizationMember.organization_id == organization_id)
                .group_by(User.id)
                .order_by(User.first_name, User.last_name, User.email)
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    if not personas:
        return []

    user_ids = [persona.id for persona in personas]
    filas = (
        await session.execute(
            select(OrganizationMember, Role)
            .join(Role, Role.id == OrganizationMember.role_id)
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id.in_(user_ids),
            )
            .order_by(OrganizationMember.created_at)
        )
    ).all()

    roles_por_usuario: dict[uuid.UUID, list[tuple[OrganizationMember, Role]]] = {
        user_id: [] for user_id in user_ids
    }
    for miembro, rol in filas:
        roles_por_usuario[miembro.user_id].append((miembro, rol))

    return [(persona, roles_por_usuario[persona.id]) for persona in personas]


async def count_members_grouped(session: AsyncSession, organization_id: uuid.UUID) -> int:
    """Cuántas **personas** distintas, no cuántas filas de membresía."""
    total = await session.scalar(
        select(func.count(func.distinct(OrganizationMember.user_id))).where(
            OrganizationMember.organization_id == organization_id
        )
    )
    return int(total or 0)


async def member_roles_for_user(
    session: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> list[tuple[OrganizationMember, Role]]:
    """Todos los roles de una persona en la organización.

    Para reconstruir su fila completa tras un alta o una baja de rol: la
    respuesta agrupada (`MemberResponse.roles`) necesita verlos todos, no
    solo el que se acaba de tocar.
    """
    filas = (
        await session.execute(
            select(OrganizationMember, Role)
            .join(Role, Role.id == OrganizationMember.role_id)
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
            .order_by(OrganizationMember.created_at)
        )
    ).all()
    return [(miembro, rol) for miembro, rol in filas]


def best_profile_data(filas: list[tuple[OrganizationMember, Role]]) -> dict[str, Any]:
    """El `profile_data` de la membresía con más campos rellenos.

    Empate → la más antigua (`created_at` ascendente, ya es el orden de
    `filas`). Documentado en `MemberResponse`: es una elección entre varias
    razonables (la otra era «siempre la primera»), no la única posible."""
    if not filas:
        return {}
    mejor = max(
        filas,
        key=lambda par: len(par[0].profile_data),
    )
    return mejor[0].profile_data


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


def invitations_query(organization_id: uuid.UUID) -> Select[Any]:
    """Invitaciones con la clave de su rol, ya filtradas por organización."""
    return (
        select(OrganizationInvitation, Role)
        .join(Role, Role.id == OrganizationInvitation.role_id)
        .where(OrganizationInvitation.organization_id == organization_id)
        .order_by(OrganizationInvitation.created_at.desc())
    )


async def unsafe_select_all(session: AsyncSession, modelo: type[Base]) -> list[Any]:
    """Lee una tabla **sin** filtrar por organización.

    Existe solo para los tests de aislamiento: demuestra que, aunque el repositorio
    olvide el filtro, RLS sigue devolviendo únicamente las filas del tenant activo.
    No debe usarse en código de producción.
    """
    resultado = await session.scalars(select(modelo))
    return list(resultado)
