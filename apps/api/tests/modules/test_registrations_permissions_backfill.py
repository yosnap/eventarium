"""Backfill de `registrations:read`/`registrations:write` de la migración `0010`.

Mismo patrón que `test_events_permissions_backfill.py` de la fase 2 del PRD: se
recrea el escenario "antes del backfill" a mano y se ejecuta la sentencia SQL
del backfill directamente, igual que hace la migración.
"""

from __future__ import annotations

from sqlalchemy import text

from app.core.database import SessionMaintenance
from app.core.permissions import Permission
from tests.conftest import OrganizacionDePrueba, crear_rol

_BACKFILL_REGISTRATIONS_READ = """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'registrations:read', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'registrations:read'
)
"""

_BACKFILL_REGISTRATIONS_WRITE = """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'registrations:write', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'registrations:write'
)
"""


async def _ejecutar_backfill() -> None:
    async with SessionMaintenance() as session:
        await session.execute(text(_BACKFILL_REGISTRATIONS_READ))
        await session.execute(text(_BACKFILL_REGISTRATIONS_WRITE))
        await session.commit()


async def _permisos_del_rol(role_id) -> set[str]:  # type: ignore[no-untyped-def]
    async with SessionMaintenance() as session:
        filas = await session.execute(
            text("SELECT permission FROM role_permissions WHERE role_id = :id"), {"id": role_id}
        )
        return {fila[0] for fila in filas}


async def test_un_rol_a_medida_con_organizations_write_recibe_registrations(
    organizacion: OrganizacionDePrueba,
) -> None:
    role_id = await crear_rol(organizacion, key="gestor", permisos=[Permission.ORGANIZATIONS_WRITE])

    await _ejecutar_backfill()

    permisos = await _permisos_del_rol(role_id)
    assert "registrations:read" in permisos
    assert "registrations:write" in permisos


async def test_un_rol_sin_organizations_write_no_recibe_registrations(
    organizacion: OrganizacionDePrueba,
) -> None:
    role_id = await crear_rol(
        organizacion, key="voluntario_a_medida", permisos=[Permission.MEMBERS_READ]
    )

    await _ejecutar_backfill()

    permisos = await _permisos_del_rol(role_id)
    assert "registrations:read" not in permisos
    assert "registrations:write" not in permisos


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
                "WHERE role_id = :id AND permission = 'registrations:read'"
            ),
            {"id": role_id},
        )
    assert conteo == 1


async def test_el_rol_owner_ya_clonado_recibe_registrations_via_backfill(
    organizacion: OrganizacionDePrueba,
) -> None:
    async with SessionMaintenance() as session:
        await session.execute(
            text(
                "DELETE FROM role_permissions WHERE role_id = :id "
                "AND permission IN ('registrations:read', 'registrations:write')"
            ),
            {"id": organizacion.owner_role_id},
        )
        await session.commit()

    await _ejecutar_backfill()

    permisos = await _permisos_del_rol(organizacion.owner_role_id)
    assert "registrations:read" in permisos
    assert "registrations:write" in permisos
