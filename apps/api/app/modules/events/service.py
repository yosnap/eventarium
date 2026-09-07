"""Servicios de eventos y agenda.

Valida lo que el esquema Pydantic no puede: unicidad de slug en base de datos,
que una sesión caiga dentro del rango del evento, y las transiciones de estado
válidas (`archived` es terminal).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.events import repository
from app.modules.events.models import Event, EventSession
from app.shared.errors import ConflictError, NotFoundError, ValidationDomainError


async def _asegurar_slug_disponible(
    session: AsyncSession, organization_id: uuid.UUID, slug: str
) -> None:
    existente = await repository.get_event_by_slug(session, organization_id, slug)
    if existente is not None:
        raise ConflictError(f"Ya existe un evento con el identificador «{slug}».")


async def create_event(
    session: AsyncSession, *, organization_id: uuid.UUID, datos: dict[str, Any]
) -> Event:
    await _asegurar_slug_disponible(session, organization_id, datos["slug"])

    evento = Event(organization_id=organization_id, **datos)
    session.add(evento)
    try:
        await session.flush()
    except IntegrityError as exc:
        # La comprobación de arriba no cierra la carrera: dos altas con el mismo
        # slug pueden llegar a la vez. El `UNIQUE(organization_id, slug)` es la
        # única fuente de verdad ante esa carrera estrecha.
        raise ConflictError(f"Ya existe un evento con el identificador «{datos['slug']}».") from exc
    return evento


def _validar_transicion_de_estado(actual: str, nuevo: str) -> None:
    if actual == "archived" and nuevo != "archived":
        raise ValidationDomainError("Un evento archivado no puede volver a editarse.")


async def update_event(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID, datos: dict[str, Any]
) -> Event:
    evento = await repository.get_event(session, organization_id, event_id)
    if evento is None:
        raise NotFoundError("El evento no existe.")

    nuevo_slug = datos.get("slug")
    if nuevo_slug is not None and nuevo_slug != evento.slug:
        await _asegurar_slug_disponible(session, organization_id, nuevo_slug)

    nuevo_estado = datos.get("status")
    if nuevo_estado is not None and nuevo_estado != evento.status:
        _validar_transicion_de_estado(evento.status, nuevo_estado)

    inicio = datos.get("starts_at", evento.starts_at)
    fin = datos.get("ends_at", evento.ends_at)
    if fin <= inicio:
        raise ValidationDomainError("La fecha de fin debe ser posterior a la de inicio.")

    for campo, valor in datos.items():
        setattr(evento, campo, valor)

    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(f"Ya existe un evento con el identificador «{nuevo_slug}».") from exc
    return evento


def _validar_sesion_dentro_del_evento(
    evento: Event, starts_at: datetime, ends_at: datetime
) -> None:
    if starts_at < evento.starts_at or ends_at > evento.ends_at:
        raise ValidationDomainError("La sesión debe caer dentro del rango de fechas del evento.")


async def create_session(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    datos: dict[str, Any],
) -> EventSession:
    evento = await repository.get_event(session, organization_id, event_id)
    if evento is None:
        raise NotFoundError("El evento no existe.")
    _validar_sesion_dentro_del_evento(evento, datos["starts_at"], datos["ends_at"])

    sesion = EventSession(event_id=event_id, organization_id=organization_id, **datos)
    session.add(sesion)
    await session.flush()
    return sesion


async def update_session(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    session_id: uuid.UUID,
    datos: dict[str, Any],
) -> EventSession:
    evento = await repository.get_event(session, organization_id, event_id)
    if evento is None:
        raise NotFoundError("El evento no existe.")
    sesion = await repository.get_event_session(session, organization_id, event_id, session_id)
    if sesion is None:
        raise NotFoundError("La sesión no existe.")

    inicio = datos.get("starts_at", sesion.starts_at)
    fin = datos.get("ends_at", sesion.ends_at)
    if fin <= inicio:
        raise ValidationDomainError("La fecha de fin debe ser posterior a la de inicio.")
    _validar_sesion_dentro_del_evento(evento, inicio, fin)

    for campo, valor in datos.items():
        setattr(sesion, campo, valor)
    await session.flush()
    return sesion


async def delete_session(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    session_id: uuid.UUID,
) -> None:
    sesion = await repository.get_event_session(session, organization_id, event_id, session_id)
    if sesion is None:
        raise NotFoundError("La sesión no existe.")
    await session.delete(sesion)
    await session.flush()
