"""Plantillas de rol del sistema.

Viven en código, no en base de datos: al crear una organización se **clonan** como
filas propias con `organization_id`. Cambiar una plantilla afecta a las
organizaciones nuevas, nunca a las existentes, que ya pueden haberla personalizado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.permissions import Permission


@dataclass(frozen=True, slots=True)
class ProfileFieldTemplate:
    """Campo de perfil predefinido de un rol del sistema."""

    key: str
    label: str
    field_type: str = "text"
    is_required: bool = False
    options: dict[str, Any] | None = None
    sort_order: int = 0


@dataclass(frozen=True, slots=True)
class SystemRoleTemplate:
    """Rol predefinido con sus permisos y campos."""

    key: str
    name: str
    description: str
    permissions: tuple[Permission, ...] = ()
    profile_fields: tuple[ProfileFieldTemplate, ...] = field(default=())


OWNER = SystemRoleTemplate(
    key="owner",
    name="Propietario",
    description="Control total de la organización. No se puede eliminar.",
    permissions=tuple(Permission),
    profile_fields=(
        ProfileFieldTemplate(key="cargo", label="Cargo", sort_order=10),
        ProfileFieldTemplate(key="telefono", label="Teléfono", field_type="phone", sort_order=20),
    ),
)

ORGANIZER = SystemRoleTemplate(
    key="organizer",
    name="Organizador",
    description="Gestiona el evento, el equipo y el contenido público.",
    permissions=(
        Permission.ORGANIZATIONS_READ,
        Permission.ORGANIZATIONS_WRITE,
        Permission.BRANDING_WRITE,
        Permission.ROLES_READ,
        Permission.ROLES_WRITE,
        Permission.MEMBERS_READ,
        Permission.MEMBERS_WRITE,
        Permission.USERS_READ,
        Permission.EVENTS_READ,
        Permission.EVENTS_WRITE,
    ),
    profile_fields=(
        ProfileFieldTemplate(key="cargo", label="Cargo", sort_order=10),
        ProfileFieldTemplate(key="telefono", label="Teléfono", field_type="phone", sort_order=20),
    ),
)

SPEAKER = SystemRoleTemplate(
    key="speaker",
    name="Ponente",
    description="Imparte una charla o taller. Su perfil se publica en la web.",
    permissions=(Permission.ORGANIZATIONS_READ,),
    profile_fields=(
        ProfileFieldTemplate(
            key="bio", label="Biografía", field_type="textarea", is_required=True, sort_order=10
        ),
        ProfileFieldTemplate(key="titular", label="Titular profesional", sort_order=20),
        ProfileFieldTemplate(key="empresa", label="Empresa u organización", sort_order=30),
        ProfileFieldTemplate(
            key="curriculum", label="Currículum", field_type="textarea", sort_order=40
        ),
        ProfileFieldTemplate(key="web", label="Sitio web", field_type="url", sort_order=50),
        ProfileFieldTemplate(
            key="contacto", label="Correo de contacto", field_type="email", sort_order=60
        ),
    ),
)

VOLUNTEER = SystemRoleTemplate(
    key="volunteer",
    name="Voluntariado",
    description="Apoya la organización durante el evento.",
    permissions=(Permission.ORGANIZATIONS_READ,),
    profile_fields=(
        ProfileFieldTemplate(
            key="disponibilidad", label="Disponibilidad", field_type="textarea", sort_order=10
        ),
        ProfileFieldTemplate(
            key="talla_camiseta",
            label="Talla de camiseta",
            field_type="select",
            options={"choices": ["XS", "S", "M", "L", "XL", "XXL"]},
            sort_order=20,
        ),
        ProfileFieldTemplate(key="telefono", label="Teléfono", field_type="phone", sort_order=30),
    ),
)

ATTENDEE = SystemRoleTemplate(
    key="attendee",
    name="Asistente",
    description="Persona inscrita en el evento.",
    permissions=(),
    profile_fields=(
        ProfileFieldTemplate(key="empresa", label="Empresa u organización", sort_order=10),
        ProfileFieldTemplate(key="perfil", label="Perfil profesional", sort_order=20),
    ),
)

SYSTEM_ROLE_TEMPLATES: tuple[SystemRoleTemplate, ...] = (
    OWNER,
    ORGANIZER,
    SPEAKER,
    VOLUNTEER,
    ATTENDEE,
)

TEMPLATES_BY_KEY: dict[str, SystemRoleTemplate] = {t.key: t for t in SYSTEM_ROLE_TEMPLATES}

OWNER_KEY = OWNER.key
