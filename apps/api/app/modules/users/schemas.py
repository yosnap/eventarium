"""Esquemas del módulo de usuarios."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr

from app.core.permissions import Permission


class CurrentUserResponse(BaseModel):
    """Usuario autenticado en el contexto de la organización actual."""

    id: str
    email: EmailStr
    full_name: str
    is_superadmin: bool
    organization_id: str
    roles: list[str]
    permissions: list[Permission]
