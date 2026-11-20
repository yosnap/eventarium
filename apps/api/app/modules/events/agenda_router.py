"""Endpoints de la agenda de un evento: sesiones, sus participantes y las sedes."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.core.deps import CurrentUserDep, DbDep, require_permission
from app.core.permissions import Permission
from app.modules.events import (
    agenda,
    repository,
    sedes,
    session_types,
)
from app.modules.events.models import (
    Event,
    EventSession,
    EventSessionParticipant,
    EventVenue,
)
from app.modules.events.router_comun import obtener_evento_o_404
from app.modules.events.schemas import (
    EventSessionCreate,
    EventSessionResponse,
    EventSessionUpdate,
    EventVenueCreate,
    EventVenueResponse,
    EventVenueUpdate,
    SessionParticipantResponse,
    SessionParticipantsUpdate,
    SessionParticipationOut,
    SessionTypeRef,
)
from app.shared.errors import NotFoundError

# Sin prefijo ni etiqueta: los hereda al incluirse en `events.router`.
router = APIRouter()


def _venue_response(sede: EventVenue) -> EventVenueResponse:
    return EventVenueResponse(
        id=str(sede.id),
        name=sede.name,
        address=sede.address,
        capacity=sede.capacity,
        display_order=sede.display_order,
        latitude=float(sede.latitude) if sede.latitude is not None else None,
        longitude=float(sede.longitude) if sede.longitude is not None else None,
        geocoded_at=sede.geocoded_at,
    )


def _session_response(sesion: EventSession) -> EventSessionResponse:
    return EventSessionResponse(
        id=str(sesion.id),
        session_type=sesion.session_type,
        type=SessionTypeRef(**session_types.referencia(sesion.tipo)),
        title=sesion.title,
        description=sesion.description,
        starts_at=sesion.starts_at,
        ends_at=sesion.ends_at,
        room=sesion.room,
        video_platform=sesion.video_platform,  # type: ignore[arg-type]
        video_url=sesion.video_url,
        materials=sesion.materials,
        sort_order=sesion.sort_order,
        venue_id=str(sesion.venue_id) if sesion.venue_id is not None else None,
        updated_at=sesion.updated_at,
    )


def _session_participant_response(fila: Any) -> SessionParticipantResponse:
    participante, miembro, miembro_org, persona = fila
    return SessionParticipantResponse(
        id=str(participante.id),
        event_member_id=str(miembro.id),
        user_id=str(persona.id),
        email=persona.email,
        first_name=persona.first_name,
        last_name=persona.last_name,
        role_key=participante.role_key,
        sort_order=participante.sort_order,
    )


@router.get(
    "/{event_id}/sessions",
    summary="Listar la agenda de un evento",
    response_model=list[EventSessionResponse],
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_sessions(
    evento: Annotated[Event, Depends(obtener_evento_o_404)], session: DbDep
) -> list[EventSessionResponse]:
    consulta = repository.sessions_query(evento.organization_id, evento.id)
    filas = (await session.execute(consulta)).scalars()
    return [_session_response(sesion) for sesion in filas]


@router.post(
    "/{event_id}/sessions",
    summary="Añadir una sesión a la agenda",
    status_code=status.HTTP_201_CREATED,
    response_model=EventSessionResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def create_session(
    datos: EventSessionCreate,
    evento: Annotated[Event, Depends(obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
) -> EventSessionResponse:
    sesion = await agenda.create_session(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        datos=datos.model_dump(),
    )
    return _session_response(sesion)


@router.patch(
    "/{event_id}/sessions/{session_id}",
    summary="Actualizar una sesión de la agenda",
    response_model=EventSessionResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def update_session(
    datos: EventSessionUpdate,
    evento: Annotated[Event, Depends(obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
    session_id: str,
) -> EventSessionResponse:
    sesion = await agenda.update_session(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        session_id=uuid.UUID(session_id),
        datos=datos.model_dump(exclude_unset=True),
    )
    return _session_response(sesion)


@router.delete(
    "/{event_id}/sessions/{session_id}",
    summary="Quitar una sesión de la agenda",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def delete_session(
    evento: Annotated[Event, Depends(obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
    session_id: str,
) -> None:
    await agenda.delete_session(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        session_id=uuid.UUID(session_id),
    )


@router.get(
    "/{event_id}/participations",
    summary="Participaciones del roster en las sesiones del evento",
    response_model=list[SessionParticipationOut],
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_event_participations(
    evento: Annotated[Event, Depends(obtener_evento_o_404)], session: DbDep
) -> list[SessionParticipationOut]:
    filas = await session.execute(
        select(EventSessionParticipant, EventSession)
        .join(EventSession, EventSession.id == EventSessionParticipant.session_id)
        .where(
            EventSessionParticipant.organization_id == evento.organization_id,
            EventSession.event_id == evento.id,
        )
        .order_by(EventSession.starts_at)
    )
    return [
        SessionParticipationOut(
            event_member_id=str(participacion.event_member_id),
            session_id=str(sesion.id),
            session_title=sesion.title,
            starts_at=sesion.starts_at,
            ends_at=sesion.ends_at,
            role_key=participacion.role_key,
        )
        for participacion, sesion in filas.all()
    ]


@router.get(
    "/{event_id}/sessions/{session_id}/participants",
    summary="Listar los participantes de una sesión",
    response_model=list[SessionParticipantResponse],
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_session_participants(
    evento: Annotated[Event, Depends(obtener_evento_o_404)],
    session: DbDep,
    session_id: str,
) -> list[SessionParticipantResponse]:
    sesion = await repository.get_event_session(
        session, evento.organization_id, evento.id, uuid.UUID(session_id)
    )
    if sesion is None:
        raise NotFoundError("La sesión no existe.")
    consulta = repository.session_participants_query(evento.organization_id, sesion.id)
    filas = (await session.execute(consulta)).all()
    return [_session_participant_response(fila) for fila in filas]


@router.get(
    "/{event_id}/venues",
    summary="Listar las sedes de un evento",
    response_model=list[EventVenueResponse],
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_venues(
    evento: Annotated[Event, Depends(obtener_evento_o_404)], session: DbDep
) -> list[EventVenueResponse]:
    consulta = repository.venues_query(evento.organization_id, evento.id)
    filas = (await session.execute(consulta)).scalars()
    return [_venue_response(sede) for sede in filas]


@router.post(
    "/{event_id}/venues",
    summary="Añadir una sede a un evento",
    status_code=status.HTTP_201_CREATED,
    response_model=EventVenueResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def create_venue(
    datos: EventVenueCreate,
    evento: Annotated[Event, Depends(obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
) -> EventVenueResponse:
    sede = await sedes.create_venue(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        datos=datos.model_dump(),
    )
    return _venue_response(sede)


@router.patch(
    "/{event_id}/venues/{venue_id}",
    summary="Actualizar una sede",
    response_model=EventVenueResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def update_venue(
    datos: EventVenueUpdate,
    evento: Annotated[Event, Depends(obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
    venue_id: str,
) -> EventVenueResponse:
    sede = await sedes.update_venue(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        venue_id=uuid.UUID(venue_id),
        datos=datos.model_dump(exclude_unset=True),
    )
    return _venue_response(sede)


@router.delete(
    "/{event_id}/venues/{venue_id}",
    summary="Quitar una sede de un evento",
    description=(
        "Falla con 409 si alguna sesión de la agenda tiene esta sede asignada — "
        "hay que reasignarla o quitarla primero de esas sesiones."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def delete_venue(
    evento: Annotated[Event, Depends(obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
    venue_id: str,
) -> None:
    await sedes.delete_venue(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        venue_id=uuid.UUID(venue_id),
    )


@router.put(
    "/{event_id}/sessions/{session_id}/participants",
    summary="Reemplazar los participantes de una sesión",
    description=(
        "Reemplaza la lista completa en una sola petición. Lleva control de "
        "concurrencia optimista: `expected_updated_at` debe coincidir con el "
        "`updated_at` actual de la sesión, si no la petición falla con 409."
    ),
    response_model=list[SessionParticipantResponse],
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def replace_session_participants(
    datos: SessionParticipantsUpdate,
    evento: Annotated[Event, Depends(obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
    session_id: str,
) -> list[SessionParticipantResponse]:
    sesion = await agenda.replace_session_participants(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        session_id=uuid.UUID(session_id),
        expected_updated_at=datos.expected_updated_at,
        entries=[
            {"event_member_id": uuid.UUID(p.event_member_id), "role_key": p.role_key}
            for p in datos.participants
        ],
    )
    consulta = repository.session_participants_query(evento.organization_id, sesion.id)
    filas = (await session.execute(consulta)).all()
    return [_session_participant_response(fila) for fila in filas]
