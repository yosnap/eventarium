"""Permiso `invitations:manage` de la fase 0 del plan de invitaciones.

Cubre las dos vías por las que un rol `organizer` debe tener el permiso —
el bug que ya ha ocurrido cuatro veces en este proyecto (`registrations`,
`sponsors`, `payments`, `accounting`): tocar solo el backfill de la
migración y dejar sin el permiso a toda organización creada después.

El backfill se ejecuta como sentencia SQL directa (mismo patrón que
`test_events_permissions_backfill.py`): no hay ningún estado intermedio real
alcanzable desde la suite, las migraciones se aplican una sola vez al
principio.
"""

from __future__ import annotations

from sqlalchemy import select, text

from app.core.database import SessionMaintenance
from app.core.permissions import Permission
from app.modules.roles.models import Role, RolePermission
from app.modules.roles.system_roles import ORGANIZER, VOLUNTEER
from tests.conftest import OrganizacionDePrueba, crear_rol

_BACKFILL_INVITACIONES = """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'invitations:manage', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'invitations:manage'
)
"""


async def _ejecutar_backfill() -> None:
    async with SessionMaintenance() as session:
        await session.execute(text(_BACKFILL_INVITACIONES))
        await session.commit()


async def _permisos_del_rol(role_id) -> set[str]:  # type: ignore[no-untyped-def]
    async with SessionMaintenance() as session:
        filas = await session.execute(
            text("SELECT permission FROM role_permissions WHERE role_id = :id"), {"id": role_id}
        )
        return {fila[0] for fila in filas}


def test_organizer_tiene_invitations_manage_en_la_plantilla() -> None:
    """La plantilla en código, no solo el backfill: cubre la organización
    creada después de esta migración."""
    assert Permission.INVITATIONS_MANAGE in ORGANIZER.permissions


def test_volunteer_no_tiene_invitations_manage_en_la_plantilla() -> None:
    """El caso «voluntario que gestiona invitaciones» se resuelve con un rol
    a medida, no relajando el rol de sistema."""
    assert Permission.INVITATIONS_MANAGE not in VOLUNTEER.permissions


async def test_organizacion_nueva_tiene_invitations_manage_en_el_rol_organizer(
    organizacion: OrganizacionDePrueba,
) -> None:
    """`crear_organizacion` clona `SYSTEM_ROLE_TEMPLATES`, que incluye
    `ORGANIZER` ya con `invitations:manage` — sin backfill manual."""
    async with SessionMaintenance() as session:
        rol = await session.scalar(
            select(Role).where(Role.organization_id == organizacion.id, Role.key == "organizer")
        )
        assert rol is not None
        permisos = set(
            (
                await session.scalars(
                    select(RolePermission.permission).where(RolePermission.role_id == rol.id)
                )
            ).all()
        )
    assert Permission.INVITATIONS_MANAGE.value in permisos


async def test_organizacion_existente_recibe_invitations_manage_via_backfill(
    organizacion: OrganizacionDePrueba,
) -> None:
    """El `owner` de una organización ya existente (creada antes de esta
    migración) recibe `invitations:manage` sin intervención manual."""
    async with SessionMaintenance() as session:
        await session.execute(
            text(
                "DELETE FROM role_permissions WHERE role_id = :id "
                "AND permission = 'invitations:manage'"
            ),
            {"id": organizacion.owner_role_id},
        )
        await session.commit()

    await _ejecutar_backfill()

    permisos = await _permisos_del_rol(organizacion.owner_role_id)
    assert "invitations:manage" in permisos


async def test_un_rol_a_medida_con_organizations_write_recibe_invitations_manage(
    organizacion: OrganizacionDePrueba,
) -> None:
    """Ancla por capacidad: no hace falta llamarse `owner` ni `organizer`."""
    role_id = await crear_rol(
        organizacion, key="gestor_invitaciones", permisos=[Permission.ORGANIZATIONS_WRITE]
    )

    await _ejecutar_backfill()

    permisos = await _permisos_del_rol(role_id)
    assert "invitations:manage" in permisos


async def test_un_rol_sin_organizations_write_no_recibe_invitations_manage(
    organizacion: OrganizacionDePrueba,
) -> None:
    role_id = await crear_rol(
        organizacion, key="voluntario_a_medida", permisos=[Permission.MEMBERS_READ]
    )

    await _ejecutar_backfill()

    permisos = await _permisos_del_rol(role_id)
    assert "invitations:manage" not in permisos


async def test_ejecutar_el_backfill_dos_veces_no_duplica_filas(
    organizacion: OrganizacionDePrueba,
) -> None:
    role_id = await crear_rol(
        organizacion, key="gestor_repetido", permisos=[Permission.ORGANIZATIONS_WRITE]
    )

    await _ejecutar_backfill()
    await _ejecutar_backfill()

    async with SessionMaintenance() as session:
        conteo = await session.scalar(
            text(
                "SELECT count(*) FROM role_permissions "
                "WHERE role_id = :id AND permission = 'invitations:manage'"
            ),
            {"id": role_id},
        )
    assert conteo == 1
