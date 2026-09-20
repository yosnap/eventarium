"""Endpoints de analítica externa de la plataforma (fase 1 del plan
`260916-2246-cookies-analitica-externa`).

Lectura (`GET` settings y agregados) accesible a `require_platform_staff`
(`superadmin` o `soporte`); escritura de la configuración exclusiva de
`require_superadmin` — mismo reparto que `users_router.py`.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    SCOPE_SESION,
    CurrentUser,
    get_maintenance_db,
    require_platform_staff,
    require_superadmin,
)
from app.modules.admin import analytics_service, ga4_client
from app.modules.admin.analytics_schemas import (
    DIAS_PERMITIDOS,
    AnalyticsSettingsResponse,
    AnalyticsSettingsUpdate,
    ConsentimientosStatsResponse,
    DiasDeGa4,
    Ga4StatsResponse,
)
from app.modules.platform.models import PlatformAnalyticsSettings
from app.shared.errors import ValidationDomainError

router = APIRouter(prefix="/admin", tags=["administración"])

MaintenanceDb = Annotated[AsyncSession, Depends(get_maintenance_db, scope=SCOPE_SESION)]
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


@router.get(
    "/analytics-providers/ga4-stats",
    summary="Estadísticas de tráfico de GA4 de los últimos días",
    response_model=Ga4StatsResponse,
)
async def get_ga4_stats(
    _: PlatformStaff,
    dias: int = Query(default=30),
) -> Ga4StatsResponse:
    """Nunca falla con 500/503: si la credencial o la API no están
    disponibles responde con un `estado` explícito — la pantalla del panel
    se renderiza igual (fase 2 del plan de cookies).

    La validación de `dias` es manual (error de dominio 422) en vez de
    `Literal[7, 30]` en la firma: FastAPI entrega los query params como
    `str` y no los coerciona contra un `Literal` de enteros — el mismo
    invariante del enum, validado donde sí funciona.
    """
    if dias not in DIAS_PERMITIDOS:
        raise ValidationDomainError("El parámetro dias solo acepta 7 o 30.")
    return await ga4_client.estadisticas_ultimos_dias(cast(DiasDeGa4, dias))
