"""Modelos de niveles de patrocinio y patrocinadores.

Fase 5 del PRD, fase 1 de trabajo. Mismo patrón que `app/modules/tickets/
models.py`: `organization_id` denormalizado y FK **compuestas** contra
`(id, organization_id)` del padre, nunca FK simples — la integridad
referencial de PostgreSQL no pasa por RLS.

`SponsorTier` es por organización (los niveles se reutilizan entre ediciones,
ej. "Oro" siempre significa lo mismo); `Sponsor` cuelga de `(event_id,
tier_id)` porque un patrocinio es por edición, no permanente (decisión #1 del
plan de la fase 5). `Sponsor.tier_id` usa `RESTRICT` (sin `ondelete`
explícito): no se puede borrar un nivel con patrocinadores activos, el
organizador debe reasignarlos antes — un `IntegrityError` de esa FK se
traduce a 409 en `sponsors/service.py`.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.shared.identifiers import new_uuid7


class SponsorTier(Base, TimestampMixin):
    """Nivel de patrocinio de una organización (ej. Oro, Plata, Bronce)."""

    __tablename__ = "sponsor_tiers"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_sponsor_tiers_organization_id_name"),
        # Obligatoria para que la FK compuesta de `Sponsor.tier_id` pueda
        # crearse (PostgreSQL exige un índice único exacto sobre las columnas
        # referenciadas; ningún otro `UNIQUE` de esta tabla las cubre).
        UniqueConstraint("id", "organization_id", name="uq_sponsor_tiers_id_organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # large | medium | small
    logo_size: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    benefits: Mapped[str | None] = mapped_column(Text, nullable=True)


class Sponsor(Base, TimestampMixin):
    """Patrocinador concreto de un evento, en un nivel de patrocinio."""

    __tablename__ = "sponsors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_sponsors_event_id_organization_id",
            ondelete="CASCADE",
        ),
        # `RESTRICT` (por defecto, sin `ondelete`): no se puede borrar un
        # nivel con patrocinadores activos.
        ForeignKeyConstraint(
            ["tier_id", "organization_id"],
            ["sponsor_tiers.id", "sponsor_tiers.organization_id"],
            name="fk_sponsors_tier_id_organization_id",
        ),
        UniqueConstraint("id", "organization_id", name="uq_sponsors_id_organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    tier_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    logo_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # monetaria | en_especie
    contribution_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Solo si `contribution_type == "monetaria"`; validado en el servicio de
    # la fase 2 de trabajo, no aquí (el modelo no impone la exclusividad).
    contribution_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # Solo si `contribution_type == "en_especie"`.
    contribution_description: Mapped[str | None] = mapped_column(Text, nullable=True)
