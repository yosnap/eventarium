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
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog, registrar_auditoria
from app.core.deps import CurrentUser, get_maintenance_db, require_superadmin
from app.core.ratelimit import (
    AUDIT_LOG_POR_IP,
    RGPD_DELETE_POR_IP,
    RGPD_EXPORT_POR_IP,
    limit_per_ip,
)
from app.modules.admin import service as admin_service
from app.modules.admin.schemas import (
    AuditLogEntry,
    DeleteRegistrationRequest,
    RgpdExportRequest,
)
from app.modules.organizations import service
from app.modules.organizations.models import Organization, OrganizationDomain
from app.modules.organizations.schemas import (
    DomainCreate,
    DomainResponse,
    OrganizationCreate,
    OrganizationResponse,
)
from app.shared.errors import NotFoundError
from app.shared.pagination import Page, PageParams, page_params

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
    datos: OrganizationCreate, superadmin: Superadmin, session: MaintenanceDb
) -> OrganizationResponse:
    organizacion = await service.create_organization(
        session,
        slug=datos.slug,
        name=datos.name,
        host=datos.host,
        legal_name=datos.legal_name,
        contact_email=str(datos.contact_email) if datos.contact_email else None,
    )
    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=organizacion.id,
        action="organization.created",
        entity_type="organization",
        entity_id=str(organizacion.id),
        detail={"slug": organizacion.slug, "name": organizacion.name, "host": datos.host},
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
    superadmin: Superadmin,
    session: MaintenanceDb,
) -> DomainResponse:
    dominio = await service.add_domain(
        session,
        organization_id=organization_id,
        host=datos.host,
        is_primary=datos.is_primary,
    )
    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=organization_id,
        action="organization_domain.created",
        entity_type="organization_domain",
        entity_id=str(dominio.id),
        detail={"host": dominio.host, "is_primary": dominio.is_primary},
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


def _to_audit_entry(fila: AuditLog) -> AuditLogEntry:
    return AuditLogEntry(
        id=str(fila.id),
        actor_user_id=str(fila.actor_user_id) if fila.actor_user_id else None,
        organization_id=str(fila.organization_id) if fila.organization_id else None,
        action=fila.action,
        entity_type=fila.entity_type,
        entity_id=fila.entity_id,
        detail=fila.detail,
        created_at=fila.created_at,
    )


@router.get(
    "/audit-log",
    summary="Listar el registro de auditoría de la instalación",
    description=(
        "Filtros opcionales por organización, rango de fechas y tipo de acción. "
        "No hay ningún `Permission` de rol de organización que sustituya a "
        "`Superadmin` aquí."
    ),
    response_model=Page[AuditLogEntry],
    dependencies=[limit_per_ip("admin-audit-log", AUDIT_LOG_POR_IP)],
)
async def list_audit_log(
    _: Superadmin,
    session: MaintenanceDb,
    paginacion: Annotated[PageParams, Depends(page_params)],
    organization_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    action: str | None = None,
) -> Page[AuditLogEntry]:
    filas, total = await admin_service.list_audit_log(
        session,
        organization_id=organization_id,
        date_from=date_from,
        date_to=date_to,
        action=action,
        limit=paginacion.limit,
        offset=paginacion.offset,
    )
    return Page[AuditLogEntry](
        items=[_to_audit_entry(fila) for fila in filas],
        total=total,
        limit=paginacion.limit,
        offset=paginacion.offset,
    )


@router.post(
    "/events/{event_id}/rgpd-export",
    summary="Exportar en RGPD las inscripciones y entradas de un evento",
    description=(
        "ZIP con un CSV de inscripciones (con sus respuestas) y un CSV de "
        "entradas (sin el JWT del QR, que es una credencial de acceso físico "
        "válida). Exige reautenticación por contraseña en el body. Es un "
        "`POST` y no un `GET` a propósito: la Fetch API (`fetch(url, {method: "
        "'GET', body})`) prohíbe cuerpo en peticiones `GET` — lanza un "
        "`TypeError` antes de llegar a la red — y el frontend usa "
        "`provideHttpClient(withFetch())`. Un `GET` con reautenticación por "
        "contraseña en el body nunca habría funcionado desde el navegador."
    ),
    dependencies=[limit_per_ip("admin-rgpd-export", RGPD_EXPORT_POR_IP)],
)
async def export_event_rgpd(
    event_id: uuid.UUID,
    datos: RgpdExportRequest,
    superadmin: Superadmin,
    session: MaintenanceDb,
) -> Response:
    await admin_service.verificar_password_de_superadmin(
        session, user_id=superadmin.id, password=datos.password
    )
    contenido_zip, evento = await admin_service.exportar_rgpd_evento(session, event_id=event_id)
    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=evento.organization_id,
        action="registration.rgpd_export",
        entity_type="event",
        entity_id=str(evento.id),
        detail={"event_slug": evento.slug},
    )
    return Response(
        content=contenido_zip,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{evento.slug}-rgpd.zip"'},
    )


@router.delete(
    "/registrations/by-email",
    summary="Borrar (RGPD) la inscripción de una persona a un evento por email",
    description=(
        "Reutiliza el servicio de cancelación (revoca la entrada y promueve la "
        "lista de espera si liberaba una plaza) y anonimiza los escaneos de la "
        "entrada antes del borrado real de la fila. Exige reautenticación por "
        "contraseña en el body. `audit_log` guarda un hash con sal del email, "
        "nunca en claro."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[limit_per_ip("admin-rgpd-delete", RGPD_DELETE_POR_IP)],
)
async def delete_registration_by_email(
    datos: DeleteRegistrationRequest,
    superadmin: Superadmin,
    session: MaintenanceDb,
) -> Response:
    await admin_service.verificar_password_de_superadmin(
        session, user_id=superadmin.id, password=datos.password
    )
    registration_id, organization_id = await admin_service.borrar_inscrito_por_email(
        session, event_id=uuid.UUID(datos.event_id), email=datos.email
    )
    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=organization_id,
        action="registration.rgpd_delete",
        entity_type="event_registration",
        entity_id=str(registration_id),
        detail=admin_service.audit_detail_borrado(
            email=datos.email, registration_id=registration_id
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
