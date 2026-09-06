"""Esquemas del módulo de roles."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field

from app.core.permissions import Permission
from app.modules.roles.models import FIELD_TYPES

KEY_PATTERN = r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"
FieldType = Annotated[str, Field(pattern="|".join(FIELD_TYPES))]


class ProfileFieldInput(BaseModel):
    """Campo de perfil definido por la organización."""

    key: Annotated[str, Field(min_length=1, max_length=60, pattern=KEY_PATTERN)]
    label: Annotated[str, Field(min_length=1, max_length=160)]
    field_type: FieldType = "text"
    options: dict[str, Any] | None = None
    is_required: bool = False
    sort_order: int = 0


class ProfileFieldResponse(ProfileFieldInput):
    """Campo de perfil tal y como se devuelve."""

    id: str
    is_locked: bool


class RoleResponse(BaseModel):
    """Rol con sus permisos y campos."""

    id: str
    key: str
    name: str
    description: str | None = None
    is_system: bool
    system_template_key: str | None = None
    permissions: list[Permission]
    profile_fields: list[ProfileFieldResponse]


class RoleCreate(BaseModel):
    """Alta de rol.

    Con `from_template` se clona una plantilla del sistema; en otro caso se crea uno
    a medida (por ejemplo «presentador» o «cantante»).
    """

    key: Annotated[str, Field(min_length=2, max_length=60, pattern=KEY_PATTERN)]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: str | None = None
    from_template: str | None = None
    permissions: list[Permission] = Field(default_factory=list)
    profile_fields: list[ProfileFieldInput] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    """Edición de un rol existente."""

    name: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    description: str | None = None
    permissions: list[Permission] | None = None
    profile_fields: list[ProfileFieldInput] | None = None
