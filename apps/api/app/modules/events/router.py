"""Endpoints de los eventos de la organización actual.

Incluye los de la agenda (`agenda_router`) y los del roster (`ponentes_router`).
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUserDep, DbDep, PermissionsDep, require_permission
from app.core.locale import normalizar_locale
from app.core.permissions import Permission
from app.core.storage import build_object_key, get_storage, public_url_versionada, validate_upload
from app.modules.events import (
    agenda_router,
    ponentes_router,
    public_router,
    repository,
    service,
)
from app.modules.events.categories import LONGITUD_MAX_ETIQUETA
from app.modules.events.models import (
    Event,
)
from app.modules.events.router_comun import obtener_evento_o_404
from app.modules.events.schemas import (
    EventCategoryOut,
    EventCreate,
    EventListItem,
    EventResponse,
    EventStatus,
    EventUpdate,
    PublicEventDetail,
)
from app.modules.media import service as media_service
from app.modules.media.models import Media
from app.modules.payments import repository as payments_repository
from app.shared.errors import ValidationDomainError
from app.shared.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/events", tags=["eventos"])


async def _event_response(session: AsyncSession, evento: Event) -> EventResponse:
    almacen = get_storage()
    if evento.cover_media_id is not None:
        media = await session.get(Media, evento.cover_media_id)
        cover_url = public_url_versionada(media.object_key, media.updated_at) if media else None
    elif evento.cover_object_key:
        cover_url = almacen.public_url(evento.cover_object_key)
    else:
        cover_url = None
    return EventResponse(
        id=str(evento.id),
        slug=evento.slug,
        source_locale=normalizar_locale(evento.source_locale),
        category=(
            EventCategoryOut(
                id=str(evento.category.id),
                slug=evento.category.slug,
                name=evento.category.name,
                display_order=evento.category.display_order,
                is_active=evento.category.is_active,
            )
            if evento.category is not None
            else None
        ),
        tags=list(evento.tags),
        title=evento.title,
        summary=evento.summary,
        description=evento.description,
        cover_url=cover_url,
        status=evento.status,  # type: ignore[arg-type]
        cancelled_at=evento.cancelled_at,
        cancellation_reason=evento.cancellation_reason,
        visibility=evento.visibility,  # type: ignore[arg-type]
        timezone=evento.timezone,
        starts_at=evento.starts_at,
        ends_at=evento.ends_at,
        location_mode=evento.location_mode,  # type: ignore[arg-type]
        location_name=evento.location_name,
        location_address=evento.location_address,
        city=evento.city,
        online_url=evento.online_url,
        capacity=evento.capacity,
        registration_mode=evento.registration_mode,  # type: ignore[arg-type]
        registration_opens_at=evento.registration_opens_at,
        email_verification_required=evento.email_verification_required,
        payment_checkout_window_minutes=evento.payment_checkout_window_minutes,
        reminder_enabled=evento.reminder_enabled,
        reminder_hours_before=evento.reminder_hours_before,
        attendance_closed_at=evento.attendance_closed_at,
        latitude=float(evento.latitude) if evento.latitude is not None else None,
        longitude=float(evento.longitude) if evento.longitude is not None else None,
        contingency_fund_percent=evento.contingency_fund_percent,
        budget_approved_at=evento.budget_approved_at,
        contingency_fund_cents=evento.contingency_fund_cents,
        accounting_currency=evento.accounting_currency,
        theme_template_id=(str(evento.theme_template_id) if evento.theme_template_id else None),
        theme_overrides=evento.theme_overrides,
    )


def _media_id_o_422(valor: str) -> uuid.UUID:
    try:
        return uuid.UUID(valor)
    except ValueError as exc:
        raise ValidationDomainError("«media_id» no es un identificador válido.") from exc


@router.get(
    "",
    summary="Listar eventos",
    response_model=Page[EventListItem],
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_events(
    usuario: CurrentUserDep,
    session: DbDep,
    paginacion: Annotated[PageParams, Depends(page_params)],
    estado: Annotated[EventStatus | None, Query(alias="status")] = None,
) -> Page[EventListItem]:
    consulta = repository.events_query(usuario.organization_id, status=estado)
    total = len((await session.execute(consulta)).all())
    eventos = list(
        (
            await session.execute(consulta.limit(paginacion.limit).offset(paginacion.offset))
        ).scalars()
    )
    # Una sola consulta de tipos de entrada para toda la página (sin N+1).
    precios: dict[uuid.UUID, list[tuple[int, str]]] = {}
    for tipo in await payments_repository.get_ticket_types_for_events(
        session,
        usuario.organization_id,
        [evento.id for evento in eventos if evento.registration_mode == "paid"],
    ):
        if tipo.is_active:
            precios.setdefault(tipo.event_id, []).append((tipo.price_cents, tipo.currency))

    async def _item(evento: Event) -> EventListItem:
        base = await _event_response(session, evento)
        del_evento = precios.get(evento.id, [])
        mas_barato = min(del_evento, default=None)
        return EventListItem(
            **base.model_dump(),
            price_from_cents=mas_barato[0] if mas_barato else None,
            price_currency=mas_barato[1] if mas_barato else None,
            price_multiple=len({precio for precio, _ in del_evento}) > 1,
        )

    return Page[EventListItem](
        items=[await _item(evento) for evento in eventos],
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
    return await _event_response(session, evento)


@router.get(
    "/tags",
    summary="Sugerir etiquetas ya usadas",
    description=(
        "Etiquetas de los eventos de la organización que contienen `q` (primero las "
        "que empiezan por él), ordenadas por uso. Sin `q`, las más usadas. Alimenta "
        "el autocompletado del campo de etiquetas."
    ),
    response_model=list[str],
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def suggest_event_tags(
    usuario: CurrentUserDep,
    session: DbDep,
    q: Annotated[str, Query(max_length=LONGITUD_MAX_ETIQUETA)] = "",
) -> list[str]:
    texto = re.sub(r"\s+", " ", q.strip().lower())
    return await repository.sugerir_etiquetas(session, usuario.organization_id, texto)


@router.get(
    "/{event_id}",
    summary="Ver un evento",
    response_model=EventResponse,
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def get_event(
    evento: Annotated[Event, Depends(obtener_evento_o_404)], session: DbDep
) -> EventResponse:
    return await _event_response(session, evento)


@router.get(
    "/{event_id}/preview",
    summary="Vista previa de la ficha pública de un evento",
    response_model=PublicEventDetail,
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def preview_event(
    evento: Annotated[Event, Depends(obtener_evento_o_404)], session: DbDep
) -> PublicEventDetail:
    """La ficha tal y como la verá el público, en cualquier estado (también un
    borrador): para revisarla antes de publicar. Solo para el equipo."""
    return await public_router.detalle_publico(session, evento)


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
    return await _event_response(session, evento)


@router.put(
    "/{event_id}/cover",
    summary="Subir o asignar la portada del evento",
    description=(
        "Multipart (`fichero`): sube una imagen nueva, PNG/JPEG/WebP de hasta "
        "5 MB. JSON (`{media_id}`): asigna una imagen ya subida a la "
        "biblioteca de medios. JSON (`{url}`): descarga una imagen https "
        "pública (hasta 5 MB) y la guarda en la biblioteca."
    ),
    response_model=EventResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def upload_cover(
    request: Request,
    evento: Annotated[Event, Depends(obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
    permisos: PermissionsDep,
    background_tasks: BackgroundTasks,
    fichero: Annotated[UploadFile | None, File(description="Imagen de portada")] = None,
) -> EventResponse:
    anterior_media_id = evento.cover_media_id
    anterior_object_key = evento.cover_object_key
    almacen = get_storage()

    if request.headers.get("content-type", "").startswith("application/json"):
        cuerpo = await request.json()
        media_id = cuerpo.get("media_id")
        url = cuerpo.get("url")
        if media_id and url:
            raise ValidationDomainError("Indica «media_id» o «url», no los dos.")
        if media_id:
            if not isinstance(media_id, str):
                raise ValidationDomainError("«media_id» debe ser una cadena.")
            media = await media_service.obtener_visible(
                session,
                media_id=_media_id_o_422(media_id),
                organization_id=usuario.organization_id,
                kind="events",
                user_id=usuario.id,
                permisos=permisos,
            )
            evento.cover_media_id = media.id
            evento.cover_object_key = None
        elif url:
            if not isinstance(url, str):
                raise ValidationDomainError("«url» debe ser una cadena.")
            await service.set_cover_from_url(
                session,
                evento=evento,
                url=url,
                uploaded_by_user_id=usuario.id,
                permisos=permisos,
            )
        else:
            raise ValidationDomainError("Falta «media_id» o «url».")
    else:
        if fichero is None:
            raise ValidationDomainError("Falta el fichero.")
        contenido = await fichero.read()
        mime, extension = validate_upload(contenido)
        clave = build_object_key(evento.organization_id, f"events/{evento.id}/cover", extension)
        await almacen.put_object(clave, contenido, mime)
        evento.cover_media_id = None
        evento.cover_object_key = clave

    await session.flush()

    # El objeto anterior se borra en un `BackgroundTask`, que corre tras el
    # `commit` real de la transacción. El orden no lo da el `BackgroundTask` por
    # sí solo — de hecho, una dependencia con `yield` sin `scope` cierra
    # *después* de las tareas de fondo —, sino el `scope="function"` con el que
    # `core/deps.py` declara la sesión; su docstring lo explica y
    # `tests/test_core_deps.py` lo vigila. Si el `commit` fallara, su excepción
    # sustituye la respuesta y esta tarea nunca se ejecuta: el
    # objeto anterior no se borra si la fila no queda actualizada. Borrarlo justo
    # tras el `flush()` (como hacía `branding/logo`) dejaría la fila apuntando a
    # un objeto ya inexistente ante cualquier fallo posterior en la misma
    # transacción — más grave aquí, porque esta portada alimenta `og:image` en
    # una página pública indexada.
    #
    # Regla de reemplazo (biblioteca de medios, plan `260918-1944`): si la
    # portada anterior ya estaba gestionada por la biblioteca, su ciclo de
    # vida ya no es cosa de este endpoint — solo se borra el objeto legado.
    if (
        anterior_media_id is None
        and anterior_object_key
        and anterior_object_key != evento.cover_object_key
    ):
        background_tasks.add_task(almacen.delete_object, anterior_object_key)

    return await _event_response(session, evento)


@router.delete(
    "/{event_id}/cover",
    summary="Quitar la portada del evento",
    description=(
        "Deja el evento sin portada. Una imagen de la biblioteca de medios sigue "
        "en la biblioteca; solo se borra el objeto de una portada legada, que no "
        "tiene otro dueño."
    ),
    response_model=EventResponse,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def remove_cover(
    evento: Annotated[Event, Depends(obtener_evento_o_404)],
    session: DbDep,
    background_tasks: BackgroundTasks,
) -> EventResponse:
    anterior_media_id = evento.cover_media_id
    anterior_object_key = evento.cover_object_key
    evento.cover_media_id = None
    evento.cover_object_key = None
    await session.flush()

    # Mismo orden que en `upload_cover`: el objeto legado se borra tras el commit.
    if anterior_media_id is None and anterior_object_key:
        background_tasks.add_task(get_storage().delete_object, anterior_object_key)

    return await _event_response(session, evento)


router.include_router(agenda_router.router)
router.include_router(ponentes_router.router)
