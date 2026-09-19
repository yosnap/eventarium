"""Endpoints de plataforma de la pasarela de IA (nivel admin).

Viven en `modules/admin` —y no en `modules/ai_gateway`— porque
`platform_ai_settings`/`platform_services` tienen revocado el DML para
`app_user` (V-2): solo la sesión de mantenimiento puede escribirlas, y este
es el único módulo autorizado a usarla. Fichero propio, como
`analytics_router.py`/`platform_router.py`, en vez de engordar `router.py`.

Todas las rutas declaran `Superadmin` a mano, que es la única barrera real:
`get_maintenance_db` (BYPASSRLS) **no autentica por sí solo**. El test
estático `tests/modules/test_admin.py` recorre las rutas de `/admin` y falla
si alguna se queda sin gate (V-9).

Los esquemas se importan de `ai_gateway.schemas`: el formulario del admin y
el del organizador validan lo mismo, y duplicarlos invitaría a que
divergieran.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.deps import CurrentUser, get_maintenance_db, require_superadmin
from app.modules.ai_gateway import repository as ai_repository
from app.modules.ai_gateway import service as ai_service
from app.modules.ai_gateway.schemas import (
    OrganizationServiceOut,
    OrganizationServicesUpdate,
    PlatformAiSettingsOut,
    PlatformAiSettingsUpdate,
    PlatformServicesUpdate,
    ServiceOut,
)
from app.modules.organizations.models import Organization
from app.shared.errors import NotFoundError

router = APIRouter(prefix="/admin", tags=["administración"])

MaintenanceDb = Annotated[AsyncSession, Depends(get_maintenance_db)]
Superadmin = Annotated[CurrentUser, Depends(require_superadmin)]


@router.get(
    "/ai-settings",
    summary="Configuración de IA por defecto de la plataforma",
    description=(
        "Proveedor, modelo, dirección efectiva y techo de gasto de la "
        "instalación. **Nunca** devuelve la clave, ni siquiera a quien la "
        "guardó: solo `has_key`, la pista de sus últimos caracteres y la fecha."
    ),
    response_model=PlatformAiSettingsOut,
)
async def get_platform_ai_settings(_: Superadmin, session: MaintenanceDb) -> PlatformAiSettingsOut:
    return ai_service.vista_de_plataforma(await ai_repository.get_platform_settings(session))


@router.put(
    "/ai-settings",
    summary="Configurar la IA por defecto de la plataforma",
    description=(
        "Guarda proveedor, modelo, clave (write-only) y techo de gasto. La clave "
        "se cifra en reposo con `AI_SETTINGS_ENCRYPTION_KEY`; sin esa variable, "
        "la operación falla con un error de dominio explícito.\n\n"
        "Bajar el techo por debajo de límites de organización ya fijados **no** "
        "se bloquea: el límite efectivo de cada organización es el menor de los "
        "dos, así que el techo manda igualmente."
    ),
    response_model=PlatformAiSettingsOut,
)
async def update_platform_ai_settings(
    datos: PlatformAiSettingsUpdate, superadmin: Superadmin, session: MaintenanceDb
) -> PlatformAiSettingsOut:
    fila = await ai_service.guardar_config_de_plataforma(session, datos)
    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=None,
        action="platform_ai_settings.updated",
        entity_type="platform_ai_settings",
        entity_id=str(fila.id),
        # Nunca la clave ni su pista: la auditoría es otro sitio donde una
        # credencial no debe acabar en claro.
        detail={
            "provider": fila.provider,
            "default_model": fila.default_model,
            "has_key": fila.api_key_encrypted is not None,
        },
    )
    return ai_service.vista_de_plataforma(fila)


@router.get(
    "/services",
    summary="Interruptores globales de servicios",
    response_model=list[ServiceOut],
)
async def list_platform_services(_: Superadmin, session: MaintenanceDb) -> list[ServiceOut]:
    return await ai_service.estado_global_de_servicios(session)


@router.put(
    "/services",
    summary="Activar o desactivar servicios para toda la instalación",
    description=(
        "Un servicio apagado aquí queda apagado para **todas** las "
        "organizaciones; ninguna puede reactivarlo. Una clave de servicio fuera "
        "del catálogo se rechaza con 422."
    ),
    response_model=list[ServiceOut],
)
async def update_platform_services(
    datos: PlatformServicesUpdate, superadmin: Superadmin, session: MaintenanceDb
) -> list[ServiceOut]:
    estado = await ai_service.aplicar_interruptores_globales(session, datos.services)
    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=None,
        action="platform_services.updated",
        entity_type="platform_services",
        entity_id=None,
        detail={"cambios": [cambio.model_dump() for cambio in datos.services]},
    )
    return estado


async def _organizacion_o_404(session: AsyncSession, organization_id: uuid.UUID) -> Organization:
    organizacion = await session.get(Organization, organization_id)
    if organizacion is None:
        raise NotFoundError("La organización no existe.")
    return organizacion


@router.get(
    "/organizations/{organization_id}/services",
    summary="Estado de los servicios de una organización",
    response_model=list[OrganizationServiceOut],
)
async def get_organization_services(
    organization_id: uuid.UUID, _: Superadmin, session: MaintenanceDb
) -> list[OrganizationServiceOut]:
    await _organizacion_o_404(session, organization_id)
    return await ai_service.estado_de_servicios_de_organizacion(session, organization_id)


@router.put(
    "/organizations/{organization_id}/services",
    summary="Forzar a apagado (o volver a heredar) un servicio de una organización",
    description=(
        "El override es binario y solo puede **desactivar**: `enabled=false` "
        "apaga el servicio para esa organización y `enabled=true` borra el "
        "override para volver a heredar el estado global — nunca enciende por "
        "encima de una decisión global de apagado. Lo escribe solo el admin: el "
        "organizador no tiene ningún endpoint de servicios."
    ),
    response_model=list[OrganizationServiceOut],
)
async def update_organization_services(
    organization_id: uuid.UUID,
    datos: OrganizationServicesUpdate,
    superadmin: Superadmin,
    session: MaintenanceDb,
) -> list[OrganizationServiceOut]:
    await _organizacion_o_404(session, organization_id)
    estado = await ai_service.aplicar_override_de_servicios(
        session, organization_id, datos.services
    )
    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=organization_id,
        action="organization_services.updated",
        entity_type="organization_services",
        entity_id=str(organization_id),
        detail={"cambios": [cambio.model_dump() for cambio in datos.services]},
    )
    return estado
