"""`SPONSORS_READ`/`SPONSORS_WRITE` llegan por las dos vías del plan (fase 5
del PRD, decisión #7): backfill a roles existentes con
`organizations:write`, y la plantilla `ORGANIZER` en `system_roles.py` para
organizaciones creadas después de la migración.

También comprueba que `AUDIT_READ` no existe en el enum `Permission`: si
existiera, `OWNER` (que clona `tuple(Permission)`) lo heredaría
automáticamente, contradiciendo su exclusividad para superadmin.
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
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0012_patrocinio_legal_auditoria.py"
)
_spec = importlib.util.spec_from_file_location("_migracion_0012", _RUTA_MIGRACION)
assert _spec is not None and _spec.loader is not None
_migracion = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migracion)


def test_audit_read_no_existe_en_el_enum() -> None:
    assert "AUDIT_READ" not in Permission.__members__
    assert not any(valor.value == "audit:read" for valor in Permission)


def test_organizer_template_incluye_sponsors_en_codigo() -> None:
    assert Permission.SPONSORS_READ in ORGANIZER.permissions
    assert Permission.SPONSORS_WRITE in ORGANIZER.permissions


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


async def test_organizacion_de_fase_anterior_tiene_sponsors_en_el_owner(
    organizacion: OrganizacionDePrueba,
) -> None:
    """La fixture `organizacion` se crea (vía `crear_organizacion`) igual que
    cualquier organización previa a esta migración: el backfill de la propia
    migración debe haberle dado `sponsors:read`/`write` a su rol `owner`."""
    permisos = await _permisos_del_rol(organizacion, "owner")
    assert Permission.SPONSORS_READ.value in permisos
    assert Permission.SPONSORS_WRITE.value in permisos


async def test_backfill_anade_sponsors_a_un_rol_preexistente_sin_recrearlo() -> None:
    """Reproduce el escenario real del hallazgo #3 del red-team: un rol que ya
    existía con `organizations:write` **antes** de que `sponsors:read`/
    `write` existiera. Inserta ese estado a mano (sin pasar por el enum
    `Permission`, que ya declara `SPONSORS_*` en este checkout) y comprueba
    que las sentencias de backfill de la propia migración 0012 se lo dan sin
    tocar la fila del rol."""
    async with SessionMaintenance() as session:
        organizacion = Organization(slug="pre-sponsors", name="Pre Sponsors")
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
        assert Permission.SPONSORS_READ.value not in antes
        assert Permission.SPONSORS_WRITE.value not in antes

        for sentencia in _migracion._BACKFILL_SPONSORS:
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
    assert Permission.SPONSORS_READ.value in despues
    assert Permission.SPONSORS_WRITE.value in despues


async def test_organizacion_creada_despues_de_la_migracion_tiene_sponsors_en_el_organizer() -> None:
    """Organización creada en el propio test (tras la migración ya aplicada
    por la fixture de sesión `migraciones`): su `organizer` clonado debe
    tener `sponsors:read`/`write` sin ningún backfill manual, solo por la
    plantilla actualizada en `system_roles.py`."""
    nueva = await crear_organizacion("nueva-tras-migracion", "nueva-tras-migracion.test")
    permisos = await _permisos_del_rol(nueva, "organizer")
    assert Permission.SPONSORS_READ.value in permisos
    assert Permission.SPONSORS_WRITE.value in permisos
