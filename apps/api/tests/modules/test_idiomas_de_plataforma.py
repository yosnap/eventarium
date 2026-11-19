"""Idiomas activos de la plataforma y visibilidad del selector de idioma."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.modules.platform.models import PlatformBranding
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

IDENTIDAD = "/api/v1/admin/identity"
BRANDING = "/api/v1/tenant/branding"


async def _cabeceras_superadmin(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> dict[str, str]:
    from app.modules.users.models import User

    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == organizacion.owner_email))
        assert usuario is not None
        usuario.is_superadmin = True
        await session.commit()
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    return cabeceras


@pytest.fixture(autouse=True)
async def _restaurar() -> AsyncIterator[None]:
    yield
    async with SessionMaintenance() as session:
        branding = await session.get(PlatformBranding, "default")
        if branding is not None:
            branding.enabled_locales = ["es-ES", "en-US"]
            branding.language_switcher_visible = True
            await session.commit()


async def test_por_defecto_estan_todos_los_idiomas_y_el_selector(cliente: AsyncClient) -> None:
    plataforma = (await cliente.get(BRANDING)).json()["platform"]
    assert plataforma["enabled_locales"] == ["es-ES", "en-US"]
    assert plataforma["language_switcher_visible"] is True


async def test_el_superadmin_desactiva_el_ingles_y_oculta_el_selector(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _cabeceras_superadmin(cliente, organizacion)
    respuesta = await cliente.patch(
        IDENTIDAD,
        headers=cabeceras,
        json={"enabled_locales": ["es-ES"], "language_switcher_visible": False},
    )
    assert respuesta.status_code == 200, respuesta.text
    plataforma = (await cliente.get(BRANDING)).json()["platform"]
    assert plataforma["enabled_locales"] == ["es-ES"]
    assert plataforma["language_switcher_visible"] is False


async def test_el_idioma_por_defecto_no_se_puede_desactivar(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _cabeceras_superadmin(cliente, organizacion)
    respuesta = await cliente.patch(
        IDENTIDAD, headers=cabeceras, json={"enabled_locales": ["en-US"]}
    )
    assert respuesta.status_code == 422
    fuera_de_catalogo = await cliente.patch(
        IDENTIDAD, headers=cabeceras, json={"enabled_locales": ["es-ES", "fr-FR"]}
    )
    assert fuera_de_catalogo.status_code == 422


async def test_quien_no_es_superadmin_no_cambia_los_idiomas(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.patch(
        IDENTIDAD, headers=cabeceras, json={"enabled_locales": ["es-ES"]}
    )
    assert respuesta.status_code == 403
