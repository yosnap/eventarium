"""Endpoints de superadministración y su aislamiento del resto de la API."""

from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

ADMIN = "/api/v1/admin/organizations"


async def _hacer_superadmin(email: str) -> None:
    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == email))
        assert usuario is not None
        usuario.is_superadmin = True
        await session.commit()


async def test_sin_token_devuelve_401(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await cliente.get(ADMIN, headers={"Host": organizacion.host})
    assert respuesta.status_code == 401


async def test_un_usuario_normal_devuelve_403(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """El propietario de una organización no es superadministrador de la instalación."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.get(ADMIN, headers=cabeceras)
    assert respuesta.status_code == 403


async def test_un_superadmin_crea_una_organizacion_completa(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        ADMIN,
        headers=cabeceras,
        json={"slug": "nueva", "name": "Organización Nueva", "host": "nueva.example"},
    )
    assert respuesta.status_code == 201
    nueva = respuesta.json()

    # La organización queda operativa: su host resuelve y trae branding y roles.
    branding = await cliente.get("/api/v1/tenant/branding", headers={"Host": "nueva.example"})
    assert branding.status_code == 200
    assert branding.json()["organization_slug"] == "nueva"

    dominios = await cliente.get(f"{ADMIN}/{nueva['id']}/domains", headers=cabeceras)
    assert [d["host"] for d in dominios.json()] == ["nueva.example"]


async def test_no_se_puede_repetir_el_slug_ni_el_dominio(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    repetido_slug = await cliente.post(
        ADMIN,
        headers=cabeceras,
        json={"slug": organizacion.slug, "name": "Copia", "host": "copia.example"},
    )
    assert repetido_slug.status_code == 409

    repetido_host = await cliente.post(
        ADMIN,
        headers=cabeceras,
        json={"slug": "otra-mas", "name": "Otra", "host": organizacion.host},
    )
    assert repetido_host.status_code == 409


async def test_anadir_un_dominio_a_una_organizacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        f"{ADMIN}/{organizacion.id}/domains",
        headers=cabeceras,
        json={"host": "Eventos.Example", "is_primary": False},
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["host"] == "eventos.example", "el host se normaliza"

    branding = await cliente.get("/api/v1/tenant/branding", headers={"Host": "eventos.example"})
    assert branding.json()["organization_slug"] == organizacion.slug


def test_solo_el_modulo_admin_usa_el_motor_de_mantenimiento() -> None:
    """El rol con BYPASSRLS no debe filtrarse a ningún otro módulo de la API.

    Es una comprobación estática deliberada: si alguien añade `get_maintenance_db` a
    otro router, RLS dejaría de proteger ese camino y ningún test funcional lo notaría.
    """
    modules = Path(__file__).resolve().parents[2] / "app" / "modules"
    infractores = [
        str(fichero.relative_to(modules.parent))
        for fichero in modules.rglob("*.py")
        if fichero.parent.name != "admin" and "get_maintenance_db" in fichero.read_text()
    ]
    assert not infractores, f"get_maintenance_db usado fuera de modules/admin: {infractores}"
