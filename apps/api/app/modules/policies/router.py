"""Endpoints del panel para las políticas y condiciones propias del organizador.

Escribir exige `organizations:write` también para la sustitución en un
evento: estos textos obligan jurídicamente a toda la organización, y un rol a
medida puede tener `events:write` sin `organizations:write`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, DbDep, PermissionsDep, require_permission
from app.core.permissions import Permission
from app.modules.events import repository as events_repository
from app.modules.events.models import Event
from app.modules.policies import service
from app.modules.policies.models import TIPOS_DE_POLITICA, OrganizationPolicyVersion
from app.modules.policies.schemas import (
    EventPoliciesOut,
    EventPolicyItem,
    OrganizationPoliciesOut,
    OrganizationPolicyItem,
    PolicyUpdate,
    PolicyVersionOut,
    TipoDePolitica,
)
from app.shared.errors import NotFoundError

router_organizacion = APIRouter(prefix="/organizations/me/policies", tags=["políticas"])
router_evento = APIRouter(prefix="/events/{event_id}/policies", tags=["políticas"])


def version_out(fila: OrganizationPolicyVersion) -> PolicyVersionOut:
    return PolicyVersionOut(
        version_id=str(fila.id),
        kind=fila.kind,  # type: ignore[arg-type]
        version=fila.version,
        content=fila.content or "",
        created_at=fila.created_at,
    )


async def _obtener_evento_o_404(
    session: DbDep, usuario: CurrentUserDep, event_id: uuid.UUID
) -> Event:
    evento = await events_repository.get_event(session, usuario.organization_id, event_id)
    if evento is None:
        raise NotFoundError("El evento no existe.")
    return evento


EventoDep = Annotated[Event, Depends(_obtener_evento_o_404)]


async def _items_de_organizacion(
    session: DbDep, organization_id: uuid.UUID
) -> list[OrganizationPolicyItem]:
    ultimas = await service.ultimas_de_organizacion(session, organization_id)
    items = []
    for kind in TIPOS_DE_POLITICA:
        fila = ultimas.get(kind)
        items.append(
            OrganizationPolicyItem(
                kind=kind,  # type: ignore[arg-type]
                current=version_out(fila) if fila is not None and fila.content else None,
                last_version=fila.version if fila is not None else None,
            )
        )
    return items


async def _items_de_evento(session: DbDep, evento: Event) -> list[EventPolicyItem]:
    vigentes = await service.vigentes_de_evento(session, evento.organization_id, evento.id)
    return [
        EventPolicyItem(
            kind=vigente.kind,  # type: ignore[arg-type]
            origin=vigente.origen,  # type: ignore[arg-type]
            current=version_out(vigente.version) if vigente.version is not None else None,
            organization=(
                version_out(vigente.de_organizacion)
                if vigente.de_organizacion is not None
                else None
            ),
        )
        for vigente in vigentes
    ]


@router_organizacion.get(
    "",
    summary="Textos por defecto de la organización",
    response_model=OrganizationPoliciesOut,
    dependencies=[require_permission(Permission.ORGANIZATIONS_READ)],
)
async def list_organization_policies(
    session: DbDep, usuario: CurrentUserDep, permisos: PermissionsDep
) -> OrganizationPoliciesOut:
    return OrganizationPoliciesOut(
        can_edit=Permission.ORGANIZATIONS_WRITE in permisos,
        items=await _items_de_organizacion(session, usuario.organization_id),
    )


@router_organizacion.put(
    "/{kind}",
    summary="Guardar un texto por defecto de la organización (vacío = retirar)",
    response_model=OrganizationPoliciesOut,
    dependencies=[require_permission(Permission.ORGANIZATIONS_WRITE)],
)
async def save_organization_policy(
    kind: TipoDePolitica, datos: PolicyUpdate, session: DbDep, usuario: CurrentUserDep
) -> OrganizationPoliciesOut:
    await service.guardar_version(
        session,
        organization_id=usuario.organization_id,
        event_id=None,
        kind=kind,
        content=datos.content,
        user_id=usuario.id,
    )
    return OrganizationPoliciesOut(
        can_edit=True, items=await _items_de_organizacion(session, usuario.organization_id)
    )


@router_evento.get(
    "",
    summary="Textos vigentes de un evento y de dónde salen",
    response_model=EventPoliciesOut,
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_event_policies(
    evento: EventoDep, session: DbDep, permisos: PermissionsDep
) -> EventPoliciesOut:
    return EventPoliciesOut(
        can_edit=Permission.ORGANIZATIONS_WRITE in permisos,
        items=await _items_de_evento(session, evento),
    )


@router_evento.put(
    "/{kind}",
    summary="Sustituir un texto en un evento (nulo = volver a heredar)",
    response_model=EventPoliciesOut,
    dependencies=[require_permission(Permission.ORGANIZATIONS_WRITE)],
)
async def save_event_policy(
    kind: TipoDePolitica,
    datos: PolicyUpdate,
    evento: EventoDep,
    session: DbDep,
    usuario: CurrentUserDep,
) -> EventPoliciesOut:
    await service.guardar_version(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        kind=kind,
        content=datos.content,
        user_id=usuario.id,
    )
    return EventPoliciesOut(can_edit=True, items=await _items_de_evento(session, evento))


@router_evento.get(
    "/versions/{version_id}",
    summary="Contenido exacto de una versión (lo que aceptó una inscripción)",
    response_model=PolicyVersionOut,
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def get_policy_version(
    version_id: uuid.UUID, evento: EventoDep, session: DbDep
) -> PolicyVersionOut:
    fila = await service.obtener_version(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        version_id=version_id,
    )
    return version_out(fila)
