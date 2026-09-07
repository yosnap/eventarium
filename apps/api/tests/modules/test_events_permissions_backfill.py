"""Backfill de `events:read`/`events:write` de la migración `0009`.

No se prueba con `alembic downgrade`/`upgrade` (no hay ningún estado intermedio
real alcanzable desde la suite: las migraciones se aplican una sola vez al
principio, fixture `migraciones`). En su lugar se recrea el escenario "antes del
backfill" a mano — un rol con `organizations:write` y sin `events:*` — y se
ejecuta la sentencia SQL del backfill directamente, igual que hace la migración.
"""

from __future__ import annotations

from sqlalchemy import text

from app.core.database import SessionMaintenance
from app.core.permissions import Permission
from tests.conftest import OrganizacionDePrueba, crear_rol

_BACKFILL_EVENTS_READ = """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'events:read', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'events:read'
)
"""

_BACKFILL_EVENTS_WRITE = """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'events:write', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'events:write'
)
"""


async def _ejecutar_backfill() -> None:
    async with SessionMaintenance() as session:
        await session.execute(text(_BACKFILL_EVENTS_READ))
        await session.execute(text(_BACKFILL_EVENTS_WRITE))
        await session.commit()


async def _permisos_del_rol(role_id) -> set[str]:  # type: ignore[no-untyped-def]
    async with SessionMaintenance() as session:
        filas = await session.execute(
            text("SELECT permission FROM role_permissions WHERE role_id = :id"), {"id": role_id}
        )
        return {fila[0] for fila in filas}


async def test_un_rol_a_medida_con_organizations_write_recibe_events(
    organizacion: OrganizacionDePrueba,
) -> None:
    """Ancla por capacidad: no hace falta llamarse `owner` ni `organizer`."""
    role_id = await crear_rol(
        organizacion, key="gestor", permisos=[Permission.ORGANIZATIONS_WRITE]
    )

    await _ejecutar_backfill()

    permisos = await _permisos_del_rol(role_id)
    assert "events:read" in permisos
    assert "events:write" in permisos


async def test_un_rol_sin_organizations_write_no_recibe_events(
    organizacion: OrganizacionDePrueba,
) -> None:
    role_id = await crear_rol(
        organizacion, key="voluntario_a_medida", permisos=[Permission.MEMBERS_READ]
    )

    await _ejecutar_backfill()

    permisos = await _permisos_del_rol(role_id)
    assert "events:read" not in permisos
    assert "events:write" not in permisos


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
                "WHERE role_id = :id AND permission = 'events:read'"
            ),
            {"id": role_id},
        )
    assert conteo == 1


async def test_el_rol_owner_ya_clonado_recibe_events_via_backfill(
    organizacion: OrganizacionDePrueba,
) -> None:
    """El `owner` de una organización ya existente (creada antes de esta migración)
    recibe `events:*` sin intervención manual."""
    async with SessionMaintenance() as session:
        await session.execute(
            text(
                "DELETE FROM role_permissions WHERE role_id = :id "
                "AND permission IN ('events:read', 'events:write')"
            ),
            {"id": organizacion.owner_role_id},
        )
        await session.commit()

    await _ejecutar_backfill()

    permisos = await _permisos_del_rol(organizacion.owner_role_id)
    assert "events:read" in permisos
    assert "events:write" in permisos
