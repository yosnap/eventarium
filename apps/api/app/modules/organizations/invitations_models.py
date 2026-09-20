"""Invitaciones pendientes a la organización.

Fase 1 del plan de invitaciones (plan.md). La fila guarda **estado**, nunca el
token: el token de un solo uso vive en Redis
(`auth/verification.py`, `PROPOSITO_INVITACION`), con el `id` de esta fila
como payload. Quien lea esta tabla no puede entrar con lo que hay en ella.

`estado` solo guarda lo que no se puede derivar (`pendiente`, `aceptada`,
`revocada`): «caducada» se calcula al leer comparando `expires_at`, no se
escribe — dos fuentes de verdad para el mismo hecho es el error que evita
`invitations_service.estado_efectivo`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.shared.identifiers import new_uuid7

ESTADOS_ALMACENADOS = ("pendiente", "aceptada", "revocada")


class OrganizationInvitation(Base, TimestampMixin):
    """Invitación de una persona a un rol de la organización."""

    __tablename__ = "organization_invitations"
    __table_args__ = (
        # `event_id` es NULL para una invitación de equipo y se rellena cuando
        # nace desde un evento (fase 3): FK compuesta contra `(id,
        # organization_id)` de `events`, como `event_members`, para que no
        # pueda apuntar a un evento de otra organización.
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_organization_invitations_event_id_organization_id",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "estado IN ('pendiente', 'aceptada', 'revocada')",
            name="ck_organization_invitations_estado",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    # `ON DELETE CASCADE`: borrar un rol cancela (borra) las invitaciones
    # pendientes que apuntaban a él — un rol borrado no debería poder
    # concederse (requisito de la fase 1).
    role_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Huella (SHA-256) del token vigente en Redis, no el token: igual que
    # `users.password_hash` no es la contraseña. Sirve para que reenviar
    # (`invitations_service.resend_invitation`) pueda borrar la clave anterior
    # por su huella sin haber guardado el token en claro en ningún sitio.
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Nulos con `SET NULL`, mismo patrón que `audit_log.actor_user_id`: la fila
    # de invitación se conserva por trazabilidad aunque la persona se borre.
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
