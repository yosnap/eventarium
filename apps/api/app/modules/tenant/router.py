"""Endpoints públicos del tenant."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import SessionDep
from app.core.ratelimit import ANALITICA_POR_IP, limit_per_ip
from app.modules.platform import service as platform_service
from app.modules.platform.models import PlatformAnalyticsSettings
from app.modules.tenant.schemas import (
    AnalyticsPublicResponse,
    BrandingResponse,
    PlatformBrandingBlock,
    ResolvedTheme,
)

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.get(
    "/branding",
    summary="Identidad visual de la instalación",
    description=(
        "Eventarium es una SaaS centralizada: una sola instalación, una sola "
        "identidad de marca, sin dominio por organización. Un evento concreto "
        "tiene su propia plantilla y colores, servidos en el detalle público "
        "de ese evento, no aquí."
    ),
    response_model=BrandingResponse,
)
async def branding(session: SessionDep) -> BrandingResponse:
    plataforma = await platform_service.branding_publico(session)
    return BrandingResponse(
        platform=PlatformBrandingBlock(
            name=plataforma.name,
            logo_url=plataforma.logo_url,
            favicon_url=plataforma.favicon_url,
            social_links=[dict(enlace) for enlace in plataforma.social_links],
            theme_template_id=plataforma.theme_template_id,
            theme=(
                ResolvedTheme(
                    id=plataforma.theme.id,
                    key=plataforma.theme.key,
                    name=plataforma.theme.name,
                    tokens=plataforma.theme.tokens,
                    default_mode=plataforma.theme.default_mode,
                )
                if plataforma.theme is not None
                else None
            ),
        )
    )


@router.get(
    "/analytics",
    summary="Identificadores de analítica configurados",
    description=(
        "Los identificadores de los proveedores de analítica que el banner "
        "de cookies cargará solo tras el consentimiento correspondiente. "
        "Público a propósito: son los mismos valores que ya viajarían en el "
        "HTML si los scripts se incrustaran directamente."
    ),
    response_model=AnalyticsPublicResponse,
    dependencies=[limit_per_ip("tenant-analytics", ANALITICA_POR_IP)],
)
async def analytics(session: SessionDep) -> AnalyticsPublicResponse:
    fila = (
        await session.execute(
            select(PlatformAnalyticsSettings).where(
                PlatformAnalyticsSettings.singleton == "default"
            )
        )
    ).scalar_one_or_none()
    return AnalyticsPublicResponse(
        ga4_measurement_id=fila.ga4_measurement_id if fila else None,
        meta_pixel_id=fila.meta_pixel_id if fila else None,
        cloudflare_analytics_token=fila.cloudflare_analytics_token if fila else None,
        gtm_container_id=fila.gtm_container_id if fila else None,
    )
