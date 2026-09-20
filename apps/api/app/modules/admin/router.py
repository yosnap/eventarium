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
from app.core.audit_redaction import redactar_importes
from app.core.deps import CurrentUser, get_maintenance_db, require_superadmin
from app.core.ratelimit import (
    AUDIT_LOG_POR_IP,
    RGPD_DELETE_POR_IP,
    RGPD_EXPORT_POR_IP,
    limit_per_ip,
)
from app.modules.admin import metrics_service
from app.modules.admin import service as admin_service
from app.modules.admin.metrics_schemas import MetricasDePlataformaOut
from app.modules.admin.schemas import (
    AuditLogEntry,
    DeleteRegistrationRequest,
    RgpdExportRequest,
)
from app.modules.organizations import service
from app.modules.organizations.models import Organization
from app.modules.organizations.schemas import OrganizationCreate, OrganizationResponse
from app.modules.theme_templates import repository as theme_templates_repository
from app.modules.theme_templates.contrast import comprobar_contraste_de_plantilla
from app.modules.theme_templates.models import ThemeTemplate
from app.modules.theme_templates.schemas import (
    ThemeTemplateCreate,
    ThemeTemplateResponse,
    ThemeTemplateUpdate,
)
from app.shared.errors import ConflictError, NotFoundError, ValidationDomainError
from app.shared.identifiers import new_uuid7
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
    description="Crea la organización con su branding y roles clonados.",
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
        detail={"slug": organizacion.slug, "name": organizacion.name},
    )
    return _to_response(organizacion)


def _to_audit_entry(fila: AuditLog) -> AuditLogEntry:
    return AuditLogEntry(
        id=str(fila.id),
        actor_user_id=str(fila.actor_user_id) if fila.actor_user_id else None,
        organization_id=str(fila.organization_id) if fila.organization_id else None,
        action=fila.action,
        entity_type=fila.entity_type,
        entity_id=fila.entity_id,
        # Los importes no salen por aquí: el administrador de la instalación no
        # ve el negocio de las organizaciones (`app/core/audit_redaction.py`).
        # La fila en base conserva el detalle completo.
        detail=redactar_importes(fila.detail),
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


def _to_theme_template_response(plantilla: ThemeTemplate) -> ThemeTemplateResponse:
    return ThemeTemplateResponse(
        id=str(plantilla.id),
        key=plantilla.key,
        name=plantilla.name,
        tokens=plantilla.tokens,
        is_default=plantilla.is_default,
        default_mode=plantilla.default_mode,
    )


def _rechazar_si_incumple_contraste(tokens: dict[str, dict[str, str]]) -> None:
    """422 con el detalle de cada par incumplido. Se llama **antes** del
    `flush`, así que un rechazo no deja ninguna fila creada ni modificada
    (decisión A de la sesión 3 de validación del plan de UX/UI)."""
    incumplimientos = comprobar_contraste_de_plantilla(tokens)
    if incumplimientos:
        raise ValidationDomainError(
            "La plantilla no supera el contraste mínimo AA (4,5:1) en alguno de sus "
            "pares críticos.",
            extra={
                "errors": [
                    {
                        "primero": incumplimiento.primero,
                        "segundo": incumplimiento.segundo,
                        "modo": incumplimiento.modo,
                        "ratio": incumplimiento.ratio,
                    }
                    for incumplimiento in incumplimientos
                ]
            },
        )


@router.get(
    "/theme-templates",
    summary="Listar el catálogo de plantillas de tema",
    response_model=list[ThemeTemplateResponse],
)
async def list_theme_templates(
    _: Superadmin, session: MaintenanceDb
) -> list[ThemeTemplateResponse]:
    plantillas = await theme_templates_repository.list_theme_templates(session)
    return [_to_theme_template_response(plantilla) for plantilla in plantillas]


@router.post(
    "/theme-templates",
    summary="Crear una plantilla de tema",
    status_code=status.HTTP_201_CREATED,
    response_model=ThemeTemplateResponse,
)
async def create_theme_template(
    datos: ThemeTemplateCreate, superadmin: Superadmin, session: MaintenanceDb
) -> ThemeTemplateResponse:
    _rechazar_si_incumple_contraste(datos.tokens)

    existente = await theme_templates_repository.get_theme_template_by_key(session, datos.key)
    if existente is not None:
        raise ConflictError(f"Ya existe una plantilla con la clave «{datos.key}».")

    if datos.is_default:
        await theme_templates_repository.clear_default(session)

    plantilla = ThemeTemplate(
        id=new_uuid7(),
        key=datos.key,
        name=datos.name,
        tokens=datos.tokens,
        is_default=datos.is_default,
        default_mode=datos.default_mode,
    )
    session.add(plantilla)
    await session.flush()

    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=None,
        action="theme_template.created",
        entity_type="theme_template",
        entity_id=str(plantilla.id),
        detail={"key": plantilla.key, "is_default": plantilla.is_default},
    )
    return _to_theme_template_response(plantilla)


@router.patch(
    "/theme-templates/{template_id}",
    summary="Editar una plantilla de tema",
    description="Edita `name`, `tokens` e `is_default`. No hay borrado en este pase.",
    response_model=ThemeTemplateResponse,
)
async def update_theme_template(
    template_id: uuid.UUID,
    datos: ThemeTemplateUpdate,
    superadmin: Superadmin,
    session: MaintenanceDb,
) -> ThemeTemplateResponse:
    plantilla = await theme_templates_repository.get_theme_template(session, template_id)
    if plantilla is None:
        raise NotFoundError("La plantilla de tema no existe.")

    tokens_nuevos = datos.tokens if datos.tokens is not None else plantilla.tokens
    _rechazar_si_incumple_contraste(tokens_nuevos)

    if datos.name is not None:
        plantilla.name = datos.name
    if datos.tokens is not None:
        plantilla.tokens = datos.tokens
    if datos.is_default is not None:
        if datos.is_default:
            await theme_templates_repository.clear_default(session, except_id=plantilla.id)
        plantilla.is_default = datos.is_default
    if datos.default_mode is not None:
        plantilla.default_mode = datos.default_mode
    await session.flush()

    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=None,
        action="theme_template.updated",
        entity_type="theme_template",
        entity_id=str(plantilla.id),
        detail={"key": plantilla.key, "is_default": plantilla.is_default},
    )
    return _to_theme_template_response(plantilla)


@router.get(
    "/metrics",
    summary="Escritorio de la plataforma",
    description=(
        "Estado de la instalación y qué hace cada organización, para operarla. "
        "**No incluye ningún importe de ninguna organización**: la frontera del "
        "producto es que el administrador de la instalación no ve el negocio de "
        "las organizaciones. Para mirarlo hay que suplantar una cuenta. Los "
        "esquemas de respuesta son un allowlist cerrado, y hay un test que "
        "comprueba que ninguna de sus claves es monetaria.\n\n"
        "Corre con el motor de mantenimiento: es el único módulo autorizado a "
        "saltarse RLS, y precisamente por eso lo que devuelve está acotado por "
        "el esquema y no por la política."
    ),
    response_model=MetricasDePlataformaOut,
)
async def get_platform_metrics(_: Superadmin, session: MaintenanceDb) -> MetricasDePlataformaOut:
    return await metrics_service.metricas_de_la_plataforma(session)
