"""Endpoints de eventos y agenda de la organización actual."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile, status

from app.core.deps import CurrentUserDep, DbDep, require_permission
from app.core.permissions import Permission
from app.core.storage import build_object_key, get_storage, validate_upload
from app.modules.events import repository, service
from app.modules.events.models import Event, EventSession
from app.modules.events.schemas import (
    EventCreate,
    EventResponse,
    EventSessionCreate,
    EventSessionResponse,
    EventSessionUpdate,
    EventStatus,
    EventUpdate,
)
from app.shared.errors import NotFoundError
from app.shared.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/events", tags=["eventos"])


def _event_response(evento: Event) -> EventResponse:
    almacen = get_storage()
    return EventResponse(
        id=str(evento.id),
        slug=evento.slug,
        title=evento.title,
        summary=evento.summary,
        description=evento.description,
        cover_url=almacen.public_url(evento.cover_object_key) if evento.cover_object_key else None,
        status=evento.status,  # type: ignore[arg-type]
        visibility=evento.visibility,  # type: ignore[arg-type]
        timezone=evento.timezone,
        starts_at=evento.starts_at,
        ends_at=evento.ends_at,
        location_mode=evento.location_mode,  # type: ignore[arg-type]
        location_name=evento.location_name,
        location_address=evento.location_address,
        online_url=evento.online_url,
        capacity=evento.capacity,
        registration_mode=evento.registration_mode,  # type: ignore[arg-type]
        email_verification_required=evento.email_verification_required,
    )


def _session_response(sesion: EventSession) -> EventSessionResponse:
    return EventSessionResponse(
        id=str(sesion.id),
        session_type=sesion.session_type,  # type: ignore[arg-type]
        title=sesion.title,
        description=sesion.description,
        starts_at=sesion.starts_at,
        ends_at=sesion.ends_at,
        room=sesion.room,
        video_platform=sesion.video_platform,  # type: ignore[arg-type]
        video_url=sesion.video_url,
        materials=sesion.materials,
        sort_order=sesion.sort_order,
    )


async def _obtener_evento_o_404(session: DbDep, usuario: CurrentUserDep, event_id: str) -> Event:
    evento = await repository.get_event(session, usuario.organization_id, uuid.UUID(event_id))
    if evento is None:
        raise NotFoundError("El evento no existe.")
    return evento


@router.get(
    "",
    summary="Listar eventos",
    response_model=Page[EventResponse],
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_events(
    usuario: CurrentUserDep,
    session: DbDep,
    paginacion: Annotated[PageParams, Depends(page_params)],
    estado: Annotated[EventStatus | None, Query(alias="status")] = None,
) -> Page[EventResponse]:
    consulta = repository.events_query(usuario.organization_id, status=estado)
    total = len((await session.execute(consulta)).all())
    filas = (
        await session.execute(consulta.limit(paginacion.limit).offset(paginacion.offset))
    ).scalars()
    return Page[EventResponse](
        items=[_event_response(evento) for evento in filas],
        total=total,
        limit=paginacion.limit,
        offset=paginacion.offset,
    )


@router.post(
    "",
    summary="Crear un evento",
    status_code=status.HTTP_201_CREATED,
    response_model=EventResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def create_event(
    datos: EventCreate, usuario: CurrentUserDep, session: DbDep
) -> EventResponse:
    evento = await service.create_event(
        session, organization_id=usuario.organization_id, datos=datos.model_dump()
    )
    return _event_response(evento)


@router.get(
    "/{event_id}",
    summary="Ver un evento",
    response_model=EventResponse,
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def get_event(evento: Annotated[Event, Depends(_obtener_evento_o_404)]) -> EventResponse:
    return _event_response(evento)


@router.patch(
    "/{event_id}",
    summary="Actualizar un evento",
    response_model=EventResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def update_event(
    datos: EventUpdate, usuario: CurrentUserDep, session: DbDep, event_id: str
) -> EventResponse:
    evento = await service.update_event(
        session,
        organization_id=usuario.organization_id,
        event_id=uuid.UUID(event_id),
        datos=datos.model_dump(exclude_unset=True),
    )
    return _event_response(evento)


@router.put(
    "/{event_id}/cover",
    summary="Subir la portada del evento",
    description="Acepta PNG, JPEG o WebP de hasta 5 MB. El tipo se comprueba por contenido.",
    response_model=EventResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def upload_cover(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    background_tasks: BackgroundTasks,
    fichero: Annotated[UploadFile, File(description="Imagen de portada")],
) -> EventResponse:
    contenido = await fichero.read()
    mime, extension = validate_upload(contenido)

    almacen = get_storage()
    clave = build_object_key(evento.organization_id, f"events/{evento.id}/cover", extension)
    await almacen.put_object(clave, contenido, mime)

    anterior = evento.cover_object_key
    evento.cover_object_key = clave
    await session.flush()

    # El objeto anterior se borra en un `BackgroundTask`, que Starlette ejecuta
    # tras enviar la respuesta — y por tanto tras el `commit` real de la
    # transacción (que ocurre al salir de la dependencia `get_db`, antes de que
    # exista una `Response` a la que enganchar la tarea). Si el `commit` fallara,
    # nunca se llega a construir la respuesta y esta tarea nunca se ejecuta: el
    # objeto anterior no se borra si la fila no queda actualizada. Borrarlo justo
    # tras el `flush()` (como hacía `branding/logo`) dejaría la fila apuntando a
    # un objeto ya inexistente ante cualquier fallo posterior en la misma
    # transacción — más grave aquí, porque esta portada alimenta `og:image` en
    # una página pública indexada.
    if anterior and anterior != clave:
        background_tasks.add_task(almacen.delete_object, anterior)

    return _event_response(evento)


@router.get(
    "/{event_id}/sessions",
    summary="Listar la agenda de un evento",
    response_model=list[EventSessionResponse],
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_sessions(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)], session: DbDep
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
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
) -> EventSessionResponse:
    sesion = await service.create_session(
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
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
    session_id: str,
) -> EventSessionResponse:
    sesion = await service.update_session(
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
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
    session_id: str,
) -> None:
    await service.delete_session(
        session,
        organization_id=usuario.organization_id,
        event_id=evento.id,
        session_id=uuid.UUID(session_id),
    )
