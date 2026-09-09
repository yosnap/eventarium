"""`PAYMENTS_READ`/`PAYMENTS_WRITE` llegan por las dos vías (fase 6 del PRD,
decisión #16): backfill a roles existentes con `organizations:write`, y la
plantilla `ORGANIZER` en `system_roles.py` para organizaciones creadas
después de la migración. Mismo patrón que `test_sponsors_permisos.py`
(fase 5).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import select, text

from app.core.database import SessionMaintenance
from app.core.permissions import Permission
from app.modules.organizations.models import Organization
from app.modules.roles.models import Role, RolePermission
from app.modules.roles.system_roles import ORGANIZER
from tests.conftest import OrganizacionDePrueba, crear_organizacion

_RUTA_MIGRACION = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0013_pagos_stripe_connect.py"
)
_spec = importlib.util.spec_from_file_location("_migracion_0013", _RUTA_MIGRACION)
assert _spec is not None and _spec.loader is not None
_migracion = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migracion)


def test_organizer_template_incluye_payments_en_codigo() -> None:
    assert Permission.PAYMENTS_READ in ORGANIZER.permissions
    assert Permission.PAYMENTS_WRITE in ORGANIZER.permissions


async def _permisos_del_rol(organizacion: OrganizacionDePrueba, role_key: str) -> set[str]:
    async with SessionMaintenance() as session:
        rol = await session.scalar(
            select(Role).where(Role.organization_id == organizacion.id, Role.key == role_key)
        )
        assert rol is not None, f"no existe el rol {role_key}"
        filas = (
            await session.execute(
                select(RolePermission.permission).where(RolePermission.role_id == rol.id)
            )
        ).scalars()
        return set(filas)


async def test_organizacion_de_fase_anterior_tiene_payments_en_el_owner(
    organizacion: OrganizacionDePrueba,
) -> None:
    """La fixture `organizacion` se crea (vía `crear_organizacion`) igual que
    cualquier organización previa a esta migración: el backfill de la propia
    migración debe haberle dado `payments:read`/`write` a su rol `owner`."""
    permisos = await _permisos_del_rol(organizacion, "owner")
    assert Permission.PAYMENTS_READ.value in permisos
    assert Permission.PAYMENTS_WRITE.value in permisos


async def test_backfill_anade_payments_a_un_rol_preexistente_sin_recrearlo() -> None:
    """Reproduce el escenario real: un rol que ya existía con
    `organizations:write` **antes** de que `payments:read`/`write` existiera.
    Inserta ese estado a mano y comprueba que las sentencias de backfill de la
    propia migración 0013 se lo dan sin tocar la fila del rol."""
    async with SessionMaintenance() as session:
        organizacion = Organization(slug="pre-payments", name="Pre Payments")
        session.add(organizacion)
        await session.flush()

        rol = Role(
            organization_id=organizacion.id,
            key="legacy_admin",
            name="Admin heredado",
            is_system=False,
        )
        session.add(rol)
        await session.flush()
        session.add(
            RolePermission(
                role_id=rol.id,
                permission=Permission.ORGANIZATIONS_WRITE.value,
                organization_id=organizacion.id,
            )
        )
        await session.commit()
        role_id = rol.id

    async with SessionMaintenance() as session:
        antes = (
            (
                await session.execute(
                    select(RolePermission.permission).where(RolePermission.role_id == role_id)
                )
            )
            .scalars()
            .all()
        )
        assert Permission.PAYMENTS_READ.value not in antes
        assert Permission.PAYMENTS_WRITE.value not in antes

        for sentencia in _migracion._BACKFILL_PAGOS:
            await session.execute(text(sentencia))
        await session.commit()

    async with SessionMaintenance() as session:
        despues = (
            (
                await session.execute(
                    select(RolePermission.permission).where(RolePermission.role_id == role_id)
                )
            )
            .scalars()
            .all()
        )
    assert Permission.PAYMENTS_READ.value in despues
    assert Permission.PAYMENTS_WRITE.value in despues


async def test_ejecutar_el_backfill_dos_veces_no_duplica_filas(
    organizacion: OrganizacionDePrueba,
) -> None:
    async with SessionMaintenance() as session:
        for sentencia in _migracion._BACKFILL_PAGOS:
            await session.execute(text(sentencia))
            await session.execute(text(sentencia))
        await session.commit()

        conteo = await session.scalar(
            text(
                "SELECT count(*) FROM role_permissions "
                "WHERE role_id = :id AND permission = 'payments:read'"
            ),
            {"id": organizacion.owner_role_id},
        )
    assert conteo == 1


async def test_organizacion_creada_despues_de_la_migracion_tiene_payments_en_el_organizer() -> None:
    """Organización creada en el propio test (tras la migración ya aplicada
    por la fixture de sesión `migraciones`): su `organizer` clonado debe
    tener `payments:read`/`write` sin ningún backfill manual, solo por la
    plantilla actualizada en `system_roles.py`."""
    nueva = await crear_organizacion(
        "nueva-tras-migracion-pagos", "nueva-tras-migracion-pagos.test"
    )
    permisos = await _permisos_del_rol(nueva, "organizer")
    assert Permission.PAYMENTS_READ.value in permisos
    assert Permission.PAYMENTS_WRITE.value in permisos
