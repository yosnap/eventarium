"""Servicios de niveles de patrocinio y patrocinadores.

`create_tier`/`delete_tier` vienen de la fase 1 de trabajo (409 al borrar un
nivel con patrocinadores activos). Esta fase añade el resto del CRUD:
actualizar/reordenar niveles, y el alta/edición/borrado de patrocinadores con
la comprobación explícita de que el nivel elegido pertenece a la misma
organización que el evento — la FK compuesta de `Sponsor.tier_id` ya lo
garantiza a nivel de base de datos (ver `models.py:76-81`), pero sin esta
comprobación previa un intento cruzado acaba en `IntegrityError` sin traducir,
es decir, un 500 en vez de un 4xx claro.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sponsors import repository
from app.modules.sponsors.models import Sponsor, SponsorTier
from app.modules.sponsors.schemas import validate_contribution
from app.shared.errors import ConflictError, NotFoundError, ValidationDomainError


async def create_tier(
    session: AsyncSession, *, organization_id: uuid.UUID, datos: dict[str, Any]
) -> SponsorTier:
    nivel = SponsorTier(organization_id=organization_id, **datos)
    session.add(nivel)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            f"Ya existe un nivel de patrocinio llamado «{datos['name']}»."
        ) from exc
    return nivel


async def update_tier(
    session: AsyncSession, *, organization_id: uuid.UUID, tier_id: uuid.UUID, datos: dict[str, Any]
) -> SponsorTier:
    nivel = await repository.get_tier(session, organization_id, tier_id)
    if nivel is None:
        raise NotFoundError("No existe ese nivel de patrocinio.")

    for campo, valor in datos.items():
        setattr(nivel, campo, valor)

    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            f"Ya existe un nivel de patrocinio llamado «{datos.get('name', nivel.name)}»."
        ) from exc
    return nivel


async def delete_tier(
    session: AsyncSession, *, organization_id: uuid.UUID, tier_id: uuid.UUID
) -> None:
    nivel = await repository.get_tier(session, organization_id, tier_id)
    if nivel is None:
        raise NotFoundError("No existe ese nivel de patrocinio.")

    await session.delete(nivel)
    try:
        await session.flush()
    except IntegrityError as exc:
        # `sponsors.tier_id` es `RESTRICT`: no se puede borrar un nivel con
        # patrocinadores activos, hay que reasignarlos primero.
        raise ConflictError(
            "Ese nivel de patrocinio tiene patrocinadores asignados; reasígnalos antes de borrarlo."
        ) from exc


async def _asegurar_tier_de_la_organizacion(
    session: AsyncSession, organization_id: uuid.UUID, tier_id: uuid.UUID
) -> None:
    nivel = await repository.get_tier(session, organization_id, tier_id)
    if nivel is None:
        raise ValidationDomainError("Ese nivel de patrocinio no existe en esta organización.")


async def create_sponsor(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    datos: dict[str, Any],
) -> Sponsor:
    await _asegurar_tier_de_la_organizacion(session, organization_id, datos["tier_id"])

    patrocinador = Sponsor(event_id=event_id, organization_id=organization_id, **datos)
    session.add(patrocinador)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("No se ha podido dar de alta el patrocinador.") from exc
    return patrocinador


async def update_sponsor(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    sponsor_id: uuid.UUID,
    datos: dict[str, Any],
) -> Sponsor:
    patrocinador = await repository.get_sponsor(session, organization_id, event_id, sponsor_id)
    if patrocinador is None:
        raise NotFoundError("Ese patrocinador no existe.")

    nuevo_tier_id = datos.get("tier_id")
    if nuevo_tier_id is not None:
        await _asegurar_tier_de_la_organizacion(session, organization_id, nuevo_tier_id)

    # `PATCH` parcial: la exclusividad importe/descripción solo se conoce tras
    # fusionar con lo que el patrocinador ya tenía guardado (mismo motivo que
    # `events/service.py:update_session` con `video_platform`/`video_url`).
    tipo_final = datos.get("contribution_type", patrocinador.contribution_type)
    importe_final = datos.get("contribution_amount", patrocinador.contribution_amount)
    descripcion_final = datos.get("contribution_description", patrocinador.contribution_description)
    try:
        validate_contribution(tipo_final, importe_final, descripcion_final)
    except ValueError as exc:
        raise ValidationDomainError(str(exc)) from exc

    for campo, valor in datos.items():
        setattr(patrocinador, campo, valor)

    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("No se han podido guardar los cambios del patrocinador.") from exc
    return patrocinador


async def delete_sponsor(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    sponsor_id: uuid.UUID,
) -> str | None:
    """Borra el patrocinador y devuelve la clave de su logo (si tenía), para que
    el router la borre del almacén en un `BackgroundTask` tras el commit —
    mismo patrón que `events/router.py:upload_cover`."""
    patrocinador = await repository.get_sponsor(session, organization_id, event_id, sponsor_id)
    if patrocinador is None:
        raise NotFoundError("Ese patrocinador no existe.")

    clave_logo = patrocinador.logo_object_key
    await session.delete(patrocinador)
    await session.flush()
    return clave_logo
