"""Reglas anti-escalada de privilegios.

Sin estas reglas, cualquiera con `roles:write` podría fabricarse un rol con todos
los permisos y asignárselo: el permiso de gestionar roles se convertiría en permiso
de administración total.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from app.core.permissions import Permission
from app.modules.roles.system_roles import OWNER_KEY
from app.shared.errors import PermissionDeniedError


def ensure_can_grant(
    permisos_actor: Iterable[Permission], permisos_solicitados: Iterable[Permission]
) -> None:
    """Nadie puede conceder un permiso que no posee."""
    actor = set(permisos_actor)
    exceso = sorted(p.value for p in set(permisos_solicitados) - actor)
    if exceso:
        raise PermissionDeniedError(
            "No puedes conceder permisos que tú no tienes.",
            extra={"permisos_no_permitidos": exceso},
        )


def ensure_can_manage_role(
    *, actor_role_keys: Iterable[str], role_key: str, es_rol_de_sistema: bool
) -> None:
    """Solo un `owner` puede crear, modificar o asignar el rol `owner`."""
    if role_key == OWNER_KEY and OWNER_KEY not in set(actor_role_keys):
        raise PermissionDeniedError("Solo un propietario puede gestionar el rol de propietario.")
    if es_rol_de_sistema and role_key == OWNER_KEY:
        # Redundante con lo anterior, pero deja explícita la intención en el código.
        return


def ensure_not_self_escalation(
    *,
    actor_id: uuid.UUID,
    target_user_id: uuid.UUID,
    permisos_nuevos: Iterable[Permission],
    permisos_actor: Iterable[Permission],
) -> None:
    """Un actor no puede ganar permisos modificando su propia membresía."""
    if actor_id != target_user_id:
        return
    nuevos = set(permisos_nuevos) - set(permisos_actor)
    if nuevos:
        raise PermissionDeniedError(
            "No puedes ampliar tus propios permisos.",
            extra={"permisos_no_permitidos": sorted(p.value for p in nuevos)},
        )
