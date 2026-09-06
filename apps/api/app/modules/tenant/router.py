"""Endpoints públicos del tenant."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.core.deps import DbDep, get_current_organization
from app.core.storage import get_storage
from app.core.tenant import ResolvedOrganization
from app.modules.tenant.schemas import (
    DEFAULT_COLORS,
    DEFAULT_FONTS,
    BrandingResponse,
    SocialLink,
)

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.get(
    "/branding",
    summary="Identidad visual de la organización",
    description=(
        "Devuelve colores, tipografías, logotipo y plantilla de la organización "
        "asociada al host de la petición. Host desconocido → 404."
    ),
    response_model=BrandingResponse,
)
async def branding(
    session: DbDep,
    organizacion: Annotated[ResolvedOrganization, Depends(get_current_organization)],
) -> BrandingResponse:
    almacen = get_storage()

    fila = (
        await session.execute(
            text(
                "SELECT o.name, b.template_key, b.colors, b.fonts, b.social_links, "
                "       b.organizer_blurb, b.logo_object_key, b.favicon_object_key "
                "FROM organizations o "
                "LEFT JOIN organization_branding b ON b.organization_id = o.id "
                "WHERE o.id = :id"
            ),
            {"id": organizacion.id},
        )
    ).first()

    nombre = fila[0] if fila else organizacion.slug
    plantilla = (fila[1] if fila else None) or "classic"
    colores = {**DEFAULT_COLORS, **((fila[2] if fila else None) or {})}
    fuentes = {**DEFAULT_FONTS, **((fila[3] if fila else None) or {})}
    redes = (fila[4] if fila else None) or []
    blurb = fila[5] if fila else None
    logo = fila[6] if fila else None
    favicon = fila[7] if fila else None

    return BrandingResponse(
        organization_id=str(organizacion.id),
        organization_name=nombre,
        organization_slug=organizacion.slug,
        template_key=plantilla,
        colors=colores,
        fonts=fuentes,
        social_links=[SocialLink(**enlace) for enlace in redes],
        organizer_blurb=blurb,
        logo_url=almacen.public_url(logo) if logo else None,
        favicon_url=almacen.public_url(favicon) if favicon else None,
    )
