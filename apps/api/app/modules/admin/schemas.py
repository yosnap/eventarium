"""Esquemas de superadministración: auditoría, exportación y borrado RGPD.

Fase 5 del PRD, fase 4 de trabajo.
"""

from __future__ import annotations

import uuid
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


class ImpersonationRequest(Reauthentication):
    """Cuerpo de `POST /admin/impersonate`.

    La contraseña se exige igual que en las operaciones RGPD, que son menos
    sensibles: suplantar da acceso a **todos** los datos de una persona.
    """

    user_id: uuid.UUID
    organization_id: uuid.UUID
    reason: Annotated[str, Field(min_length=1, max_length=200)]


class ImpersonationResponse(BaseModel):
    """Sesión de impersonación recién abierta."""

    access_token: str
    session_id: str
    impersonated_user_id: str
    organization_id: str
    expires_in: int = Field(description="Segundos de vida del token.")


class ImpersonableMember(BaseModel):
    """Miembro de una organización, para el selector de impersonación.

    Solo lo imprescindible para elegir a quién suplantar: el correo está
    enmascarado (es dato personal, y la lista la consume el panel de
    plataforma, que no necesita el correo completo para nada).
    """

    user_id: str
    nombre: str
    email_enmascarado: str
    role_key: str
    # `false` si no es suplantable (es superadmin): el panel lo deshabilita en
    # vez de ofrecer un botón que daría 403.
    suplantable: bool
