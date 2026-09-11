"""Endpoints públicos del tenant."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.core.deps import DbPlataformaDep
from app.core.storage import get_storage
from app.core.tenant import extract_host
from app.modules.platform import service as platform_service
from app.modules.platform.host import resolve_host
from app.modules.tenant.schemas import (
    BrandingResponse,
    PlatformBrandingBlock,
    ResolvedTheme,
    SocialLink,
)
from app.shared.errors import NotFoundError

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.get(
    "/branding",
    summary="Identidad visual de la instalación y, si la hay, de la organización",
    description=(
        "Resuelve el host de la petición: si es un host de plataforma, devuelve "
        "solo la identidad de la instalación; si es el host de una organización, "
        "devuelve además la suya. Host de organización desconocido → 404.\n\n"
        "Los campos de nivel raíz (`organization_name`, `template_key`, `theme`…) "
        "se mantienen por compatibilidad con el cliente actual; el bloque "
        "`platform` es el nuevo. Los de raíz se retiran cuando el cliente "
        "consuma el bloque de plataforma."
    ),
    response_model=BrandingResponse,
)
async def branding(session: DbPlataformaDep, request: Request) -> BrandingResponse:
    """Identidad pública resuelta por host.

    Un host de plataforma sirve la identidad de la instalación **sin
    organización**: antes esto era imposible (cualquier host sin organización
    registrada daba 404 y el frontend pintaba «sitio no disponible»). Un host
    de organización sigue exigiéndola, con el mismo fail-closed de siempre.
    """
    plataforma = await platform_service.branding_publico(session)
    bloque_plataforma = PlatformBrandingBlock(
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

    resuelto = await resolve_host(session, extract_host(request))
    organizacion = resuelto.organization

    if resuelto.kind == "platform":
        return BrandingResponse(
            organization_id=None,
            organization_name=None,
            organization_slug=None,
            template_key="classic",
            theme=None,
            social_links=[],
            organizer_blurb=None,
            logo_url=None,
            favicon_url=None,
            platform=bloque_plataforma,
        )

    if organizacion is None:
        # Host sin organización y sin ser de plataforma: se conserva el 404 de
        # siempre en lugar de servir una identidad vacía que el cliente no
        # sabría distinguir de un fallo de configuración.
        raise NotFoundError("No hay ninguna organización asociada al host de esta petición.")

    almacen = get_storage()

    fila = (
        await session.execute(
            text(
                "SELECT o.name, b.template_key, b.social_links, "
                "       b.organizer_blurb, b.logo_object_key, b.favicon_object_key, "
                "       t.id, t.key, t.name, t.tokens "
                "FROM organizations o "
                "LEFT JOIN organization_branding b ON b.organization_id = o.id "
                "LEFT JOIN theme_templates t ON t.id = COALESCE("
                "    b.theme_template_id, "
                "    (SELECT id FROM theme_templates WHERE is_default IS TRUE LIMIT 1)"
                ") "
                "WHERE o.id = :id"
            ),
            {"id": organizacion.id},
        )
    ).first()

    nombre = fila[0] if fila else organizacion.slug
    plantilla = (fila[1] if fila else None) or "classic"
    redes = (fila[2] if fila else None) or []
    blurb = fila[3] if fila else None
    logo = fila[4] if fila else None
    favicon = fila[5] if fila else None
    tema = (
        ResolvedTheme(id=str(fila[6]), key=fila[7], name=fila[8], tokens=fila[9])
        if fila and fila[6] is not None
        else None
    )

    return BrandingResponse(
        organization_id=str(organizacion.id),
        organization_name=nombre,
        organization_slug=organizacion.slug,
        template_key=plantilla,
        theme=tema,
        social_links=[SocialLink(**enlace) for enlace in redes],
        organizer_blurb=blurb,
        logo_url=almacen.public_url(logo) if logo else None,
        favicon_url=almacen.public_url(favicon) if favicon else None,
        platform=bloque_plataforma,
    )
