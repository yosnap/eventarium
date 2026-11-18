"""Guardas de los cambios de modo de inscripción y de aforo de un evento con
inscripciones.

Las invoca `events.service.update_event` con el bloqueo de aforo tomado
(`repository.lock_event_for_capacity`), así que ninguna alta, verificación o
aprobación concurrente puede colarse entre el recuento y la escritura.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mensajes import marcar, t
from app.modules.events.models import Event
from app.modules.registrations import repository
from app.modules.registrations.service import reencolar_promociones_caducadas
from app.shared.errors import ConflictError

# Estados que no sobreviven a que el evento pase a ser de pago: ninguno tiene
# un `event_payments` detrás, y la verificación, la promoción de la lista de
# espera y el reenvío del formulario lo exigirían en cuanto el evento fuera
# `paid` (`_reservar_ventana_de_pago`, cinturón de `_enviar_email_por_estado`).
_SIN_PAGO_VIVAS = ("pending_verification", "pending_approval", "waitlisted", "confirmed")

# En un evento de pago toda alta pasa por el checkout, así que estas
# inscripciones tienen una compra iniciada (`event_payments` en `pending`):
# quitar el pago las confirmaría gratis con ese cobro todavía abierto. Las ya
# `confirmed` están pagadas y siguen igual.
_CON_COMPRA_INICIADA = ("pending_payment", "pending_verification", "pending_approval", "waitlisted")

_ETIQUETAS_DE_ESTADO = {
    "pending_verification": marcar("{total} pendientes de verificar el correo"),
    "pending_approval": marcar("{total} pendientes de aprobación"),
    "pending_payment": marcar("{total} pendientes de pago"),
    "waitlisted": marcar("{total} en lista de espera"),
    "confirmed": marcar("{total} confirmadas"),
}


async def _recuento_en(
    session: AsyncSession, evento: Event, estados: tuple[str, ...]
) -> dict[str, int]:
    """Inscripciones del evento en `estados`, sin los estados a cero."""
    por_estado = await repository.count_registrations_by_status(
        session, evento.organization_id, evento.id
    )
    return {estado: total for estado, total in por_estado.items() if estado in estados and total}


def _describir(recuento: dict[str, int]) -> str:
    """Recuento legible en el idioma de la petición: cada trozo se traduce aquí,
    porque va dentro de un `{parámetro}` del mensaje y no de su plantilla."""
    return ", ".join(
        t(plantilla, total=recuento[estado])  # mensaje marcado
        for estado, plantilla in _ETIQUETAS_DE_ESTADO.items()
        if estado in recuento
    )


async def asegurar_cambio_de_modo_posible(
    session: AsyncSession, evento: Event, modo_nuevo: str
) -> None:
    """Rechaza los cambios de `registration_mode` que dejarían inscripciones
    existentes en un estado sin salida. Pasar de `approval` a `free` se
    permite: lo pendiente se puede seguir aprobando o rechazando."""
    if modo_nuevo == "paid":
        recuento = await _recuento_en(session, evento, _SIN_PAGO_VIVAS)
        if recuento:
            raise ConflictError(
                "No se puede pasar el evento a «de pago» porque ya tiene inscripciones "
                "sin pago ({recuento}). Cancela esas inscripciones o crea un "
                "evento nuevo de pago.",
                params={"recuento": _describir(recuento)},
            )
    elif evento.registration_mode == "paid":
        recuento = await _recuento_en(session, evento, _CON_COMPRA_INICIADA)
        if recuento:
            raise ConflictError(
                "No se puede quitar el pago mientras haya inscripciones con una compra "
                "iniciada ({recuento}). Espera a que se resuelvan o cancélalas.",
                params={"recuento": _describir(recuento)},
            )


async def asegurar_aforo_posible(session: AsyncSession, evento: Event, aforo_nuevo: int) -> None:
    """Rechaza un aforo menor que las plazas ya ocupadas o reservadas."""
    await reencolar_promociones_caducadas(session, evento)
    reservadas = await repository.count_reserved_registrations(
        session, evento.organization_id, evento.id
    )
    if aforo_nuevo < reservadas:
        raise ConflictError(
            "El aforo no puede ser menor que las {reservadas} plazas ya ocupadas o reservadas.",
            params={"reservadas": reservadas},
        )
