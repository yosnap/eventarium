"""Sedes de un evento, con su dirección geocodificada."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.events import repository
from app.modules.events.geocoding import geocodificar_para_guardar
from app.modules.events.models import (
    EventVenue,
)
from app.shared.errors import ConflictError, NotFoundError


async def _sincronizar_geocodificacion_sede(
    sede: EventVenue, *, address: str | None, direccion_anterior: str | None
) -> None:
    """Misma lógica que `_sincronizar_geocodificacion_evento`, sin el concepto de
    `location_mode`: una sede siempre es un sitio físico, así que basta con que
    tenga dirección."""
    if not address:
        sede.latitude = None
        sede.longitude = None
        sede.geocoded_at = None
        return
    if address == direccion_anterior and sede.geocoded_at is not None:
        return
    resultado = await geocodificar_para_guardar(address)
    if resultado is None:
        sede.latitude = None
        sede.longitude = None
        sede.geocoded_at = None
        return
    sede.latitude, sede.longitude, sede.geocoded_at = resultado


async def create_venue(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    datos: dict[str, Any],
) -> EventVenue:
    evento = await repository.get_event(session, organization_id, event_id)
    if evento is None:
        raise NotFoundError("El evento no existe.")

    sede = EventVenue(event_id=event_id, organization_id=organization_id, **datos)
    session.add(sede)
    await _sincronizar_geocodificacion_sede(sede, address=sede.address, direccion_anterior=None)
    await session.flush()
    return sede


async def update_venue(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    venue_id: uuid.UUID,
    datos: dict[str, Any],
) -> EventVenue:
    evento = await repository.get_event(session, organization_id, event_id)
    if evento is None:
        raise NotFoundError("El evento no existe.")
    sede = await repository.get_event_venue(session, organization_id, event_id, venue_id)
    if sede is None:
        raise NotFoundError("La sede no existe.")

    direccion_anterior = sede.address
    for campo, valor in datos.items():
        setattr(sede, campo, valor)

    await _sincronizar_geocodificacion_sede(
        sede, address=sede.address, direccion_anterior=direccion_anterior
    )
    await session.flush()
    return sede


async def delete_venue(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    venue_id: uuid.UUID,
) -> None:
    evento = await repository.get_event(session, organization_id, event_id)
    if evento is None:
        raise NotFoundError("El evento no existe.")
    sede = await repository.get_event_venue(session, organization_id, event_id, venue_id)
    if sede is None:
        raise NotFoundError("La sede no existe.")

    en_uso = await repository.count_sessions_using_venue(session, organization_id, sede.id)
    if en_uso > 0:
        raise ConflictError(
            "No se puede borrar la sede: {en_uso} sesión(es) de la agenda la tienen asignada.",
            params={"en_uso": en_uso},
        )

    await session.delete(sede)
    await session.flush()
