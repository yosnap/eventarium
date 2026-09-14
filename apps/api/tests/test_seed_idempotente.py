"""El seed debe poder ejecutarse dos veces sin romper nada."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.database import SessionMaintenance
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.roles.models import Role
from app.seed.demo import DEMO_NAME, DEMO_SLUG, seed_demo


async def _contar(modelo: type) -> int:
    async with SessionMaintenance() as session:
        total = await session.scalar(select(func.count()).select_from(modelo))
    return int(total or 0)


async def test_sembrar_dos_veces_no_duplica_nada() -> None:
    async with SessionMaintenance() as session:
        primero = await seed_demo(session)
        await session.commit()

    assert primero.created is True
    assert primero.owner_password, "la primera siembra debe generar una contraseña"

    conteos = {
        modelo: await _contar(modelo) for modelo in (Organization, Role, OrganizationMember)
    }

    async with SessionMaintenance() as session:
        segundo = await seed_demo(session)
        await session.commit()

    assert segundo.created is False
    assert segundo.owner_password is None, "no debe cambiar la contraseña existente"
    for modelo, esperado in conteos.items():
        assert await _contar(modelo) == esperado, f"{modelo.__name__} se ha duplicado"


async def test_el_owner_sembrado_puede_iniciar_sesion(cliente: AsyncClient) -> None:
    async with SessionMaintenance() as session:
        resultado = await seed_demo(session)
        await session.commit()

    assert resultado.owner_password is not None
    respuesta = await cliente.post(
        "/api/v1/auth/login",
        json={"email": resultado.owner_email, "password": resultado.owner_password},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["user"]["email"] == resultado.owner_email


async def test_la_organizacion_de_demostracion_queda_sembrada_con_su_slug() -> None:
    """Sin dominio por organización (fase 6 del plan «organización sin
    dominio»), la siembra ya no se verifica resolviendo por host: se
    comprueba directamente que la organización queda creada con su slug y
    nombre esperados, sin duplicarse en una segunda siembra."""
    async with SessionMaintenance() as session:
        await seed_demo(session)
        await session.commit()

    async with SessionMaintenance() as session:
        organizacion = await session.scalar(
            select(Organization).where(Organization.slug == DEMO_SLUG)
        )
    assert organizacion is not None
    assert organizacion.name == DEMO_NAME


async def test_reset_password_regenera_la_contrasena() -> None:
    async with SessionMaintenance() as session:
        await seed_demo(session)
        await session.commit()

    async with SessionMaintenance() as session:
        resultado = await seed_demo(session, reset_password=True)
        await session.commit()

    assert resultado.owner_password is not None
