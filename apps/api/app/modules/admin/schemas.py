"""Esquemas de superadministración: auditoría, exportación y borrado RGPD.

Fase 5 del PRD, fase 4 de trabajo.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, EmailStr, Field


class AuditLogEntry(BaseModel):
    """Una fila de `audit_log`, tal y como la ve el superadmin."""

    id: str
    actor_user_id: str | None
    organization_id: str | None
    action: str
    entity_type: str
    entity_id: str | None
    detail: dict[str, Any]
    created_at: datetime


class Reauthentication(BaseModel):
    """Mixin de reautenticación reciente (Validation Log, sesión 1, pregunta 1
    del plan): la contraseña actual del propio superadmin, repetida en el
    body de la petición — sin sesión de reautenticación aparte ni claim
    nuevo en el JWT."""

    password: Annotated[str, Field(min_length=1, max_length=200)]


class RgpdExportRequest(Reauthentication):
    """Cuerpo de `POST /admin/events/{event_id}/rgpd-export`."""


class DeleteRegistrationRequest(Reauthentication):
    """Cuerpo de `DELETE /admin/registrations/by-email`."""

    event_id: str
    email: EmailStr
