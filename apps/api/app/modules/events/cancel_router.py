"""Endpoints del panel para cancelar un evento (ver `events/cancelacion.py`).

Cancelar mueve dinero cuando hay cobros, así que además de `events:write`
exige `payments:write` en ese caso. Se confirma en dos pasos: el panel pide el
resumen y el `POST` repite sus cifras; si han cambiado entre medias (alguien
se ha inscrito o ha pagado), se rechaza para que la persona vuelva a mirar.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

from app.core.audit import registrar_auditoria
from app.core.database import maintenance_session
from app.core.deps import CurrentUserDep, DbDep, PermissionsDep, require_permission
from app.core.permissions import Permission
from app.modules.events import cancelacion
from app.shared.errors import ConflictError, PermissionDeniedError

router = APIRouter(prefix="/events", tags=["eventos"])


class ResumenCancelacionOut(BaseModel):
    inscripciones_afectadas: int
    pagos_a_reembolsar: int
    importe_a_reembolsar_cents: int
    moneda: str | None
    # Si cancelar reembolsa algo, hace falta también `payments:write`.
    requiere_permiso_de_pagos: bool


class CancelarEventoIn(BaseModel):
    motivo: Annotated[str, Field(max_length=2000)] | None = None
    # Las cifras del resumen que la persona ha visto y confirma.
    inscripciones_afectadas: int
    importe_a_reembolsar_cents: int


class ProgresoCancelacionOut(BaseModel):
    por_cancelar: int
    por_avisar: int
    reembolsos_fallidos: int


def _resumen_out(resumen: cancelacion.ResumenCancelacion) -> ResumenCancelacionOut:
    return ResumenCancelacionOut(
        inscripciones_afectadas=resumen.inscripciones_afectadas,
        pagos_a_reembolsar=resumen.pagos_a_reembolsar,
        importe_a_reembolsar_cents=resumen.importe_a_reembolsar_cents,
        moneda=resumen.moneda,
        requiere_permiso_de_pagos=resumen.pagos_a_reembolsar > 0,
    )


async def _auditar_cancelacion(
    actor_user_id: uuid.UUID, organization_id: uuid.UUID, event_id: uuid.UUID, detalle: dict
) -> None:
    # `audit_log` solo lo escribe `app_maintainer` (`core/audit.py`).
    async with maintenance_session() as auditoria:
        await registrar_auditoria(
            auditoria,
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            action="events.cancelled",
            entity_type="event",
            entity_id=str(event_id),
            detail=detalle,
        )


async def _encolar_barrido(organization_id: uuid.UUID, event_id: uuid.UUID) -> None:
    from app.core.tasks import sweep_event_cancellation_task

    await sweep_event_cancellation_task.kiq(str(organization_id), str(event_id))


@router.get(
    "/{event_id}/cancel/preview",
    summary="Resumen de lo que implica cancelar un evento",
    response_model=ResumenCancelacionOut,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def preview_cancel_event(
    usuario: CurrentUserDep, session: DbDep, event_id: uuid.UUID
) -> ResumenCancelacionOut:
    resumen = await cancelacion.resumen_de_cancelacion(
        session, organization_id=usuario.organization_id, event_id=event_id
    )
    return _resumen_out(resumen)


@router.post(
    "/{event_id}/cancel",
    summary="Cancelar un evento publicado",
    description=(
        "Definitivo. Cancela todas las inscripciones vivas, reembolsa "
        "íntegramente lo cobrado y avisa a cada inscrito, en segundo plano. "
        "Las cifras del cuerpo deben coincidir con las del resumen."
    ),
    response_model=ProgresoCancelacionOut,
    dependencies=[require_permission(Permission.EVENTS_WRITE)],
)
async def cancel_event(
    datos: CancelarEventoIn,
    usuario: CurrentUserDep,
    session: DbDep,
    permisos: PermissionsDep,
    background_tasks: BackgroundTasks,
    event_id: uuid.UUID,
) -> ProgresoCancelacionOut:
    resumen = await cancelacion.resumen_de_cancelacion(
        session, organization_id=usuario.organization_id, event_id=event_id
    )
    if resumen.pagos_a_reembolsar > 0 and Permission.PAYMENTS_WRITE not in permisos:
        raise PermissionDeniedError(
            "Cancelar este evento reembolsa pagos: necesitas también el permiso de pagos."
        )
    if (
        resumen.inscripciones_afectadas != datos.inscripciones_afectadas
        or resumen.importe_a_reembolsar_cents != datos.importe_a_reembolsar_cents
    ):
        raise ConflictError(
            "Las inscripciones o los pagos del evento han cambiado desde el resumen. "
            "Vuelve a revisarlo antes de cancelar."
        )

    await cancelacion.cancelar_evento(
        session,
        organization_id=usuario.organization_id,
        event_id=event_id,
        motivo=datos.motivo,
    )
    # Ambas corren después del `commit` de la petición (`core/deps.py`).
    background_tasks.add_task(
        _auditar_cancelacion,
        usuario.id,
        usuario.organization_id,
        event_id,
        {
            "inscripciones_afectadas": resumen.inscripciones_afectadas,
            "pagos_a_reembolsar": resumen.pagos_a_reembolsar,
        },
    )
    background_tasks.add_task(_encolar_barrido, usuario.organization_id, event_id)
    return ProgresoCancelacionOut(
        por_cancelar=resumen.inscripciones_afectadas,
        por_avisar=resumen.inscripciones_afectadas,
        reembolsos_fallidos=0,
    )


@router.get(
    "/{event_id}/cancel/progress",
    summary="Progreso de la cancelación de un evento",
    response_model=ProgresoCancelacionOut,
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def cancel_progress(
    usuario: CurrentUserDep, session: DbDep, event_id: uuid.UUID
) -> ProgresoCancelacionOut:
    progreso = await cancelacion.progreso_de_cancelacion(
        session, organization_id=usuario.organization_id, event_id=event_id
    )
    return ProgresoCancelacionOut(**progreso)
