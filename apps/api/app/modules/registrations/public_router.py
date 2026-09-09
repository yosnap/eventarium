"""Endpoints públicos de inscripción a eventos (fase 3 del PRD, fases 2-4 de trabajo).

Mismo patrón que `events/public_router.py`: sin autenticación, contexto RLS
fijado por host vía `OrganizationDep`/`DbDep`. El enlace de verificación apunta
al dominio propio de la organización (`app/core/tasks.py`), así que la
petición a `/registrations/verify` llega de vuelta con el `Host` correcto y
resuelve la misma organización sin necesidad de pasarla en la URL.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.core.deps import DbDep, OrganizationDep
from app.core.ratelimit import (
    CANCELACION_INSCRIPCION_POR_IP,
    CONFIRMACION_PROMOCION_POR_IP,
    INSCRIPCION_POR_IP,
    PUBLICO_POR_IP,
    VERIFICACION_INSCRIPCION_POR_IP,
    limit_per_ip,
)
from app.core.turnstile import require_turnstile
from app.modules.events import repository as events_repository
from app.modules.events.models import Event
from app.modules.registrations import repository, service
from app.modules.registrations.schemas import (
    CancelRegistrationRequest,
    CancelRegistrationResponse,
    ConfirmWaitlistPromotionRequest,
    ConfirmWaitlistPromotionResponse,
    RegistrationMessageResponse,
    RegistrationQuestionPublic,
    SubmitRegistrationRequest,
    VerifyRegistrationRequest,
    VerifyRegistrationResponse,
)
from app.shared.errors import NotFoundError

router = APIRouter(prefix="/public", tags=["público"])

_MENSAJES_POR_ESTADO = {
    "confirmed": "Tu inscripción está confirmada.",
    "pending_approval": "Tu inscripción está pendiente de aprobación por parte del organizador.",
    "pending_payment": "Tu plaza está reservada; completa el pago para confirmarla.",
    "waitlisted": "El aforo está completo; te hemos añadido a la lista de espera.",
}


async def _obtener_evento_para_inscripcion_o_404(
    organizacion: OrganizationDep, session: DbDep, slug: str
) -> Event:
    evento = await events_repository.get_public_event_by_slug(session, organizacion.id, slug)
    if evento is None:
        raise NotFoundError("El evento no existe.")
    return evento


@router.get(
    "/events/{slug}/registration-questions",
    summary="Listar las preguntas personalizadas de inscripción de un evento",
    response_model=list[RegistrationQuestionPublic],
    dependencies=[limit_per_ip("inscripcion-preguntas", PUBLICO_POR_IP)],
)
async def list_registration_questions(
    evento: Annotated[Event, Depends(_obtener_evento_para_inscripcion_o_404)],
    session: DbDep,
) -> list[RegistrationQuestionPublic]:
    preguntas = await repository.get_questions(session, evento.organization_id, evento.id)
    return [
        RegistrationQuestionPublic(
            id=str(pregunta.id),
            type=pregunta.type,
            label=pregunta.label,
            required=pregunta.required,
            options=pregunta.options,
            sort_order=pregunta.sort_order,
        )
        for pregunta in preguntas
    ]


@router.post(
    "/events/{slug}/registrations",
    summary="Inscribirse a un evento",
    description=(
        "Da de alta una inscripción, o reencola el correo pendiente si el email "
        "ya estaba inscrito. Responde siempre igual, para no filtrar si un "
        "correo ya está inscrito."
    ),
    response_model=RegistrationMessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[limit_per_ip("inscripcion", INSCRIPCION_POR_IP)],
)
async def create_registration(
    evento: Annotated[Event, Depends(_obtener_evento_para_inscripcion_o_404)],
    datos: SubmitRegistrationRequest,
    request: Request,
    session: DbDep,
) -> RegistrationMessageResponse:
    await require_turnstile(request, datos.turnstile_token)
    await service.submit_registration(
        session,
        event=evento,
        email=str(datos.email),
        full_name=datos.full_name,
        answers=datos.answers,
        data_processing_accepted=datos.data_processing_accepted,
        marketing_accepted=datos.marketing_accepted,
        recording_accepted=datos.recording_accepted,
    )
    return RegistrationMessageResponse(
        message="Si los datos son correctos, en breve recibirás un correo con los siguientes pasos."
    )


@router.post(
    "/registrations/verify",
    summary="Verificar el correo de una inscripción",
    description="Consume el token del enlace de verificación y evalúa el estado siguiente.",
    response_model=VerifyRegistrationResponse,
    dependencies=[limit_per_ip("verificar-inscripcion", VERIFICACION_INSCRIPCION_POR_IP)],
)
async def verify_registration(
    datos: VerifyRegistrationRequest, session: DbDep
) -> VerifyRegistrationResponse:
    inscripcion = await service.verify_registration(session, token=datos.token)
    return VerifyRegistrationResponse(
        message=_MENSAJES_POR_ESTADO.get(inscripcion.status, "Inscripción verificada."),
        status=inscripcion.status,
    )


@router.post(
    "/registrations/confirm-waitlist-promotion",
    summary="Confirmar una promoción desde la lista de espera",
    description=(
        "Consume el token del enlace de promoción. Si ha caducado, responde que "
        "caducó sin más detalle y deja que el barrido cron reasigne la plaza."
    ),
    response_model=ConfirmWaitlistPromotionResponse,
    dependencies=[limit_per_ip("confirmar-promocion", CONFIRMACION_PROMOCION_POR_IP)],
)
async def confirm_waitlist_promotion(
    datos: ConfirmWaitlistPromotionRequest, session: DbDep
) -> ConfirmWaitlistPromotionResponse:
    await service.confirm_waitlist_promotion(session, token=datos.token)
    return ConfirmWaitlistPromotionResponse(message="Tu plaza está confirmada.")


@router.post(
    "/registrations/cancel",
    summary="Cancelar una inscripción por autocancelación",
    description=(
        "Consume el token del enlace de cancelación (un solo uso). Si liberaba una "
        "plaza confirmada, promueve automáticamente a la lista de espera."
    ),
    response_model=CancelRegistrationResponse,
    dependencies=[limit_per_ip("cancelar-inscripcion", CANCELACION_INSCRIPCION_POR_IP)],
)
async def cancel_registration(
    datos: CancelRegistrationRequest, session: DbDep
) -> CancelRegistrationResponse:
    await service.cancel_registration_by_token(session, token=datos.token)
    return CancelRegistrationResponse(message="Tu inscripción ha sido cancelada.")
