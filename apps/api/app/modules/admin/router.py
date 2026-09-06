"""Endpoints de superadministración de la instalación.

Este es el **único** módulo de la API autorizado a usar `get_maintenance_db`
(rol `app_maintainer`, con `BYPASSRLS`): dar de alta una organización implica
escribir filas de un tenant que aún no existe, así que ninguna sesión con contexto
RLS podría hacerlo. Un test estático en CI comprueba que ningún otro módulo lo usa.

No hay interfaz de usuario para estos endpoints en la fase 0; el equivalente por
línea de comandos está en `app.cli`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_maintenance_db, require_superadmin
from app.modules.organizations import service
from app.modules.organizations.models import Organization, OrganizationDomain
from app.modules.organizations.schemas import (
    DomainCreate,
    DomainResponse,
    OrganizationCreate,
    OrganizationResponse,
)
from app.shared.errors import NotFoundError

router = APIRouter(prefix="/admin", tags=["administración"])

MaintenanceDb = Annotated[AsyncSession, Depends(get_maintenance_db)]
Superadmin = Annotated[CurrentUser, Depends(require_superadmin)]


def _to_response(organizacion: Organization) -> OrganizationResponse:
    return OrganizationResponse(
        id=str(organizacion.id),
        slug=organizacion.slug,
        name=organizacion.name,
        legal_name=organizacion.legal_name,
        description=organizacion.description,
        website=organizacion.website,
        contact_email=organizacion.contact_email,
        is_active=organizacion.is_active,
    )


@router.get(
    "/organizations",
    summary="Listar organizaciones de la instalación",
    response_model=list[OrganizationResponse],
)
async def list_organizations(_: Superadmin, session: MaintenanceDb) -> list[OrganizationResponse]:
    filas = await session.scalars(select(Organization).order_by(Organization.name))
    return [_to_response(organizacion) for organizacion in filas]


@router.post(
    "/organizations",
    summary="Crear una organización",
    description="Crea la organización con su dominio principal, branding y roles clonados.",
    status_code=status.HTTP_201_CREATED,
    response_model=OrganizationResponse,
)
async def create_organization(
    datos: OrganizationCreate, _: Superadmin, session: MaintenanceDb
) -> OrganizationResponse:
    organizacion = await service.create_organization(
        session,
        slug=datos.slug,
        name=datos.name,
        host=datos.host,
        legal_name=datos.legal_name,
        contact_email=str(datos.contact_email) if datos.contact_email else None,
    )
    return _to_response(organizacion)


@router.post(
    "/organizations/{organization_id}/domains",
    summary="Añadir un dominio a una organización",
    status_code=status.HTTP_201_CREATED,
    response_model=DomainResponse,
)
async def add_domain(
    organization_id: uuid.UUID,
    datos: DomainCreate,
    _: Superadmin,
    session: MaintenanceDb,
) -> DomainResponse:
    dominio = await service.add_domain(
        session,
        organization_id=organization_id,
        host=datos.host,
        is_primary=datos.is_primary,
    )
    return DomainResponse(id=str(dominio.id), host=dominio.host, is_primary=dominio.is_primary)


@router.get(
    "/organizations/{organization_id}/domains",
    summary="Listar los dominios de una organización",
    response_model=list[DomainResponse],
)
async def list_domains(
    organization_id: uuid.UUID, _: Superadmin, session: MaintenanceDb
) -> list[DomainResponse]:
    organizacion = await session.get(Organization, organization_id)
    if organizacion is None:
        raise NotFoundError("La organización no existe.")
    filas = await session.scalars(
        select(OrganizationDomain)
        .where(OrganizationDomain.organization_id == organization_id)
        .order_by(OrganizationDomain.host)
    )
    return [DomainResponse(id=str(d.id), host=d.host, is_primary=d.is_primary) for d in filas]
