"""Servicios de eventos y agenda.

Valida lo que el esquema Pydantic no puede: unicidad de slug en base de datos,
que una sesión caiga dentro del rango del evento, y las transiciones de estado
válidas (`archived` es terminal).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.events import repository
from app.modules.events.models import Event, EventMember, EventSession, EventSessionParticipant
from app.modules.organizations import repository as organizations_repository
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


async def add_event_member(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    organization_member_id: uuid.UUID,
) -> EventMember:
    evento = await repository.get_event(session, organization_id, event_id)
    if evento is None:
        raise NotFoundError("El evento no existe.")

    miembro_org = await organizations_repository.get_member(
        session, organization_id, organization_member_id
    )
    if miembro_org is None:
        raise ValidationDomainError("Esa persona no pertenece a la organización.")

    existente = await repository.get_event_member_by_organization_member(
        session, organization_id, event_id, organization_member_id
    )
    if existente is not None:
        raise ConflictError("Esa persona ya está en el roster de este evento.")

    miembro = EventMember(
        event_id=event_id,
        organization_id=organization_id,
        organization_member_id=organization_member_id,
    )
    session.add(miembro)
    try:
        await session.flush()
    except IntegrityError as exc:
        # Carrera entre dos altas simultáneas de la misma persona en el mismo
        # evento: el `UNIQUE(event_id, organization_member_id)` es la única
        # fuente de verdad.
        raise ConflictError("Esa persona ya está en el roster de este evento.") from exc
    return miembro


async def remove_event_member(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    event_member_id: uuid.UUID,
) -> None:
    miembro = await repository.get_event_member(session, organization_id, event_id, event_member_id)
    if miembro is None:
        raise NotFoundError("Esa persona no está en el roster de este evento.")

    activas = await repository.count_active_participations(
        session, organization_id, event_member_id
    )
    if activas > 0:
        raise ConflictError(
            f"No se puede quitar del roster: tiene {activas} participación(es) activa(s) "
            "en la agenda del evento."
        )

    await session.delete(miembro)
    await session.flush()


async def replace_session_participants(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    session_id: uuid.UUID,
    expected_updated_at: datetime,
    entries: list[dict[str, Any]],
) -> EventSession:
    evento = await repository.get_event(session, organization_id, event_id)
    if evento is None:
        raise NotFoundError("El evento no existe.")
    sesion = await repository.get_event_session(session, organization_id, event_id, session_id)
    if sesion is None:
        raise NotFoundError("La sesión no existe.")

    if sesion.updated_at != expected_updated_at:
        raise ConflictError("La agenda cambió desde que la cargaste. Recarga antes de guardar.")

    ids_del_roster = await repository.event_member_ids(session, organization_id, event_id)
    for entrada in entries:
        if entrada["event_member_id"] not in ids_del_roster:
            raise ValidationDomainError(
                "Uno de los participantes no pertenece al roster de este evento."
            )

    await session.execute(
        delete(EventSessionParticipant).where(EventSessionParticipant.session_id == session_id)
    )
    for indice, entrada in enumerate(entries):
        session.add(
            EventSessionParticipant(
                session_id=session_id,
                event_member_id=entrada["event_member_id"],
                organization_id=organization_id,
                role_key=entrada["role_key"],
                sort_order=indice,
            )
        )

    # Bump explícito: sustituir participantes no toca ninguna columna propia de
    # `event_sessions`, así que el `onupdate` de `TimestampMixin` no se dispara solo.
    # Sin este bump, `expected_updated_at` nunca cambiaría entre dos guardados y el
    # control de concurrencia sería un teatro que siempre deja pasar la segunda escritura.
    sesion.updated_at = datetime.now(UTC)

    try:
        await session.flush()
    except IntegrityError as exc:
        # Carrera estrecha entre dos peticiones que pasaron la comprobación de
        # `expected_updated_at` casi a la vez: el `UNIQUE(session_id,
        # event_member_id, role_key)` es la última red antes del 500.
        raise ConflictError(
            "Dos guardados de la agenda han chocado. Recarga e inténtalo de nuevo."
        ) from exc
    return sesion
