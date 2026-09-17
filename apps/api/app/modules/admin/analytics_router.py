"""Endpoints de analítica externa de la plataforma (fase 1 del plan
`260916-2246-cookies-analitica-externa`).

Lectura (`GET` settings y agregados) accesible a `require_platform_staff`
(`superadmin` o `soporte`); escritura de la configuración exclusiva de
`require_superadmin` — mismo reparto que `users_router.py`.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_maintenance_db, require_platform_staff, require_superadmin
from app.modules.admin import analytics_service
from app.modules.admin.analytics_schemas import (
    AnalyticsSettingsResponse,
    AnalyticsSettingsUpdate,
    ConsentimientosStatsResponse,
)
from app.modules.platform.models import PlatformAnalyticsSettings

router = APIRouter(prefix="/admin", tags=["administración"])

MaintenanceDb = Annotated[AsyncSession, Depends(get_maintenance_db)]
PlatformStaff = Annotated[CurrentUser, Depends(require_platform_staff)]
Superadmin = Annotated[CurrentUser, Depends(require_superadmin)]


@router.get(
    "/analytics-settings",
    summary="Identificadores de los proveedores de analítica",
    response_model=AnalyticsSettingsResponse,
)
async def get_analytics_settings(
    _: PlatformStaff, session: MaintenanceDb
) -> PlatformAnalyticsSettings:
    return await analytics_service.obtener_configuracion_analitica(session)


@router.put(
    "/analytics-settings",
    summary="Reemplazar los identificadores de los proveedores",
    response_model=AnalyticsSettingsResponse,
)
async def update_analytics_settings(
    datos: AnalyticsSettingsUpdate, superadmin: Superadmin, session: MaintenanceDb
) -> PlatformAnalyticsSettings:
    return await analytics_service.actualizar_configuracion_analitica(
        session, datos, actor_user_id=superadmin.id
    )


@router.get(
    "/cookie-consents/stats",
    summary="Agregado semanal de consentimientos por categoría",
    response_model=ConsentimientosStatsResponse,
)
async def get_consentimientos_stats(
    _: PlatformStaff,
    session: MaintenanceDb,
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
) -> ConsentimientosStatsResponse:
    try:
        celdas = await analytics_service.agregados_de_consentimiento(session, desde, hasta)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return ConsentimientosStatsResponse(celdas=celdas)
