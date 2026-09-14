"""Endpoints públicos del tenant."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import SessionDep
from app.modules.platform import service as platform_service
from app.modules.tenant.schemas import BrandingResponse, PlatformBrandingBlock, ResolvedTheme

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
                )
                if plataforma.theme is not None
                else None
            ),
        )
    )
