"""Endpoints públicos de inscripción a eventos (fase 3 del PRD, fases 2-4 de trabajo).

Mismo patrón que `events/public_router.py`: sin autenticación, sin dominio por
organización (fase 2 del plan de organización sin dominio). La inscripción a
un evento resuelve la organización desde el propio evento
(`events.service.resolve_public_event_by_slug`); verificar, cancelar o
promover una inscripción por su token resuelve la organización desde la
propia inscripción (`app_resolve_registration_organization`, SECURITY
DEFINER), no por host — el `id` ya viene autorizado por el propio token de un
solo uso.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.core.deps import SessionDep, VerifiedUserDep, get_token_claims
from app.core.mensajes import marcar, t
from app.core.ratelimit import (
    CANCELACION_INSCRIPCION_POR_IP,
    CONFIRMACION_PROMOCION_POR_IP,
    INSCRIPCION_POR_IP,
    MIS_EVENTOS_MIOS_POR_IP,
    MIS_EVENTOS_SOLICITAR_POR_IP,
    MIS_EVENTOS_VER_POR_IP,
    PUBLICO_POR_IP,
    VERIFICACION_INSCRIPCION_POR_IP,
    VISTA_CANCELACION_POR_IP,
    limit_per_ip,
)
from app.core.security import AccessTokenClaims
from app.core.turnstile import require_turnstile
from app.modules.events.models import Event
from app.modules.events.public_deps import EVENTO_PARA_INSCRIBIR, ruta_de_evento
from app.modules.policies import service as policies_service
from app.modules.registrations import cancel_preview, mis_eventos_service, repository, service
from app.modules.registrations.calendar import calendario_de_inscripcion
from app.modules.registrations.schemas import (
    CancelPreviewResponse,
    CancelRegistrationRequest,
    CancelRegistrationResponse,
    ConfirmWaitlistPromotionRequest,
    ConfirmWaitlistPromotionResponse,
    MisEventosSolicitarRequest,
    MisEventosVerRequest,
    MyRegistrationsResponse,
    RegistrationMessageResponse,
    RegistrationQuestionPublic,
    SubmitRegistrationRequest,
    VerifyRegistrationRequest,
    VerifyRegistrationResponse,
)
from app.shared.errors import ConflictError, PermissionDeniedError

router = APIRouter(prefix="/public", tags=["público"])

_MENSAJES_POR_ESTADO = {
    "confirmed": marcar("Tu inscripción está confirmada."),
    "pending_approval": marcar(
        "Tu inscripción está pendiente de aprobación por parte del organizador."
    ),
    "pending_payment": marcar("Tu plaza está reservada; completa el pago para confirmarla."),
    "waitlisted": marcar("El aforo está completo; te hemos añadido a la lista de espera."),
}


@ruta_de_evento(
    router,
    "get",
    "/registration-questions",
    summary="Listar las preguntas personalizadas de inscripción de un evento",
    response_model=list[RegistrationQuestionPublic],
    limite=("inscripcion-preguntas", PUBLICO_POR_IP),
)
async def list_registration_questions(
    evento: Annotated[Event, Depends(EVENTO_PARA_INSCRIBIR)],
    session: SessionDep,
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


@ruta_de_evento(
    router,
    "post",
    "/registrations",
    summary="Inscribirse a un evento",
    description=(
        "Da de alta una inscripción, o reencola el correo pendiente si el email "
        "ya estaba inscrito. Responde siempre igual, para no filtrar si un "
        "correo ya está inscrito."
    ),
    response_model=RegistrationMessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    limite=("inscripcion", INSCRIPCION_POR_IP),
)
async def create_registration(
    evento: Annotated[Event, Depends(EVENTO_PARA_INSCRIBIR)],
    datos: SubmitRegistrationRequest,
    request: Request,
    session: SessionDep,
) -> RegistrationMessageResponse:
    if evento.registration_mode == "paid":
        # Un evento de pago solo admite inscripción a través del embudo de
        # compra (`POST /public/organizations/{org}/events/{slug}/checkout`), que crea la
        # inscripción y el pago en la misma transacción: este endpoint
        # gratuito nunca captura el tipo de entrada ni el código de
        # descuento, así que dejarlo colar dejaría una inscripción sin pago
        # posible (fase 6 del PRD).
        raise ConflictError("Este evento requiere completar la compra de una entrada.")
    # Antes de Turnstile: su token es de un solo uso. Si las condiciones han
    # cambiado, el formulario las recarga y reenvía con el mismo token; si ya
    # se hubiera gastado, la reaceptación moriría como «bot». No revela nada:
    # los ids vigentes son públicos. El servicio lo vuelve a comprobar.
    await policies_service.comprobar_aceptacion(session, evento, datos.accepted_policy_version_ids)
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
        accepted_policy_version_ids=datos.accepted_policy_version_ids,
    )
    return RegistrationMessageResponse(
        message=t(
            "Si los datos son correctos, en breve recibirás un correo con los siguientes pasos."
        )
    )


@router.post(
    "/registrations/verify",
    summary="Verificar el correo de una inscripción",
    description="Consume el token del enlace de verificación y evalúa el estado siguiente.",
    response_model=VerifyRegistrationResponse,
    dependencies=[limit_per_ip("verificar-inscripcion", VERIFICACION_INSCRIPCION_POR_IP)],
)
async def verify_registration(
    datos: VerifyRegistrationRequest, session: SessionDep
) -> VerifyRegistrationResponse:
    inscripcion = await service.verify_registration(session, token=datos.token)
    return VerifyRegistrationResponse(
        message=(
            t(_MENSAJES_POR_ESTADO[inscripcion.status])  # mensaje marcado
            if inscripcion.status in _MENSAJES_POR_ESTADO
            else t("Inscripción verificada.")
        ),
        status=inscripcion.status,
        event=await calendario_de_inscripcion(session, inscripcion),
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
    datos: ConfirmWaitlistPromotionRequest, session: SessionDep
) -> ConfirmWaitlistPromotionResponse:
    inscripcion = await service.confirm_waitlist_promotion(session, token=datos.token)
    return ConfirmWaitlistPromotionResponse(
        message=t("Tu plaza está confirmada."),
        event=await calendario_de_inscripcion(session, inscripcion),
    )


@router.post(
    "/registrations/cancel/preview",
    summary="Ver qué se cancelaría con un enlace de autocancelación",
    description=(
        "No consume el token: devuelve el evento, si ya ha empezado y si se devolvería "
        "el pago, para que la persona confirme antes de cancelar."
    ),
    response_model=CancelPreviewResponse,
    dependencies=[limit_per_ip("vista-cancelacion", VISTA_CANCELACION_POR_IP)],
)
async def preview_cancel_registration(
    datos: CancelRegistrationRequest, session: SessionDep
) -> CancelPreviewResponse:
    return await cancel_preview.vista_previa_de_cancelacion(session, token=datos.token)


@router.post(
    "/registrations/cancel",
    summary="Cancelar una inscripción por autocancelación",
    description=(
        "Consume el token del enlace de cancelación (un solo uso). Si liberaba una "
        "plaza confirmada, promueve automáticamente a la lista de espera. Una vez "
        "empezado el evento responde 409 sin gastar el enlace."
    ),
    response_model=CancelRegistrationResponse,
    dependencies=[limit_per_ip("cancelar-inscripcion", CANCELACION_INSCRIPCION_POR_IP)],
)
async def cancel_registration(
    datos: CancelRegistrationRequest, session: SessionDep
) -> CancelRegistrationResponse:
    await service.cancel_registration_by_token(session, token=datos.token)
    return CancelRegistrationResponse(message=t("Tu inscripción ha sido cancelada."))


@router.post(
    "/mis-eventos/solicitar",
    summary="Pedir el enlace de «Mis eventos»",
    description=(
        "Encola el magic-link solo si el email tiene alguna inscripción. "
        "Responde siempre igual, para no filtrar si un correo tiene inscripciones."
    ),
    response_model=RegistrationMessageResponse,
    dependencies=[limit_per_ip("mis-eventos-solicitar", MIS_EVENTOS_SOLICITAR_POR_IP)],
)
async def solicitar_mis_eventos(
    datos: MisEventosSolicitarRequest, request: Request, session: SessionDep
) -> RegistrationMessageResponse:
    await require_turnstile(request, datos.turnstile_token)
    await mis_eventos_service.request_mis_eventos_access(session, email=str(datos.email))
    return RegistrationMessageResponse(
        message=t("Si ese correo tiene inscripciones, en breve recibirás un enlace.")
    )


@router.post(
    "/mis-eventos/ver",
    summary="Listar las inscripciones de «Mis eventos»",
    description=(
        "Consume el token del magic-link (un solo uso) y devuelve las inscripciones. "
        "POST, no GET: el consumo del token es un efecto secundario, y un enlace de "
        "correo con efecto secundario en GET puede dispararlo un escáner de enlaces "
        "corporativo sin que la persona real haya hecho clic."
    ),
    response_model=MyRegistrationsResponse,
    dependencies=[limit_per_ip("mis-eventos-ver", MIS_EVENTOS_VER_POR_IP)],
)
async def ver_mis_eventos(
    datos: MisEventosVerRequest, session: SessionDep
) -> MyRegistrationsResponse:
    registrations = await mis_eventos_service.list_mis_eventos(session, token=datos.token)
    return MyRegistrationsResponse(registrations=registrations)


@router.get(
    "/mis-eventos/mios",
    summary="Listar «Mis eventos» con la sesión iniciada",
    description=(
        "Las inscripciones del correo de la cuenta, sin enlace mágico. Exige el "
        "correo verificado (403 si no) y no se sirve durante una suplantación: "
        "el personal de plataforma no debe ver las inscripciones personales de "
        "la persona suplantada."
    ),
    response_model=MyRegistrationsResponse,
    dependencies=[limit_per_ip("mis-eventos-mios", MIS_EVENTOS_MIOS_POR_IP)],
)
async def mis_eventos_de_la_cuenta(
    usuario: VerifiedUserDep,
    claims: Annotated[AccessTokenClaims, Depends(get_token_claims)],
    session: SessionDep,
) -> MyRegistrationsResponse:
    if claims.impersonated_by is not None:
        raise PermissionDeniedError("«Mis eventos» no está disponible durante una suplantación.")
    registrations = await mis_eventos_service.list_mis_eventos_de_cuenta(
        session, email_verificado=usuario.email
    )
    return MyRegistrationsResponse(registrations=registrations)
