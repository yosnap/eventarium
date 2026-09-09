"""Resolución de la organización por host: la base del aislamiento multi-tenant."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.core.tenant import base_url_de_organizacion, normalize_host
from app.main import create_app
from app.modules.organizations.models import OrganizationBranding
from tests.conftest import OrganizacionDePrueba

BRANDING = "/api/v1/tenant/branding"

# Id fijo de «claro» sembrado por `0014_plantillas_de_tema`.
_ID_PLANTILLA_CLARO = uuid.UUID("018fbb2f-0000-7000-8000-000000000002")


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("EJEMPLO.com", "ejemplo.com"),
        ("ejemplo.com:8080", "ejemplo.com"),
        ("  Localhost:4200 ", "localhost"),
        ("[::1]:8080", "[::1]"),
    ],
)
def test_normalize_host(entrada: str, esperado: str) -> None:
    assert normalize_host(entrada) == esperado


async def test_branding_devuelve_la_organizacion_del_host(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await cliente.get(BRANDING, headers={"Host": organizacion.host})
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["organization_slug"] == organizacion.slug
    assert cuerpo["template_key"] == "classic"


async def test_branding_resuelve_la_plantilla_por_defecto_cuando_no_hay_ninguna_elegida(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await cliente.get(BRANDING, headers={"Host": organizacion.host})
    assert respuesta.status_code == 200
    tema = respuesta.json()["theme"]
    assert tema is not None
    assert tema["key"] == "oscuro"
    assert set(tema["tokens"].keys()) == {"dark", "light"}


async def test_branding_resuelve_la_plantilla_elegida_por_la_organizacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    async with SessionMaintenance() as session:
        branding = await session.scalar(
            select(OrganizationBranding).where(
                OrganizationBranding.organization_id == organizacion.id
            )
        )
        assert branding is not None
        branding.theme_template_id = _ID_PLANTILLA_CLARO
        await session.commit()

    respuesta = await cliente.get(BRANDING, headers={"Host": organizacion.host})
    assert respuesta.status_code == 200
    assert respuesta.json()["theme"]["key"] == "claro"


async def test_cada_host_devuelve_su_propia_organizacion(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    primera = await cliente.get(BRANDING, headers={"Host": organizacion.host})
    segunda = await cliente.get(BRANDING, headers={"Host": otra_organizacion.host})
    assert primera.json()["organization_slug"] == organizacion.slug
    assert segunda.json()["organization_slug"] == otra_organizacion.slug


async def test_base_url_de_organizacion_conserva_el_puerto_en_desarrollo(
    organizacion: OrganizacionDePrueba,
) -> None:
    """Fase 6 del PRD: una redirección de Stripe (`return_url`) que perdiera el
    puerto de Caddy en desarrollo (`localhost` sin `:8080`) llevaría a una
    página que Caddy no expone. El dominio guardado en `organization_domains`
    nunca incluye puerto (no lo necesita en producción), así que la función
    debe añadirlo ella misma fuera de producción.
    """
    url = await base_url_de_organizacion(organizacion.id)
    assert url == "http://localhost:8080"


@pytest.mark.parametrize("host", ["desconocido.example", "sub.localhost", ""])
async def test_host_no_registrado_devuelve_404(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, host: str
) -> None:
    """Sin coincidencia exacta no hay organización: ni subdominios ni comodines."""
    respuesta = await cliente.get(BRANDING, headers={"Host": host})
    assert respuesta.status_code == 404


async def test_x_forwarded_host_se_ignora_desde_origen_no_confiable(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    """Un cliente que no es el proxy no puede elegir organización con una cabecera."""
    transporte = ASGITransport(app=create_app(), client=("203.0.113.10", 12345))
    async with AsyncClient(transport=transporte, base_url="http://localhost") as http:
        respuesta = await http.get(
            BRANDING,
            headers={"Host": organizacion.host, "X-Forwarded-Host": otra_organizacion.host},
        )
    assert respuesta.status_code == 200
    assert respuesta.json()["organization_slug"] == organizacion.slug


async def test_x_forwarded_host_se_acepta_desde_el_proxy_de_confianza(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    """Tras Caddy, el host original llega en X-Forwarded-Host y sí manda."""
    transporte = ASGITransport(app=create_app(), client=("127.0.0.1", 12345))
    async with AsyncClient(transport=transporte, base_url="http://localhost") as http:
        respuesta = await http.get(
            BRANDING,
            headers={"Host": organizacion.host, "X-Forwarded-Host": otra_organizacion.host},
        )
    assert respuesta.status_code == 200
    assert respuesta.json()["organization_slug"] == otra_organizacion.slug


async def test_cabecera_de_desarrollo_se_ignora_fuera_de_desarrollo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """`X-Organization-Slug` solo existe con APP_ENV=development; aquí es APP_ENV=test."""
    respuesta = await cliente.get(
        BRANDING,
        headers={"Host": "desconocido.example", "X-Organization-Slug": organizacion.slug},
    )
    assert respuesta.status_code == 404
