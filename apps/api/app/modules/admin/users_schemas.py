"""Esquemas del directorio de usuarios de plataforma.

Fase 1 de `plans/260916-0810-usuarios-y-permisos-plataforma/`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PlatformUserSummary(BaseModel):
    """Una fila del listado — nunca incluye `password_hash`."""

    id: str
    email: str
    first_name: str | None
    last_name: str | None
    is_active: bool
    platform_role: str | None
    created_at: datetime
    organization_names: str


class PlatformUserOrganization(BaseModel):
    """Una organización en la que participa el usuario, y con qué rol."""

    organization_id: str
    organization_name: str
    role_name: str


class PlatformUserDetail(BaseModel):
    """Detalle de un usuario para el directorio de plataforma."""

    id: str
    email: str
    first_name: str | None
    last_name: str | None
    is_active: bool
    platform_role: str | None
    notify_similar_events: bool
    created_at: datetime
    organizations: list[PlatformUserOrganization]
    registrations_count: int


class PlatformRoleUpdate(BaseModel):
    """Cuerpo de `PUT /admin/users/{id}/platform-role`.

    Nunca acepta `"superadmin"`: ese poder sigue siendo exclusivamente
    `is_superadmin`, fuera de este endpoint a propósito.
    """

    platform_role: Literal["soporte"] | None


class PlatformUserActionResult(BaseModel):
    """Confirmación de `deactivate`/`platform-role` — sin `organization_names`
    (esos dos endpoints no lo calculan; no vale la pena una consulta extra
    solo para una respuesta de confirmación)."""

    id: str
    email: str
    first_name: str | None
    last_name: str | None
    is_active: bool
    platform_role: str | None
