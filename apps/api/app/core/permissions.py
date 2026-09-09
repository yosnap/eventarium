"""Catálogo fijo de permisos.

Los permisos se declaran en código, nunca en base de datos: así una migración no
puede introducir un permiso que el código no conoce ni al revés. `role_permissions`
guarda únicamente valores de este enum.

Prefijos reservados para fases posteriores del PRD (no usar todavía):
`accounting:*`, `emails:*`.

`AUDIT_READ` no vive aquí a propósito (fase 5 del PRD, decisión #7 del plan):
`OWNER` se define como `permissions=tuple(Permission)` en
`app/modules/roles/system_roles.py`, así que cualquier permiso de este enum
se concede automáticamente a todo `owner` futuro. Un permiso pensado para ser
exclusivo de superadmin no puede vivir en un enum que `OWNER` hereda entero
— el endpoint de auditoría comprueba la dependencia `Superadmin` de
`app/core/deps.py` directamente, no un `Permission`.
"""

from __future__ import annotations

from enum import StrEnum


class Permission(StrEnum):
    """Permisos disponibles en la fase 0."""

    ORGANIZATIONS_READ = "organizations:read"
    ORGANIZATIONS_WRITE = "organizations:write"
    BRANDING_WRITE = "branding:write"
    ROLES_READ = "roles:read"
    ROLES_WRITE = "roles:write"
    MEMBERS_READ = "members:read"
    MEMBERS_WRITE = "members:write"
    USERS_READ = "users:read"
    EVENTS_READ = "events:read"
    EVENTS_WRITE = "events:write"
    REGISTRATIONS_READ = "registrations:read"
    REGISTRATIONS_WRITE = "registrations:write"
    TICKETS_READ = "tickets:read"
    TICKETS_WRITE = "tickets:write"
    SPONSORS_READ = "sponsors:read"
    SPONSORS_WRITE = "sponsors:write"
    PAYMENTS_READ = "payments:read"
    PAYMENTS_WRITE = "payments:write"


ALL_PERMISSIONS: frozenset[Permission] = frozenset(Permission)


def parse_permission(valor: str) -> Permission:
    """Convierte una cadena en `Permission` o lanza `ValueError`."""
    try:
        return Permission(valor)
    except ValueError as exc:  # pragma: no cover - mensaje explícito
        raise ValueError(f"Permiso desconocido: {valor}") from exc
