"""Identidad de plataforma y enlaces sin sesión, sin ninguna resolución por host.

Fase 6 del plan «organización sin dominio»: `resolve_organization`,
`extract_host`, `normalize_host` y `resolve_host` se retiraron del backend —
ya no hay ningún endpoint que decida nada a partir de la cabecera `Host`.
"""

from __future__ import annotations

from httpx import AsyncClient

from app.core.config import get_settings
from app.core.tenant import base_url_de_organizacion
from tests.conftest import OrganizacionDePrueba

BRANDING = "/api/v1/tenant/branding"


async def test_branding_devuelve_siempre_la_identidad_de_plataforma(
    cliente: AsyncClient,
) -> None:
    respuesta = await cliente.get(BRANDING)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["platform"]["name"] == "Eventarium"
    assert "organization" not in cuerpo


async def test_branding_no_depende_de_ninguna_cabecera_host(cliente: AsyncClient) -> None:
    """Ni un host de organización real, ni uno inventado, cambian la respuesta."""
    sin_cabecera = (await cliente.get(BRANDING)).json()
    con_host_desconocido = (
        await cliente.get(BRANDING, headers={"Host": "no-existe.example"})
    ).json()
    assert sin_cabecera == con_host_desconocido


async def test_base_url_de_organizacion_es_siempre_la_de_la_instalacion(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    """Sin dominio por organización (fase 4 del plan de organización sin
    dominio), un enlace que llega sin sesión ni contexto (correo
    transaccional, redirección de Stripe) apunta siempre al dominio único de
    la instalación, con independencia de la organización del recurso — ya no
    hay ninguna organización con dominio propio que resolver.
    """
    esperado = get_settings().web_base_url
    assert await base_url_de_organizacion(organizacion.id) == esperado
    assert await base_url_de_organizacion(otra_organizacion.id) == esperado
