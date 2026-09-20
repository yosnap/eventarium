"""Modelos de entradas QR y sus escaneos.

Fase 4 del PRD, fase 1 de trabajo. Mismo patrón que
`app/modules/registrations/models.py`: `organization_id` denormalizado y FK
**compuestas** contra `(id, organization_id)` del padre, nunca FK simples —
la integridad referencial de PostgreSQL no pasa por RLS.

`event_tickets` es 1:1 con `event_registrations` (decisión #2 del plan de la
fase 4): se emite automáticamente al confirmarse una inscripción, nunca bajo
demanda. `event_ticket_scans` registra cada intento de escaneo, no solo el
último resultado (decisión #5) — es la fuente de verdad para resolver
duplicados de la sincronización offline y para la auditoría del organizador.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin
from app.modules.events.models import Event
from app.shared.identifiers import new_uuid7


class EventTicket(Base, TimestampMixin):
    """Entrada emitida para una inscripción `confirmed`."""

    __tablename__ = "event_tickets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_event_tickets_event_id_organization_id",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["registration_id", "organization_id"],
            ["event_registrations.id", "event_registrations.organization_id"],
            name="fk_event_tickets_registration_id_organization_id",
            ondelete="CASCADE",
        ),
        # Nulo si nadie la ha escaneado todavía; `SET NULL` (no `RESTRICT`)
        # porque es un dato de auditoría sobre quién marcó el uso, no una
        # referencia de la que dependa la validez de la propia entrada.
        ForeignKeyConstraint(
            ["used_by_event_member_id", "organization_id"],
            ["event_members.id", "event_members.organization_id"],
            name="fk_event_tickets_used_by_event_member_id_organization_id",
            ondelete="SET NULL",
        ),
        UniqueConstraint("registration_id", name="uq_event_tickets_registration_id"),
        UniqueConstraint("id", "organization_id", name="uq_event_tickets_id_organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    registration_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_event_member_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # `viewonly`: `event_id`/`organization_id` ya se fijan explícitamente en
    # `service.emitir_entrada`, nunca por cascada del ORM (mismo criterio que
    # el resto del esquema). Solo sirve para leer `evento.ends_at` sin una
    # consulta aparte — `lazy="selectin"` la deja cargada tanto si el ticket
    # se obtiene con `session.get` como con una consulta normal.
    event: Mapped[Event] = relationship(viewonly=True, lazy="selectin")


class EventTicketScan(Base, TimestampMixin):
    """Un intento de escaneo de una entrada (fase 2 de trabajo lo popula).

    `ticket_id` es **nulo** cuando el JWT no resuelve a ninguna entrada real
    (`result = not_found` o una firma que no verifica) — la fase 2 necesita
    dejar constancia del intento igual que de uno válido, sin tener una
    entrada real a la que enlazarlo.
    """

    __tablename__ = "event_ticket_scans"
    __table_args__ = (
        ForeignKeyConstraint(
            ["ticket_id", "organization_id"],
            ["event_tickets.id", "event_tickets.organization_id"],
            name="fk_event_ticket_scans_ticket_id_organization_id",
            ondelete="CASCADE",
        ),
        # Sin `ondelete`: RESTRICT por defecto, mismo patrón que
        # `event_session_participants.event_member_id` — el registro de quién
        # escaneó es de auditoría, no debe poder desaparecer en cascada al
        # quitar a alguien del roster del evento.
        ForeignKeyConstraint(
            ["scanned_by_event_member_id", "organization_id"],
            ["event_members.id", "event_members.organization_id"],
            name="fk_event_ticket_scans_scanned_by_event_member_id_org_id",
        ),
        UniqueConstraint("client_scan_id", name="uq_event_ticket_scans_client_scan_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    # Denormalizado (mismo criterio que el resto del esquema): permite listar
    # los escaneos de un evento sin pasar por `event_tickets` cuando
    # `ticket_id` es nulo.
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    scanned_by_event_member_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    # Generado en el dispositivo al escanear, no al sincronizar (decisión #6):
    # es la clave de idempotencia de la cola offline.
    client_scan_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    client_scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # valid | duplicate | expired | invalid_signature | revoked | not_found
    result: Mapped[str] = mapped_column(String(30), nullable=False)
    device_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
