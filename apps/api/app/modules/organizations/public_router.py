"""Página pública de una organización (opt-in): perfil y sus eventos.

Solo existe si la organización activó `public_page_enabled`. Con el interruptor
apagado, una organización inactiva y una inexistente devuelven **el mismo** 404:
no se puede distinguir cuál de las tres cosas ocurre. El perfil se construye
campo a campo (`PublicOrganizationProfile`): nunca `legal_name` ni
`contact_email`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.core.deps import SessionDep
from app.core.ratelimit import PUBLICO_POR_IP, limit_per_ip
from app.modules.events import service as events_service
from app.modules.events.public_summary import resumen_publico
from app.modules.events.schemas import PublicEventSummary
from app.modules.organizations import service
from app.modules.organizations.schemas import PublicOrganizationProfile
from app.shared.pagination import Page

router = APIRouter(prefix="/public/organizations", tags=["público"])


@router.get(
    "/{org_slug}",
    summary="Perfil público de una organización",
    description="404 si la organización no existe, está inactiva o no activó su página pública.",
    response_model=PublicOrganizationProfile,
    dependencies=[limit_per_ip("public-organization", PUBLICO_POR_IP)],
)
async def get_public_organization(org_slug: str, session: SessionDep) -> PublicOrganizationProfile:
    organizacion = await service.resolve_public_organization(session, org_slug)
    return await service.public_profile(session, organizacion)


@router.get(
    "/{org_slug}/events",
    summary="Eventos públicos de una organización",
    description=(
        "Próximos (los que aún no han terminado, del más cercano al más lejano) o "
        "pasados (del más reciente al más antiguo), paginados. Solo `published` + "
        "`public`. Mismo 404 que el perfil si la página no está activa."
    ),
    response_model=Page[PublicEventSummary],
    dependencies=[limit_per_ip("public-organization-events", PUBLICO_POR_IP)],
)
async def list_public_organization_events(
    org_slug: str,
    session: SessionDep,
    when: Annotated[Literal["upcoming", "past"], Query()] = "upcoming",
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[PublicEventSummary]:
    organizacion = await service.resolve_public_organization(session, org_slug)
    filas, total = await events_service.list_public_events_of_organization(
        session, organizacion.id, upcoming=when == "upcoming", limit=limit, offset=offset
    )
    referencia = await service.public_ref(session, organizacion.id)
    return Page(
        items=[
            resumen_publico(evento, reservadas, precio, cover_url, referencia)
            for evento, reservadas, precio, cover_url in filas
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
