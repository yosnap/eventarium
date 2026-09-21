"""Traducción del catálogo a LiteLLM, con mock HTTP y sin red ni claves reales.

Mismo patrón que los tests de `payments/stripe_client.py`: la petición se
construye entera y se inspecciona antes de salir de proceso, así que se puede
afirmar exactamente qué `model`, qué `api_base` y qué cabecera
`Authorization` habrían llegado al proveedor.

Las claves son literales falsos con el formato de cada proveedor
(`sk-test-…`, `ci_live_test-…`), nunca variables de entorno de una cuenta
real.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.ai_gateway import client as ai_client
from tests.ai_gateway_test_helpers import (
    ProveedorSimulado,
    configurar_organizacion,
    respuesta_de_chat,
)
from tests.conftest import OrganizacionDePrueba

MENSAJES = [{"role": "user", "content": "hola"}]

CLAVE_NAN = "sk-test-nan-0000-1111"
CLAVE_CHEAPER = "ci_live_test-2222-3333"
CLAVE_OPENROUTER = "sk-or-test-4444-5555"


@pytest.mark.parametrize(
    ("provider", "modelo", "clave", "url_esperada", "modelo_en_el_cuerpo"),
    [
        (
            "nan_builders",
            "deepseek-v4-flash",
            CLAVE_NAN,
            "https://api.nan.builders/v1/chat/completions",
            "deepseek-v4-flash",
        ),
        (
            "cheaper_inference",
            "gpt-5.4",
            CLAVE_CHEAPER,
            "https://api.cheaperinference.com/v1/chat/completions",
            "gpt-5.4",
        ),
        (
            "openrouter",
            "openai/gpt-4o-mini",
            CLAVE_OPENROUTER,
            "https://openrouter.ai/api/v1/chat/completions",
            "openai/gpt-4o-mini",
        ),
    ],
)
async def test_cada_proveedor_sale_a_su_direccion_con_su_clave(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
    provider: str,
    modelo: str,
    clave: str,
    url_esperada: str,
    modelo_en_el_cuerpo: str,
) -> None:
    """`nan_builders` y `cheaper_inference` enrutan por `openai/...` contra la
    dirección fija del catálogo; `openrouter` enruta por `openrouter/...` sin
    `api_base` propio (la pone LiteLLM). En los tres casos la clave sale en
    `Authorization: Bearer`, y es la de la organización, no ninguna del
    entorno."""
    proveedor_simulado.cuerpo = respuesta_de_chat(model=modelo)
    await configurar_organizacion(
        organizacion.id, provider=provider, default_model=modelo, clave=clave
    )

    await ai_client.completar(organization_id=organizacion.id, use_case="prueba", messages=MENSAJES)

    salida = proveedor_simulado.ultima
    assert salida.url == url_esperada
    assert salida.authorization == f"Bearer {clave}"
    assert salida.cuerpo["model"] == modelo_en_el_cuerpo


def test_el_api_base_efectivo_sale_del_catalogo() -> None:
    """La dirección de los proveedores de base fija no viene de la fila: si
    el proveedor cambia de URL se cambia en el catálogo y nada más."""
    from app.modules.ai_gateway import proveedores

    assert proveedores.api_base_efectivo("nan_builders", None) == "https://api.nan.builders/v1"
    assert (
        proveedores.api_base_efectivo("cheaper_inference", None)
        == "https://api.cheaperinference.com/v1"
    )
    assert proveedores.api_base_efectivo("openrouter", None) is None


async def test_los_dos_gateways_dejan_el_gasto_no_auditable(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    """Ni el catálogo de NaN ni el de CheaperInference están en el mapa de
    precios de LiteLLM: su gasto queda estimado, nunca a cero ni a nulo."""
    for provider, modelo, clave in (
        ("nan_builders", "glm5.3", CLAVE_NAN),
        ("cheaper_inference", "gemini-3.7-flash", CLAVE_CHEAPER),
    ):
        await configurar_organizacion(
            organizacion.id, provider=provider, default_model=modelo, clave=clave
        )
        resultado = await ai_client.completar(
            organization_id=organizacion.id, use_case="prueba", messages=MENSAJES
        )
        assert resultado.cost_auditable is False
        assert resultado.cost_usd == ai_client.COSTE_DE_SEGURIDAD_USD


async def test_openrouter_si_da_un_coste_auditable(
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
) -> None:
    await configurar_organizacion(
        organizacion.id,
        provider="openrouter",
        default_model="openai/gpt-4o",
        clave=CLAVE_OPENROUTER,
    )
    proveedor_simulado.cuerpo = respuesta_de_chat(model="openai/gpt-4o")

    resultado = await ai_client.completar(
        organization_id=organizacion.id, use_case="prueba", messages=MENSAJES
    )

    assert resultado.cost_auditable is True
    assert resultado.cost_usd > Decimal("0")
