"""Acceso a datos de niveles de patrocinio y patrocinadores.

Filtra siempre por `organization_id` de forma explícita, igual que
`events/repository.py`: RLS es la red de seguridad, no el filtro principal.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.events.models import Event
from app.modules.sponsors.models import Sponsor, SponsorTier


def sponsor_tiers_query(organization_id: uuid.UUID) -> Select[tuple[SponsorTier]]:
    return (
        select(SponsorTier)
        .where(SponsorTier.organization_id == organization_id)
        .order_by(SponsorTier.display_order, SponsorTier.name)
    )


async def get_tier(
    session: AsyncSession, organization_id: uuid.UUID, tier_id: uuid.UUID
) -> SponsorTier | None:
    resultado: SponsorTier | None = await session.scalar(
        select(SponsorTier).where(
            SponsorTier.id == tier_id, SponsorTier.organization_id == organization_id
        )
    )
    return resultado


def sponsors_query(organization_id: uuid.UUID, event_id: uuid.UUID) -> Select[tuple[Sponsor]]:
    """Patrocinadores de un evento para el panel, agrupados de facto por nivel al
    unirlos con `SponsorTier` para ordenar por su `display_order`."""
    return (
        select(Sponsor)
        .join(SponsorTier, SponsorTier.id == Sponsor.tier_id)
        .where(Sponsor.organization_id == organization_id, Sponsor.event_id == event_id)
        .order_by(SponsorTier.display_order, SponsorTier.name, Sponsor.name)
    )


async def get_sponsor(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID, sponsor_id: uuid.UUID
) -> Sponsor | None:
    resultado: Sponsor | None = await session.scalar(
        select(Sponsor).where(
            Sponsor.id == sponsor_id,
            Sponsor.event_id == event_id,
            Sponsor.organization_id == organization_id,
        )
    )
    return resultado


def public_sponsor_history_query(
    organization_id: uuid.UUID, sponsor_name: str, exclude_event_id: uuid.UUID
) -> Select[tuple[Event, SponsorTier]]:
    """Otras ediciones publicadas y públicas en las que aparece un
    patrocinador con este mismo nombre (comparación insensible a mayúsculas),
    excluyendo el evento actual. Coincide por nombre porque `Sponsor` no
    tiene identidad propia entre eventos — es la única señal real
    disponible, sin inventar un enlace que el modelo no guarda."""
    return (
        select(Event, SponsorTier)
        .join(Sponsor, Sponsor.event_id == Event.id)
        .join(SponsorTier, SponsorTier.id == Sponsor.tier_id)
        .where(
            Sponsor.organization_id == organization_id,
            func.lower(Sponsor.name) == sponsor_name.lower(),
            Event.id != exclude_event_id,
            Event.status == "published",
            Event.visibility == "public",
        )
        .order_by(Event.starts_at.desc())
    )


def public_sponsors_query(
    organization_id: uuid.UUID, event_id: uuid.UUID
) -> Select[tuple[Sponsor, SponsorTier]]:
    """Patrocinadores de un evento con su nivel, para el bloque público agrupado.

    El filtro de publicación del evento (`published` + `public`) vive en el
    router público, que solo llama aquí tras resolver el evento por esa vía —
    igual que `events/repository.sessions_query` respecto a
    `get_public_event_by_slug`."""
    return (
        select(Sponsor, SponsorTier)
        .join(SponsorTier, SponsorTier.id == Sponsor.tier_id)
        .where(Sponsor.organization_id == organization_id, Sponsor.event_id == event_id)
        .order_by(SponsorTier.display_order, SponsorTier.name, Sponsor.name)
    )
