"""Página pública de las políticas y condiciones de un evento.

Resuelve el evento con `resolve_public_event_by_slug` sin cambios, igual que
el formulario de inscripción: solo eventos `published` + `public`; un borrador,
un evento oculto o privado da 404 y no revela que existe.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import SessionDep
from app.core.ratelimit import PUBLICO_POR_IP, limit_per_ip
from app.modules.events import service as events_service
from app.modules.organizations.models import Organization
from app.modules.policies import service
from app.modules.policies.router import version_out
from app.modules.policies.schemas import PublicEventPolicies

router = APIRouter(prefix="/public", tags=["público"])


@router.get(
    "/events/{slug}/policies",
    summary="Políticas y condiciones vigentes de un evento",
    response_model=PublicEventPolicies,
    dependencies=[limit_per_ip("politicas-publicas", PUBLICO_POR_IP)],
)
async def get_public_event_policies(slug: str, session: SessionDep) -> PublicEventPolicies:
    evento = await events_service.resolve_public_event_by_slug(session, slug, para_mostrar=True)
    organizacion = await session.get(Organization, evento.organization_id)
    vigentes = await service.vigentes_de_evento(session, evento.organization_id, evento.id)
    return PublicEventPolicies(
        organization_name=organizacion.name if organizacion is not None else "",
        policies=[version_out(v.version) for v in vigentes if v.version is not None],
        theme=await events_service.tema_publico_del_evento(session, evento),
    )
