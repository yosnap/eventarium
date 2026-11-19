"""Alta, edición, orden y copia de los sitios cercanos de un evento.

Todas las consultas filtran además por `organization_id`, aunque RLS ya aísla:
mismo criterio que el resto de módulos.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.events import repository as events_repository
from app.modules.events.models import Event
from app.modules.nearby.models import EventNearbyPlace
from app.shared.errors import NotFoundError, ValidationDomainError

MAXIMO_POR_EVENTO = 50


def _limpiar(datos: dict[str, Any]) -> dict[str, Any]:
    """Texto sin espacios de más; un campo opcional vacío es nulo."""
    limpios: dict[str, Any] = {}
    for clave, valor in datos.items():
        if isinstance(valor, str):
            valor = valor.strip() or None
        limpios[clave] = valor
    if limpios.get("kind") not in (None, "other"):
        limpios["custom_kind"] = None
    return limpios


async def listar(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[EventNearbyPlace]:
    filas = await session.scalars(
        select(EventNearbyPlace)
        .where(
            EventNearbyPlace.organization_id == organization_id,
            EventNearbyPlace.event_id == event_id,
        )
        .order_by(EventNearbyPlace.display_order, EventNearbyPlace.created_at)
    )
    return list(filas)


async def _contar(session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID) -> int:
    """Bloquea la fila del evento antes de contar: dos altas simultáneas no
    pueden pasar las dos del tope."""
    await session.execute(
        select(Event.id)
        .where(Event.id == event_id, Event.organization_id == organization_id)
        .with_for_update()
    )
    return int(
        await session.scalar(
            select(func.count())
            .select_from(EventNearbyPlace)
            .where(
                EventNearbyPlace.organization_id == organization_id,
                EventNearbyPlace.event_id == event_id,
            )
        )
        or 0
    )


async def _siguiente_orden(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> int:
    maximo = await session.scalar(
        select(func.max(EventNearbyPlace.display_order)).where(
            EventNearbyPlace.organization_id == organization_id,
            EventNearbyPlace.event_id == event_id,
        )
    )
    return 0 if maximo is None else int(maximo) + 1


async def crear(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    datos: dict[str, Any],
) -> EventNearbyPlace:
    if await _contar(session, organization_id, event_id) >= MAXIMO_POR_EVENTO:
        raise ValidationDomainError(
            "Un evento admite hasta {maximo} sitios cercanos.", params={"maximo": MAXIMO_POR_EVENTO}
        )
    sitio = EventNearbyPlace(
        organization_id=organization_id,
        event_id=event_id,
        display_order=await _siguiente_orden(session, organization_id, event_id),
        **_limpiar(datos),
    )
    session.add(sitio)
    await session.flush()
    return sitio


async def _obtener(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID, place_id: uuid.UUID
) -> EventNearbyPlace:
    sitio = await session.scalar(
        select(EventNearbyPlace).where(
            EventNearbyPlace.id == place_id,
            EventNearbyPlace.organization_id == organization_id,
            EventNearbyPlace.event_id == event_id,
        )
    )
    if sitio is None:
        raise NotFoundError("El sitio no existe.")
    return sitio


async def actualizar(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    place_id: uuid.UUID,
    datos: dict[str, Any],
) -> EventNearbyPlace:
    sitio = await _obtener(session, organization_id, event_id, place_id)
    cambios = _limpiar(datos)
    tipo = cambios.get("kind", sitio.kind)
    libre = cambios["custom_kind"] if "custom_kind" in cambios else sitio.custom_kind
    if tipo != "other":
        libre = None
    if (tipo == "other") != bool(libre):
        raise ValidationDomainError(
            "Indica el tipo con nombre libre solo cuando el tipo es «Otro»."
        )
    if "name" in cambios and cambios["name"] is None:
        raise ValidationDomainError("El sitio necesita un nombre.")
    for clave, valor in cambios.items():
        setattr(sitio, clave, valor)
    sitio.custom_kind = libre
    await session.flush()
    return sitio


async def borrar(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID, place_id: uuid.UUID
) -> None:
    sitio = await _obtener(session, organization_id, event_id, place_id)
    await session.delete(sitio)
    await session.flush()


async def reordenar(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID, ids: list[str]
) -> list[EventNearbyPlace]:
    sitios = await listar(session, organization_id, event_id)
    por_id = {str(sitio.id): sitio for sitio in sitios}
    if sorted(ids) != sorted(por_id):
        raise ValidationDomainError("El orden debe incluir todos los sitios del evento, una vez.")
    for indice, place_id in enumerate(ids):
        por_id[place_id].display_order = indice
    await session.flush()
    return await listar(session, organization_id, event_id)


async def copiar_de_otro_evento(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    origen_id: uuid.UUID,
) -> list[EventNearbyPlace]:
    """Añade al final copias de los sitios de otro evento de la misma organización."""
    if origen_id == event_id:
        raise ValidationDomainError("Elige otro evento: no se puede copiar del mismo.")
    if await events_repository.get_event(session, organization_id, origen_id) is None:
        raise NotFoundError("El evento de origen no existe.")
    origen = await listar(session, organization_id, origen_id)
    if await _contar(session, organization_id, event_id) + len(origen) > MAXIMO_POR_EVENTO:
        raise ValidationDomainError(
            "Un evento admite hasta {maximo} sitios cercanos.", params={"maximo": MAXIMO_POR_EVENTO}
        )
    orden = await _siguiente_orden(session, organization_id, event_id)
    for desplazamiento, sitio in enumerate(origen):
        session.add(
            EventNearbyPlace(
                organization_id=organization_id,
                event_id=event_id,
                kind=sitio.kind,
                custom_kind=sitio.custom_kind,
                name=sitio.name,
                address=sitio.address,
                phone=sitio.phone,
                website=sitio.website,
                notes=sitio.notes,
                display_order=orden + desplazamiento,
            )
        )
    await session.flush()
    return await listar(session, organization_id, event_id)
