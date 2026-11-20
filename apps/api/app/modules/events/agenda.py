"""Agenda de un evento: sesiones, roster del evento y participantes de cada sesión.

Valida que una sesión caiga dentro del rango del evento y en una de sus sedes,
y que solo participen personas del roster.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.events import repository, session_types
from app.modules.events import schemas as events_schemas
from app.modules.events.models import (
    Event,
    EventMember,
    EventSession,
    EventSessionParticipant,
    SessionType,
)
from app.modules.organizations import repository as organizations_repository
from app.shared.errors import ConflictError, NotFoundError, ValidationDomainError


def _validar_sesion_dentro_del_evento(
    evento: Event, starts_at: datetime, ends_at: datetime
) -> None:
    if starts_at < evento.starts_at or ends_at > evento.ends_at:
        raise ValidationDomainError("La sesión debe caer dentro del rango de fechas del evento.")


async def _validar_sede_del_evento(
    session: AsyncSession,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    venue_id: str,
) -> None:
    try:
        venue_uuid = uuid.UUID(venue_id)
    except ValueError as exc:
        raise ValidationDomainError("El identificador de la sede no es válido.") from exc
    sede = await repository.get_event_venue(session, organization_id, event_id, venue_uuid)
    if sede is None:
        raise ValidationDomainError("La sede indicada no pertenece a este evento.")


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
    if datos.get("venue_id") is not None:
        await _validar_sede_del_evento(session, organization_id, event_id, datos["venue_id"])

    tipo = await _tipo_pedido(session, organization_id, datos)
    sesion = EventSession(
        event_id=event_id,
        organization_id=organization_id,
        session_type_id=tipo.id,
        session_type=session_types.clave_heredada(tipo),
        **datos,
    )
    session.add(sesion)
    await _guardar_sesion(session)
    await session.refresh(sesion, ["tipo"])
    return sesion


async def _guardar_sesion(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        # El tipo se borró entre elegirlo y guardar (la FK compuesta lo impide).
        if "fk_event_sessions_session_type_id_organization_id" in str(exc.orig):
            raise ConflictError(
                "Ese tipo de sesión acaba de borrarse: elige otro y vuelve a guardar."
            ) from exc
        raise


async def _tipo_pedido(
    session: AsyncSession,
    organization_id: uuid.UUID,
    datos: dict[str, Any],
    *,
    actual: uuid.UUID | None = None,
) -> SessionType:
    """Saca de `datos` el tipo pedido (por id o por clave heredada) y lo resuelve."""
    tipo_id = datos.pop("session_type_id", None)
    clave = datos.pop("session_type", None)
    try:
        id_pedido = uuid.UUID(tipo_id) if tipo_id else None
    except ValueError as exc:
        raise ValidationDomainError("Ese tipo de sesión no es válido.") from exc
    return await session_types.resolver_para_sesion(
        session,
        organization_id,
        tipo_id=id_pedido,
        clave=clave,
        actual=actual,
    )


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
    # El rango se comprueba solo si las fechas cambian (comparando valores: el
    # formulario siempre las reenvía): una sesión que ya quedó fuera de rango
    # antes de existir esta regla se tiene que poder seguir editando.
    if inicio != sesion.starts_at or fin != sesion.ends_at:
        _validar_sesion_dentro_del_evento(evento, inicio, fin)
    if "venue_id" in datos and datos["venue_id"] is not None:
        await _validar_sede_del_evento(session, organization_id, event_id, datos["venue_id"])

    # `EventSessionUpdate` valida `video_url`/`materials` campo a campo, pero un
    # `PATCH` parcial puede tocar solo uno de los dos (p. ej. cambiar la URL sin
    # repetir la plataforma): la combinación final solo se conoce aquí, tras
    # fusionar con lo que ya tenía la sesión.
    try:
        events_schemas.validate_video_url(
            datos.get("video_platform", sesion.video_platform),
            datos.get("video_url", sesion.video_url),
        )
        events_schemas.validate_materials(datos.get("materials", sesion.materials))
    except ValueError as exc:
        # Mensajes de `validate_video_url` y `validate_materials`, ya marcados.
        raise ValidationDomainError(str(exc)) from exc  # mensaje marcado

    pide_tipo = datos.get("session_type_id") is not None or (
        datos.get("session_type") is not None and datos["session_type"] != sesion.session_type
    )
    if pide_tipo:
        tipo = await _tipo_pedido(session, organization_id, datos, actual=sesion.session_type_id)
        sesion.session_type_id = tipo.id
        sesion.session_type = session_types.clave_heredada(tipo)
    datos.pop("session_type_id", None)
    datos.pop("session_type", None)
    for campo, valor in datos.items():
        setattr(sesion, campo, valor)
    await _guardar_sesion(session)
    await session.refresh(sesion, ["tipo"])
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
            "No se puede quitar del roster: tiene {activas} participación(es) activa(s) "
            "en la agenda del evento.",
            params={"activas": activas},
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

    # Una pausa (descanso, comida…) no lleva ponentes; vaciar su lista sí se permite.
    if entries and sesion.session_type_id is not None:
        tipo = await session.get(SessionType, sesion.session_type_id)
        if tipo is not None and tipo.is_break:
            raise ValidationDomainError("Una pausa no lleva ponentes.")

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
