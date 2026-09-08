"""Registro de auditoría de acciones sensibles.

Fase 5 del PRD, fase 1 de trabajo. `AuditLog` vive en `app/core` (no en un
módulo de dominio) porque no pertenece a ningún tenant en particular: es una
tabla de instalación que varios módulos (roles, organizaciones, superadmin)
instrumentan explícitamente, no un recurso de negocio con su propio CRUD.

Log de solo-inserción, sin UI de edición (decisión #4 del plan): se
instrumenta cada acción sensible desde el propio servicio que la realiza, no
es un sistema de eventos genérico ni un middleware que audite todo
automáticamente.

**Sin política RLS y sin el acceso por defecto de `app_user`.** La migración
`0012_patrocinadores_legal_y_auditoria` ejecuta `REVOKE ALL ON audit_log FROM
app_user` explícito: sin él, `ALTER DEFAULT PRIVILEGES`
(`infra/postgres/sql/roles.sql`) le concedería SELECT/INSERT/UPDATE/DELETE
automáticamente sobre esta tabla igual que sobre cualquier otra, permitiendo
que cualquier sesión de organización lea y **borre** el registro de
auditoría completo de la instalación. Solo `app_maintainer` (BYPASSRLS,
`maintenance_session`) puede escribir aquí.

Retención: indefinida, sin purga automática (Validation Log, sesión 1,
pregunta 2 del plan) — es un log de cumplimiento (RGPD, seguridad) y el
proyecto no tiene hoy ningún mecanismo de purga que valga la pena replicar
solo para esta tabla.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.identifiers import new_uuid7


class AuditLog(Base):
    """Una acción sensible registrada, con su actor y el detalle en JSON."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    # `SET NULL`, nunca `CASCADE`: conserva la fila de auditoría aunque el
    # usuario actor se borre después (p. ej. barrido de cuentas no
    # verificadas) — borrar en cascada destruiría la propia prueba de
    # auditoría.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Sin FK: es solo un filtro de consulta, nunca debe arrastrar el borrado
    # de una organización a su propio registro de auditoría.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )
    # Ej.: `role.permissions_changed`, `organization.created`,
    # `organization_domain.created`, `registration.rgpd_export`,
    # `registration.rgpd_delete`.
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


async def registrar_auditoria(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID | None,
    organization_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Único punto de escritura de `audit_log` (fase 4 de trabajo).

    La sesión que se le pase **debe** correr bajo `app_maintainer`
    (`get_maintenance_db` o `maintenance_session()`): la tabla tiene
    `REVOKE ALL ... FROM app_user`, así que una sesión de organización no
    podría insertar aquí ni aunque quisiera. Los puntos de instrumentación
    que corren bajo `app_user` (p. ej. `roles.service.update_role`) abren su
    propia `maintenance_session()` solo para esta llamada, en vez de ampliar
    los privilegios de `app_user` sobre esta tabla.
    """
    session.add(
        AuditLog(
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail or {},
        )
    )
    await session.flush()
