"""Servicios de eventos y agenda.

Valida lo que el esquema Pydantic no puede: unicidad de slug en base de datos,
que una sesión caiga dentro del rango del evento, y las transiciones de estado
válidas (`archived` es terminal).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.events import repository
from app.modules.events import schemas as events_schemas
from app.modules.events.geocoding import geocode_address
from app.modules.events.models import (
    Event,
    EventMember,
    EventSession,
    EventSessionParticipant,
    EventVenue,
)
from app.modules.organizations import repository as organizations_repository
from app.modules.payments import repository as payments_repository
from app.modules.payments import service as payments_service
from app.shared.errors import ConflictError, NotFoundError, ValidationDomainError


async def _asegurar_slug_disponible(
    session: AsyncSession, organization_id: uuid.UUID, slug: str
) -> None:
    existente = await repository.get_event_by_slug(session, organization_id, slug)
    if existente is not None:
        raise ConflictError(f"Ya existe un evento con el identificador «{slug}».")


async def _asegurar_venta_posible(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    status: str,
    registration_mode: str,
    event_id: uuid.UUID | None = None,
) -> None:
    """Bloquea la **venta**, no la configuración (decisión #13 del plan de
    la fase 6 del PRD): crear y editar un evento `paid` sigue permitido en
    borrador, mientras el organizador completa el KYC de Stripe, que puede
    tardar días. Lo único que exige `charges_enabled = true` es que el
    resultante sea `published` **y** `paid` a la vez.

    Invocada desde `create_event` **y** `update_event`: `create_event` no
    validaba nada de estado y aceptaba un
    evento ya `published`/`paid` de alta, así que la guarda no puede vivir
    solo en la edición.

    `event_id` solo llega desde `update_event` (`create_event` no tiene
    todavía una fila de evento sobre la que colgar tipos de entrada). Con él,
    exige al menos un tipo de entrada vigente: el formulario público decide
    si un evento «es de pago» por si
    la lista de tipos de entrada vendibles está vacía o no
    (`registration-page.ts`), así que un evento `paid` publicado sin ninguno
    la confundiría con uno gratuito.
    """
    if status != "published" or registration_mode != "paid":
        return

    settings = get_settings()
    if not settings.payments_enabled:
        raise ConflictError(
            "No se puede publicar un evento de pago: esta instalación no tiene Stripe configurado."
        )

    cuenta = await payments_repository.get_cuenta_activa(session, organization_id)
    if cuenta is None or not cuenta.charges_enabled:
        raise ConflictError(
            "No se puede publicar un evento de pago hasta conectar una cuenta de Stripe "
            "y completar su verificación."
        )

    if event_id is not None:
        ahora = datetime.now(UTC)
        tipos = await payments_repository.get_ticket_types(session, organization_id, event_id)
        if not any(payments_service.validar_tipo_vigente(tipo, ahora) for tipo in tipos):
            raise ConflictError(
                "No se puede publicar un evento de pago sin ningún tipo de entrada vigente."
            )


async def _geocodificar_direccion(address: str) -> tuple[Decimal, Decimal, datetime] | None:
    """Geocodifica `address` y empaqueta el resultado listo para persistir, o
    `None` si Nominatim no devolvió coordenadas (fallo de red, sin resultados,
    respuesta inesperada — `geocode_address` ya absorbe esos casos, aquí solo
    se traduce a los tipos de columna)."""
    resultado = await geocode_address(address)
    if resultado is None:
        return None
    latitud, longitud = resultado
    return (Decimal(str(latitud)), Decimal(str(longitud)), datetime.now(UTC))


async def _sincronizar_geocodificacion_evento(
    evento: Event, *, location_mode: str, address: str | None, direccion_anterior: str | None
) -> None:
    """Geocodifica `Event.location_address` con el mismo mecanismo que
    `EventVenue.address` (decisión #4 del encargo: un único mecanismo de
    dirección+geocodificación para ambos). Solo llama a Nominatim cuando la
    dirección cambió (o nunca se geocodificó) respecto al valor guardado — la
    comparación vive aquí, `geocode_address` es una función pura sin acceso a
    base de datos."""
    if location_mode == "online" or not address:
        evento.latitude = None
        evento.longitude = None
        evento.geocoded_at = None
        return
    if address == direccion_anterior and evento.geocoded_at is not None:
        return
    resultado = await _geocodificar_direccion(address)
    if resultado is None:
        evento.latitude = None
        evento.longitude = None
        evento.geocoded_at = None
        return
    evento.latitude, evento.longitude, evento.geocoded_at = resultado


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

    # `event_id=evento.id` tras el `flush` (no antes de crearlo, como hacía
    # esta llamada originalmente): sin él, un alta directa con
    # `status=published`/`registration_mode=paid` se saltaba la exigencia de
    # al menos un tipo de entrada vigente, porque
    # `_asegurar_venta_posible` solo la comprueba cuando recibe `event_id`. Si
    # esto falla, el `session.begin()` de `get_db` deshace también el
    # `flush` de arriba: nunca queda un evento a medio crear.
    await _asegurar_venta_posible(
        session,
        organization_id,
        status=evento.status,
        registration_mode=evento.registration_mode,
        event_id=evento.id,
    )
    await _sincronizar_geocodificacion_evento(
        evento,
        location_mode=evento.location_mode,
        address=evento.location_address,
        direccion_anterior=None,
    )
    await session.flush()
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

    # Evaluado sobre el evento **resultante**, no el actual: un `PATCH` que
    # cambia `status` y `registration_mode` a la vez debe quedar bloqueado
    # igual que si cada campo se editara por separado.
    await _asegurar_venta_posible(
        session,
        organization_id,
        status=datos.get("status", evento.status),
        registration_mode=datos.get("registration_mode", evento.registration_mode),
        event_id=evento.id,
    )

    inicio = datos.get("starts_at", evento.starts_at)
    fin = datos.get("ends_at", evento.ends_at)
    if fin <= inicio:
        raise ValidationDomainError("La fecha de fin debe ser posterior a la de inicio.")

    direccion_anterior = evento.location_address
    for campo, valor in datos.items():
        setattr(evento, campo, valor)

    await _sincronizar_geocodificacion_evento(
        evento,
        location_mode=evento.location_mode,
        address=evento.location_address,
        direccion_anterior=direccion_anterior,
    )

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
        raise ValidationDomainError(str(exc)) from exc

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
    resultado = await _geocodificar_direccion(address)
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
            f"No se puede borrar la sede: {en_uso} sesión(es) de la agenda la tienen asignada."
        )

    await session.delete(sede)
    await session.flush()
