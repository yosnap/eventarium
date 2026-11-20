"""Página pública de las políticas y condiciones de un evento.

Resuelve el evento con `resolve_public_event_by_slug` sin cambios, igual que
el formulario de inscripción: solo eventos `published` + `public`; un borrador,
un evento oculto o privado da 404 y no revela que existe.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import SessionDep
from app.core.locale import idioma_actual
from app.core.ratelimit import PUBLICO_POR_IP
from app.modules.events import publico as events_publico
from app.modules.events.models import Event
from app.modules.events.public_deps import EVENTO_PARA_MOSTRAR, ruta_de_evento
from app.modules.organizations.models import Organization
from app.modules.policies import service
from app.modules.policies.router import version_out
from app.modules.policies.schemas import PublicEventPolicies
from app.modules.translations.service import traductor_de_evento

router = APIRouter(prefix="/public", tags=["público"])


@ruta_de_evento(
    router,
    "get",
    "/policies",
    summary="Políticas y condiciones vigentes de un evento",
    response_model=PublicEventPolicies,
    limite=("politicas-publicas", PUBLICO_POR_IP),
)
async def get_public_event_policies(
    evento: Annotated[Event, Depends(EVENTO_PARA_MOSTRAR)], session: SessionDep
) -> PublicEventPolicies:
    organizacion = await session.get(Organization, evento.organization_id)
    vigentes = await service.vigentes_de_evento(session, evento.organization_id, evento.id)
    tr = await traductor_de_evento(
        session,
        evento,
        idioma_actual(),
        de_organizacion={
            "policy_version": [v.version.id for v in vigentes if v.version is not None]
        },
    )
    politicas = []
    for vigente in vigentes:
        if vigente.version is None:
            continue
        salida = version_out(vigente.version)
        salida.content = (
            tr.campo(
                "policy_version", vigente.version.id, "content", salida.content, principal=True
            )
            or ""
        )
        politicas.append(salida)
    return PublicEventPolicies(
        organization_name=organizacion.name if organizacion is not None else "",
        policies=politicas,
        # La aceptación queda registrada contra el original: la web avisa de que la
        # traducción es orientativa.
        translated=tr.sirvio("policy_version"),
        original_locale=tr.origen_de("policy_version"),
        theme=await events_publico.tema_publico_del_evento(session, evento),
        **tr.metadatos(),
    )
