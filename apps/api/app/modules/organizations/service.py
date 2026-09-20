"""Servicios de organización.

`create_organization` es una operación transversal: crea filas de una organización
que todavía no existe, así que ninguna sesión con contexto RLS podría hacerlo. Se
ejecuta siempre con una sesión de mantenimiento (`app_maintainer`) desde el CLI, el
seed o el módulo `admin`; nunca desde un router de negocio.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization, OrganizationBranding
from app.modules.roles.models import Role, RolePermission, RoleProfileField
from app.modules.roles.system_roles import SYSTEM_ROLE_TEMPLATES
from app.shared.errors import ConflictError


async def clone_system_roles(session: AsyncSession, organization_id: uuid.UUID) -> dict[str, Role]:
    """Clona las plantillas del sistema como roles propios de la organización."""
    creados: dict[str, Role] = {}
    for plantilla in SYSTEM_ROLE_TEMPLATES:
        rol = Role(
            organization_id=organization_id,
            key=plantilla.key,
            name=plantilla.name,
            description=plantilla.description,
            is_system=True,
            system_template_key=plantilla.key,
        )
        session.add(rol)
        await session.flush()

        for permiso in plantilla.permissions:
            session.add(
                RolePermission(
                    role_id=rol.id,
                    permission=permiso.value,
                    organization_id=organization_id,
                )
            )
        for campo in plantilla.profile_fields:
            session.add(
                RoleProfileField(
                    organization_id=organization_id,
                    role_id=rol.id,
                    key=campo.key,
                    label=campo.label,
                    field_type=campo.field_type,
                    options=campo.options,
                    is_required=campo.is_required,
                    # Los campos que vienen de la plantilla no se pueden borrar.
                    is_locked=True,
                    sort_order=campo.sort_order,
                )
            )
        creados[plantilla.key] = rol

    await session.flush()
    return creados


async def create_organization(
    session: AsyncSession,
    *,
    slug: str,
    name: str,
    legal_name: str | None = None,
    contact_email: str | None = None,
) -> Organization:
    """Crea una organización con su branding y roles clonados.

    Sin dominio propio (fase 6 del plan de organización sin dominio): ya no
    crea ninguna fila en `organization_domains`, retirada del esquema.
    """
    slug_limpio = slug.strip().lower()

    existente = await session.scalar(select(Organization).where(Organization.slug == slug_limpio))
    if existente is not None:
        raise ConflictError(f"Ya existe una organización con el identificador «{slug_limpio}».")

    organizacion = Organization(
        slug=slug_limpio,
        name=name,
        legal_name=legal_name,
        contact_email=contact_email,
        is_active=True,
    )
    session.add(organizacion)
    await session.flush()

    session.add(
        OrganizationBranding(
            organization_id=organizacion.id,
            social_links=[],
        )
    )
    await clone_system_roles(session, organizacion.id)
    await session.flush()
    return organizacion
