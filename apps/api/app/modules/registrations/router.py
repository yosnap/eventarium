"""Panel de organizador sobre inscripciones de un evento (fase 3 de trabajo).

Mismo patrón que `events/router.py`: la organización se resuelve de
`usuario.organization_id` (nunca de la URL), y cada escritura exige
`registrations:write`, cada lectura `registrations:read` — igual que
`events:*` en la fase 2.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentUserDep, DbDep, require_permission
from app.core.permissions import Permission
from app.modules.events import repository as events_repository
from app.modules.events.models import Event
from app.modules.registrations import repository, service
from app.modules.registrations.models import EventRegistration, EventRegistrationQuestion
from app.modules.registrations.schemas import (
    RegistrationAnswerOut,
    RegistrationConsentOut,
    RegistrationDetail,
    RegistrationListItem,
    RegistrationQuestionCreate,
    RegistrationQuestionResponse,
    RegistrationQuestionUpdate,
    RegistrationStats,
    RegistrationStatus,
)
from app.shared.errors import NotFoundError
from app.shared.pagination import Page, PageParams, page_params

router = APIRouter(prefix="/events/{event_id}", tags=["inscripciones"])


async def _obtener_evento_o_404(usuario: CurrentUserDep, session: DbDep, event_id: str) -> Event:
    evento = await events_repository.get_event(
        session, usuario.organization_id, uuid.UUID(event_id)
    )
    if evento is None:
        raise NotFoundError("El evento no existe.")
    return evento


def _registration_list_item(inscripcion: EventRegistration) -> RegistrationListItem:
    return RegistrationListItem(
        id=str(inscripcion.id),
        email=inscripcion.email,
        full_name=inscripcion.full_name,
        status=inscripcion.status,  # type: ignore[arg-type]
        created_at=inscripcion.created_at,
        verified_at=inscripcion.verified_at,
        confirmed_at=inscripcion.confirmed_at,
        waitlist_promoted_at=inscripcion.waitlist_promoted_at,
        waitlist_promotion_expires_at=inscripcion.waitlist_promotion_expires_at,
    )


def _registration_detail(
    inscripcion: EventRegistration,
    preguntas_por_id: dict[uuid.UUID, EventRegistrationQuestion],
) -> RegistrationDetail:
    respuestas = [
        RegistrationAnswerOut(
            question_id=str(respuesta.question_id),
            label=(
                preguntas_por_id[respuesta.question_id].label
                if respuesta.question_id in preguntas_por_id
                else "(pregunta eliminada)"
            ),
            value=respuesta.value,
        )
        for respuesta in inscripcion.answers
    ]
    consentimiento = (
        RegistrationConsentOut(
            data_processing_accepted_at=inscripcion.consent.data_processing_accepted_at,
            marketing_accepted_at=inscripcion.consent.marketing_accepted_at,
            recording_accepted_at=inscripcion.consent.recording_accepted_at,
        )
        if inscripcion.consent is not None
        else None
    )
    return RegistrationDetail(
        **_registration_list_item(inscripcion).model_dump(),
        approved_at=inscripcion.approved_at,
        rejected_at=inscripcion.rejected_at,
        cancelled_at=inscripcion.cancelled_at,
        answers=respuestas,
        consent=consentimiento,
    )


def _question_response(pregunta: EventRegistrationQuestion) -> RegistrationQuestionResponse:
    return RegistrationQuestionResponse(
        id=str(pregunta.id),
        type=pregunta.type,  # type: ignore[arg-type]
        label=pregunta.label,
        required=pregunta.required,
        sort_order=pregunta.sort_order,
        options=pregunta.options,
    )


async def _obtener_inscripcion_o_404(
    evento: Event, session: DbDep, registration_id: str
) -> EventRegistration:
    inscripcion = await repository.get_registration(
        session, evento.organization_id, evento.id, uuid.UUID(registration_id)
    )
    if inscripcion is None:
        raise NotFoundError("La inscripción no existe.")
    return inscripcion


@router.get(
    "/registrations",
    summary="Listar las inscripciones de un evento",
    response_model=Page[RegistrationListItem],
    dependencies=[require_permission(Permission.REGISTRATIONS_READ)],
)
async def list_registrations(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    paginacion: Annotated[PageParams, Depends(page_params)],
    estado: Annotated[RegistrationStatus | None, Query(alias="status")] = None,
) -> Page[RegistrationListItem]:
    consulta = repository.registrations_query(evento.organization_id, evento.id, status=estado)
    total = len((await session.execute(consulta)).all())
    filas = (
        await session.execute(consulta.limit(paginacion.limit).offset(paginacion.offset))
    ).scalars()
    return Page[RegistrationListItem](
        items=[_registration_list_item(inscripcion) for inscripcion in filas],
        total=total,
        limit=paginacion.limit,
        offset=paginacion.offset,
    )


@router.get(
    "/registrations/stats",
    summary="Estadísticas de conversión del embudo de inscripción",
    response_model=RegistrationStats,
    dependencies=[require_permission(Permission.REGISTRATIONS_READ)],
)
async def get_registration_stats(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)], session: DbDep
) -> RegistrationStats:
    estadisticas = await service.get_registration_stats(
        session, organization_id=evento.organization_id, event_id=evento.id
    )
    return RegistrationStats(**estadisticas)


@router.get(
    "/registrations/{registration_id}",
    summary="Ver el detalle de una inscripción",
    response_model=RegistrationDetail,
    dependencies=[require_permission(Permission.REGISTRATIONS_READ)],
)
async def get_registration(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    registration_id: str,
) -> RegistrationDetail:
    inscripcion = await _obtener_inscripcion_o_404(evento, session, registration_id)
    preguntas = await repository.get_questions(session, evento.organization_id, evento.id)
    return _registration_detail(inscripcion, {pregunta.id: pregunta for pregunta in preguntas})


@router.post(
    "/registrations/{registration_id}/approve",
    summary="Aprobar una inscripción pendiente de aprobación",
    response_model=RegistrationListItem,
    dependencies=[require_permission(Permission.REGISTRATIONS_WRITE)],
)
async def approve_registration(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    registration_id: str,
) -> RegistrationListItem:
    inscripcion = await service.approve_registration(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        registration_id=uuid.UUID(registration_id),
    )
    return _registration_list_item(inscripcion)


@router.post(
    "/registrations/{registration_id}/reject",
    summary="Rechazar una inscripción pendiente de aprobación",
    response_model=RegistrationListItem,
    dependencies=[require_permission(Permission.REGISTRATIONS_WRITE)],
)
async def reject_registration(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    registration_id: str,
) -> RegistrationListItem:
    inscripcion = await service.reject_registration(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        registration_id=uuid.UUID(registration_id),
    )
    return _registration_list_item(inscripcion)


@router.post(
    "/registrations/{registration_id}/cancel",
    summary="Cancelar una inscripción desde el panel de organizador",
    description=(
        "Si la inscripción cancelada estaba confirmada, promueve automáticamente "
        "a la primera persona en lista de espera."
    ),
    response_model=RegistrationListItem,
    dependencies=[require_permission(Permission.REGISTRATIONS_WRITE)],
)
async def cancel_registration(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    registration_id: str,
) -> RegistrationListItem:
    inscripcion = await service.cancel_registration(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        registration_id=uuid.UUID(registration_id),
    )
    return _registration_list_item(inscripcion)


@router.get(
    "/registration-questions",
    summary="Listar las preguntas personalizadas de inscripción de un evento",
    response_model=list[RegistrationQuestionResponse],
    dependencies=[require_permission(Permission.REGISTRATIONS_READ)],
)
async def list_registration_questions(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)], session: DbDep
) -> list[RegistrationQuestionResponse]:
    preguntas = await repository.get_questions(session, evento.organization_id, evento.id)
    return [_question_response(pregunta) for pregunta in preguntas]


@router.post(
    "/registration-questions",
    summary="Añadir una pregunta personalizada de inscripción",
    status_code=status.HTTP_201_CREATED,
    response_model=RegistrationQuestionResponse,
    dependencies=[require_permission(Permission.REGISTRATIONS_WRITE)],
)
async def create_registration_question(
    datos: RegistrationQuestionCreate,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
) -> RegistrationQuestionResponse:
    pregunta = await service.create_registration_question(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        type_=datos.type,
        label=datos.label,
        required=datos.required,
        sort_order=datos.sort_order,
        options=datos.options,
    )
    return _question_response(pregunta)


@router.patch(
    "/registration-questions/{question_id}",
    summary="Editar una pregunta personalizada de inscripción",
    description=(
        "Cambiar el tipo o las opciones falla con 409 si la pregunta ya tiene "
        "respuestas guardadas; el resto de campos se puede editar siempre."
    ),
    response_model=RegistrationQuestionResponse,
    dependencies=[require_permission(Permission.REGISTRATIONS_WRITE)],
)
async def update_registration_question(
    datos: RegistrationQuestionUpdate,
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    question_id: str,
) -> RegistrationQuestionResponse:
    pregunta = await service.update_registration_question(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        question_id=uuid.UUID(question_id),
        datos=datos.model_dump(exclude_unset=True),
    )
    return _question_response(pregunta)


@router.delete(
    "/registration-questions/{question_id}",
    summary="Quitar una pregunta personalizada de inscripción",
    description="Falla con 409 si la pregunta ya tiene respuestas guardadas.",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission(Permission.REGISTRATIONS_WRITE)],
)
async def delete_registration_question(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    session: DbDep,
    question_id: str,
) -> None:
    await service.delete_registration_question(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        question_id=uuid.UUID(question_id),
    )
