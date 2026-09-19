"""Catálogo de proveedores y validación SSRF del `api_base`.

Sin red: las IPs se prueban por literal, nunca resolviendo un hostname real
(mismo criterio que `test_ssrf_validation.py`, para no depender de cómo
resuelva el DNS de CI).
"""

from __future__ import annotations

import pytest

from app.modules.ai_gateway import proveedores, servicios
from app.modules.ai_gateway.errores import ErrorDeConfiguracionDeIa
from app.modules.ai_gateway.validacion import validar_api_base


def test_los_tres_proveedores_soportados_estan_en_el_catalogo() -> None:
    for clave in ("nan_builders", "openrouter", "cheaper_inference"):
        assert clave in proveedores.PROVEEDORES


def test_solo_custom_pide_api_base() -> None:
    """El formulario no pide dirección a ningún otro proveedor."""
    editables = [
        clave for clave, proveedor in proveedores.PROVEEDORES.items() if proveedor.api_base_editable
    ]
    assert editables == ["custom"]


def test_los_gateways_llevan_su_api_base_constante() -> None:
    assert proveedores.PROVEEDORES["nan_builders"].api_base_fijo == "https://api.nan.builders/v1"
    assert (
        proveedores.PROVEEDORES["cheaper_inference"].api_base_fijo
        == "https://api.cheaperinference.com/v1"
    )


def test_api_base_efectivo_sale_del_catalogo_aunque_la_fila_este_vacia() -> None:
    assert proveedores.api_base_efectivo("nan_builders", None) == "https://api.nan.builders/v1"
    assert proveedores.api_base_efectivo("openrouter", None) is None
    assert proveedores.api_base_efectivo("custom", "https://mi.endpoint/v1") == (
        "https://mi.endpoint/v1"
    )


def test_ningun_proveedor_declara_un_api_base_no_https() -> None:
    for proveedor in proveedores.PROVEEDORES.values():
        if proveedor.api_base_fijo is not None:
            assert proveedor.api_base_fijo.startswith("https://")


def test_todo_proveedor_cerrado_tiene_al_menos_un_modelo() -> None:
    """Un proveedor sin modelos y sin modelos abiertos sería inservible."""
    for proveedor in proveedores.PROVEEDORES.values():
        assert proveedor.modelos or proveedor.modelos_abiertos


def test_el_modelo_se_valida_contra_la_lista_del_proveedor() -> None:
    nan = proveedores.PROVEEDORES["nan_builders"]
    assert nan.acepta_modelo("deepseek-v4-flash")
    assert not nan.acepta_modelo("gpt-4o")


def test_custom_acepta_cualquier_modelo_no_vacio() -> None:
    custom = proveedores.PROVEEDORES["custom"]
    assert custom.acepta_modelo("mi-modelo-local")
    assert not custom.acepta_modelo("  ")


def test_cada_modelo_declara_su_marca_de_vision() -> None:
    for proveedor in proveedores.PROVEEDORES.values():
        for modelo in proveedor.modelos:
            assert isinstance(modelo.vision, bool)


def test_el_catalogo_de_servicios_incluye_ia() -> None:
    assert servicios.existe(servicios.SERVICIO_IA)
    assert not servicios.existe("inventado")


@pytest.mark.parametrize("es_produccion", [True, False])
def test_rechaza_esquema_no_https(es_produccion: bool) -> None:
    with pytest.raises(ErrorDeConfiguracionDeIa):
        validar_api_base("http://ejemplo.com/v1", es_produccion=es_produccion)


@pytest.mark.parametrize(
    "url",
    [
        "https://10.0.0.5/v1",
        "https://192.168.1.5/v1",
        "https://172.16.0.5/v1",
        "https://169.254.169.254/v1",
        "https://[::ffff:169.254.169.254]/v1",  # IPv4-mapped: esquiva is_link_local
        "https://100.64.0.1/v1",  # CGNAT
        "https://0.0.0.0/v1",
        "https://[fd00::1]/v1",
        "https://[fe80::1]/v1",
        "https://127.0.0.1/v1",
        "https://[::1]/v1",
        "https://localhost/v1",
    ],
)
def test_rechaza_direcciones_internas_en_produccion(url: str) -> None:
    with pytest.raises(ErrorDeConfiguracionDeIa):
        validar_api_base(url, es_produccion=True)


def test_fuera_de_produccion_se_admite_un_modelo_local() -> None:
    """`http://localhost` en desarrollo, y solo contra la propia máquina."""
    assert validar_api_base("http://localhost:11434/v1", es_produccion=False) == (
        "http://localhost:11434/v1"
    )
    with pytest.raises(ErrorDeConfiguracionDeIa):
        validar_api_base("https://10.0.0.5/v1", es_produccion=False)


def test_una_url_sin_host_se_rechaza() -> None:
    with pytest.raises(ErrorDeConfiguracionDeIa):
        validar_api_base("https:///v1", es_produccion=False)


def test_quita_la_barra_final() -> None:
    assert validar_api_base("http://127.0.0.1:8000/v1/", es_produccion=False) == (
        "http://127.0.0.1:8000/v1"
    )


def test_el_contrato_publica_la_clave_como_write_only_y_el_catalogo() -> None:
    """La clave no puede existir en ningún esquema de salida.

    Se comprueba sobre el esquema que genera la propia aplicación, no sobre
    `openapi.json` exportado: así un cambio de esquema falla aquí aunque
    nadie haya regenerado el fichero todavía.
    """
    from app.main import create_app

    esquemas = create_app().openapi()["components"]["schemas"]

    for nombre in ("PlatformAiSettingsUpdate", "OrganizationAiSettingsUpdate"):
        api_key = esquemas[nombre]["properties"]["api_key"]
        variantes = api_key.get("anyOf", [api_key])
        assert any(v.get("writeOnly") is True for v in variantes), nombre
        assert "example" not in api_key and "examples" not in api_key

    for nombre in ("PlatformAiSettingsOut", "OrganizationAiSettingsOut"):
        assert "api_key" not in esquemas[nombre]["properties"], nombre

    provider = esquemas["PlatformAiSettingsUpdate"]["properties"]["provider"]
    publicados = [
        valor
        for variante in provider.get("anyOf", [provider])
        for valor in variante.get("enum", [])
    ]
    assert publicados == list(proveedores.CLAVES_DE_PROVEEDOR)
