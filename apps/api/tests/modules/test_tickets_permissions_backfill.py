"""Backfill de `tickets:read`/`tickets:write` de la migración `0011`.

Mismo patrón que `test_registrations_permissions_backfill.py` de la fase 3:
se recrea el escenario "antes del backfill" a mano y se ejecuta la sentencia
SQL del backfill directamente, igual que hace la migración.
"""

from __future__ import annotations

from sqlalchemy import text

from app.core.database import SessionMaintenance
from app.core.permissions import Permission
from tests.conftest import OrganizacionDePrueba, crear_rol

_BACKFILL_TICKETS_READ = """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'tickets:read', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'tickets:read'
)
"""

_BACKFILL_TICKETS_WRITE = """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'tickets:write', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'tickets:write'
)
"""

_BACKFILL_TICKETS_WRITE_VOLUNTEER = """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'tickets:write', r.organization_id
FROM roles r
WHERE r.key = 'volunteer'
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'tickets:write'
)
"""


async def _ejecutar_backfill() -> None:
    async with SessionMaintenance() as session:
        await session.execute(text(_BACKFILL_TICKETS_READ))
        await session.execute(text(_BACKFILL_TICKETS_WRITE))
        await session.execute(text(_BACKFILL_TICKETS_WRITE_VOLUNTEER))
        await session.commit()


async def _permisos_del_rol(role_id) -> set[str]:  # type: ignore[no-untyped-def]
    async with SessionMaintenance() as session:
        filas = await session.execute(
            text("SELECT permission FROM role_permissions WHERE role_id = :id"), {"id": role_id}
        )
        return {fila[0] for fila in filas}


async def test_un_rol_a_medida_con_organizations_write_recibe_tickets(
    organizacion: OrganizacionDePrueba,
) -> None:
    role_id = await crear_rol(organizacion, key="gestor", permisos=[Permission.ORGANIZATIONS_WRITE])

    await _ejecutar_backfill()

    permisos = await _permisos_del_rol(role_id)
    assert "tickets:read" in permisos
    assert "tickets:write" in permisos


async def test_un_rol_sin_organizations_write_ni_volunteer_no_recibe_tickets(
    organizacion: OrganizacionDePrueba,
) -> None:
    role_id = await crear_rol(
        organizacion, key="ponente_a_medida", permisos=[Permission.MEMBERS_READ]
    )

    await _ejecutar_backfill()

    permisos = await _permisos_del_rol(role_id)
    assert "tickets:read" not in permisos
    assert "tickets:write" not in permisos


async def test_el_rol_volunteer_ya_clonado_recibe_solo_tickets_write(
    organizacion: OrganizacionDePrueba,
) -> None:
    """El voluntariado solo escanea, no ve estadísticas ni gestiona preguntas
    (decisión #8 del plan de la fase 4). Se borra el permiso primero para
    simular una organización clonada antes de que `volunteer` lo llevara de
    fábrica — igual que `test_el_rol_owner_ya_clonado_recibe_tickets_via_backfill`."""
    async with SessionMaintenance() as session:
        role_id = await session.scalar(
            text("SELECT id FROM roles WHERE organization_id = :org AND key = 'volunteer'"),
            {"org": organizacion.id},
        )
        assert role_id is not None
        await session.execute(
            text(
                "DELETE FROM role_permissions WHERE role_id = :id "
                "AND permission IN ('tickets:read', 'tickets:write')"
            ),
            {"id": role_id},
        )
        await session.commit()

    await _ejecutar_backfill()

    permisos = await _permisos_del_rol(role_id)
    assert "tickets:write" in permisos
    assert "tickets:read" not in permisos


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
                "WHERE role_id = :id AND permission = 'tickets:read'"
            ),
            {"id": role_id},
        )
    assert conteo == 1


async def test_el_rol_owner_ya_clonado_recibe_tickets_via_backfill(
    organizacion: OrganizacionDePrueba,
) -> None:
    async with SessionMaintenance() as session:
        await session.execute(
            text(
                "DELETE FROM role_permissions WHERE role_id = :id "
                "AND permission IN ('tickets:read', 'tickets:write')"
            ),
            {"id": organizacion.owner_role_id},
        )
        await session.commit()

    await _ejecutar_backfill()

    permisos = await _permisos_del_rol(organizacion.owner_role_id)
    assert "tickets:read" in permisos
    assert "tickets:write" in permisos
