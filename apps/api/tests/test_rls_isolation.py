"""Aislamiento entre organizaciones garantizado por Row-Level Security.

Estos tests son la prueba de que el multi-tenant es real: se salta el filtro por
organización a propósito (`unsafe_select_all`) y se comprueba que la base de datos
sigue sin entregar filas ajenas. Si RLS se rompiera, aquí se vería.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.modules.organizations.models import (
    Organization,
    OrganizationBranding,
    OrganizationDomain,
    OrganizationMember,
)
from app.modules.organizations.repository import unsafe_select_all
from app.modules.roles.models import Role, RoleProfileField
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba

TABLAS_CON_ORGANIZACION = (
    OrganizationDomain,
    OrganizationBranding,
    OrganizationMember,
    Role,
    RoleProfileField,
)


async def test_app_user_no_puede_saltarse_rls() -> None:
    """Si el rol tuviera BYPASSRLS, todo lo demás de este fichero sería decorativo."""
    async with SessionApp() as session:
        bypass = await session.scalar(
            text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
        )
    assert bypass is False


@pytest.mark.parametrize("modelo", TABLAS_CON_ORGANIZACION)
async def test_una_sesion_solo_ve_las_filas_de_su_organizacion(
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
    modelo: type,
) -> None:
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            filas = await unsafe_select_all(session, modelo)

    assert filas, f"debería ver sus propias filas de {modelo.__tablename__}"
    ajenas = [f for f in filas if f.organization_id != organizacion.id]
    assert not ajenas, f"{modelo.__tablename__} filtró filas de otra organización"


async def test_organizations_solo_devuelve_la_organizacion_activa(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            filas = await unsafe_select_all(session, Organization)

    assert [f.id for f in filas] == [organizacion.id]


async def test_users_tambien_esta_protegida_por_rls(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    """`users` es global, pero solo se ve a quien comparte organización contigo."""
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id, organizacion.owner_id)
            filas = await unsafe_select_all(session, User)

    identificadores = {f.id for f in filas}
    assert organizacion.owner_id in identificadores
    assert otra_organizacion.owner_id not in identificadores


async def test_sin_contexto_no_se_ve_ninguna_fila(
    organizacion: OrganizacionDePrueba,
) -> None:
    """Fail-closed: sin contexto no hay error, hay cero filas."""
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, None)
            assert await unsafe_select_all(session, Organization) == []
            assert await unsafe_select_all(session, Role) == []
            assert await unsafe_select_all(session, User) == []


async def test_dos_sesiones_consecutivas_del_pool_no_heredan_contexto(
    organizacion: OrganizacionDePrueba,
) -> None:
    """`SET LOCAL` muere con la transacción; una conexión reutilizada empieza limpia."""
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            assert await unsafe_select_all(session, Organization)

    async with SessionApp() as session:
        async with session.begin():
            valor = await session.scalar(
                text("SELECT current_setting('app.organization_id', true)")
            )
            assert valor in (None, "")
            assert await unsafe_select_all(session, Organization) == []


async def test_no_se_puede_insertar_en_otra_organizacion(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    """`WITH CHECK` bloquea la escritura cruzada, no solo la lectura."""
    with pytest.raises(DBAPIError):
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, organizacion.id)
                session.add(
                    OrganizationDomain(
                        organization_id=otra_organizacion.id,
                        host="intruso.example",
                        is_primary=False,
                    )
                )
                await session.flush()

    # La fila no existe: la comprobación se hace con el rol de mantenimiento.
    async with SessionMaintenance() as session:
        encontrada = await session.scalar(
            text("SELECT count(*) FROM organization_domains WHERE host = 'intruso.example'")
        )
    assert encontrada == 0


async def test_no_se_puede_actualizar_una_fila_ajena(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    """Un UPDATE sin coincidencia de política no lanza error: afecta a cero filas."""
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            resultado = await session.execute(
                text("UPDATE organizations SET name = 'secuestrada' WHERE id = :id"),
                {"id": otra_organizacion.id},
            )
            assert resultado.rowcount == 0

    async with SessionMaintenance() as session:
        nombre = await session.scalar(
            text("SELECT name FROM organizations WHERE id = :id"), {"id": otra_organizacion.id}
        )
    assert nombre != "secuestrada"
