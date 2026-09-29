"""Datos del evento para «añadir a mi calendario».

Solo se ofrecen cuando la plaza está **confirmada**: proponer poner en el
calendario un evento al que todavía no se tiene plaza (pendiente de aprobación,
de pago o en lista de espera) llevaría a alguien a planificar algo que puede no
ocurrir. Por eso el helper devuelve `None` en cualquier otro estado y las
respuestas públicas lo exponen como campo opcional.

Módulo aparte, sin importar `service`: lo usan `registrations` y `tickets`, y
`registrations.service` ya importa `tickets.service` — un helper dentro de
cualquiera de los dos serviría a un ciclo de importación.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.events.models import Event
from app.modules.registrations.models import EventRegistration
from app.modules.registrations.schemas import EventCalendarInfo


def _ubicacion(evento: Event) -> str | None:
    """Texto de lugar para el calendario: sede y dirección; si el evento es solo
    en línea, el enlace de conexión (que es lo que se necesita para asistir)."""
    partes = [p.strip() for p in (evento.location_name, evento.location_address) if p and p.strip()]
    if partes:
        return ", ".join(partes)
    return evento.online_url


def calendario_de_evento(evento: Event, *, estado_inscripcion: str) -> EventCalendarInfo | None:
    """Parte pura, para quien ya tiene el `Event` cargado (p. ej. la vuelta de pago).

    Un evento cancelado tampoco se ofrece: `cancelar_evento` lo marca al
    instante, pero cancela las inscripciones después, por lotes, en una tarea
    aparte — mientras tanto siguen `confirmed`.
    """
    if estado_inscripcion != "confirmed" or evento.status == "cancelled":
        return None
    return EventCalendarInfo(
        slug=evento.slug,
        title=evento.title,
        starts_at=evento.starts_at,
        ends_at=evento.ends_at,
        timezone=evento.timezone,
        location=_ubicacion(evento),
    )


async def calendario_de_inscripcion(
    session: AsyncSession, inscripcion: EventRegistration
) -> EventCalendarInfo | None:
    if inscripcion.status != "confirmed":
        return None  # sin consulta: la mayoría de llamadas no van a ofrecerlo
    evento = await session.get(Event, inscripcion.event_id)
    if evento is None:  # pragma: no cover - la FK compuesta lo hace imposible
        return None
    return calendario_de_evento(evento, estado_inscripcion=inscripcion.status)
