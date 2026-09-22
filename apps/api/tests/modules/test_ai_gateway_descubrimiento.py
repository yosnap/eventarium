"""Catálogo de modelos en vivo y prueba de conexión.

Ningún test sale a Internet: la fijación `listado_simulado` sustituye el
transporte HTTP del módulo de descubrimiento por un `httpx.MockTransport`,
igual que hace `proveedor_simulado` con el de LiteLLM. Las claves son
literales falsos de `ai_gateway_test_helpers`, nunca variables de entorno.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.modules.ai_gateway import cache_modelos, descubrimiento
from app.modules.ai_gateway.proveedores import PROVEEDORES
from tests.ai_gateway_test_helpers import (
    CLAVE_DE_PROVEEDOR,
    configurar_organizacion,
    configurar_plataforma,
    hacer_superadmin,
)
from tests.conftest import (
    OrganizacionDePrueba,
    crear_miembro,
    iniciar_sesion,
    iniciar_sesion_con,
)

MODELOS = "/api/v1/ai/catalog/{proveedor}/models"
PRUEBA = "/api/v1/ai/test-connection"


@dataclass(slots=True)
class ListadoSimulado:
    """Transporte falso del listado de modelos: registra lo que sale."""

    peticiones: list[httpx.Request] = field(default_factory=list)
    estado: int = 200
    cuerpo: Any = field(default_factory=lambda: {"data": [{"id": "modelo-de-prueba"}]})
    #: Si se rellena, la «llamada» levanta esta excepción en vez de responder.
    fallo: Exception | None = None

    async def _manejar(self, peticion: httpx.Request) -> httpx.Response:
        self.peticiones.append(peticion)
        if self.fallo is not None:
            raise self.fallo
        return httpx.Response(self.estado, json=self.cuerpo)

    @property
    def ultima(self) -> httpx.Request:
        assert self.peticiones, "no salió ninguna petición al proveedor"
        return self.peticiones[-1]


@pytest.fixture
def listado_simulado(monkeypatch: pytest.MonkeyPatch) -> Iterator[ListadoSimulado]:
    simulado = ListadoSimulado()
    original = httpx.AsyncClient

    def _cliente(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(simulado._manejar)
        return original(*args, **kwargs)

    monkeypatch.setattr(descubrimiento.httpx, "AsyncClient", _cliente)
    yield simulado


# --- Interpretación del cuerpo de cada proveedor ------------------------------


def test_openrouter_deduce_la_vision_de_las_modalidades_de_entrada() -> None:
    modelos = descubrimiento.interpretar(
        {
            "data": [
                {
                    "id": "openai/gpt-4o",
                    "name": "GPT-4o",
                    "architecture": {"input_modalities": ["text", "image"]},
                },
                {
                    "id": "meta/llama-solo-texto",
                    "name": "Llama",
                    "architecture": {"input_modalities": ["text"]},
                },
            ]
        }
    )

    por_clave = {modelo.clave: modelo for modelo in modelos}
    assert por_clave["openai/gpt-4o"].vision is True
    assert por_clave["openai/gpt-4o"].etiqueta == "GPT-4o"
    assert por_clave["meta/llama-solo-texto"].vision is False


def test_openrouter_tambien_entiende_la_modalidad_como_cadena() -> None:
    (modelo,) = descubrimiento.interpretar(
        {"data": [{"id": "x/y", "architecture": {"modality": "text+image->text"}}]}
    )

    assert modelo.vision is True


def test_la_modalidad_de_salida_no_cuenta_como_vision() -> None:
    """`text->text+image` genera imágenes, no las acepta."""
    (modelo,) = descubrimiento.interpretar(
        {"data": [{"id": "x/y", "architecture": {"modality": "text->text+image"}}]}
    )

    assert modelo.vision is False


def test_input_modalities_vacio_no_declara_nada() -> None:
    """`[]` no es «declara que no acepta imágenes» — es indistinguible de «no
    declarado»: debe caer al catálogo estático, no fijarse en `False`."""
    (modelo,) = descubrimiento.interpretar(
        {"data": [{"id": "x/y", "architecture": {"input_modalities": []}}]}
    )

    assert modelo.vision is None


def test_modality_vacia_no_declara_nada() -> None:
    (modelo,) = descubrimiento.interpretar(
        {"data": [{"id": "x/y", "architecture": {"modality": ""}}]}
    )

    assert modelo.vision is None


def test_anthropic_usa_capabilities_image_input() -> None:
    modelos = descubrimiento.interpretar(
        {
            "data": [
                {
                    "id": "claude-opus-5",
                    "display_name": "Claude Opus 5",
                    "capabilities": {"image_input": {"supported": True}},
                },
                # `capabilities` puede llegar a `null` en modelos antiguos.
                {"id": "claude-antiguo", "display_name": "Claude antiguo", "capabilities": None},
            ]
        }
    )

    por_clave = {modelo.clave: modelo for modelo in modelos}
    assert por_clave["claude-opus-5"].vision is True
    assert por_clave["claude-opus-5"].etiqueta == "Claude Opus 5"
    # Sin declaración del proveedor no se deduce nada aquí: queda «no consta».
    assert por_clave["claude-antiguo"].vision is None


def test_cheaper_inference_usa_capabilities_vision() -> None:
    modelos = descubrimiento.interpretar(
        {
            "data": [
                {"id": "gpt-5.4", "capabilities": {"vision": True, "streaming": True}},
                {"id": "solo-texto", "capabilities": {"vision": False}},
            ]
        }
    )

    por_clave = {modelo.clave: modelo for modelo in modelos}
    assert por_clave["gpt-5.4"].vision is True
    assert por_clave["solo-texto"].vision is False


def test_gemini_sale_de_models_y_pierde_el_prefijo() -> None:
    (modelo,) = descubrimiento.interpretar(
        {
            "models": [
                {
                    "name": "models/gemini-2.0-flash",
                    "displayName": "Gemini 2.0 Flash",
                    "supportedGenerationMethods": ["generateContent"],
                }
            ]
        }
    )

    # `generateContent` no dice nada sobre modalidades: el identificador se
    # normaliza, pero la visión queda «no consta».
    assert modelo.clave == "gemini-2.0-flash"
    assert modelo.etiqueta == "Gemini 2.0 Flash"
    assert modelo.vision is None


def test_openai_no_declara_capacidades_y_la_etiqueta_cae_al_identificador() -> None:
    (modelo,) = descubrimiento.interpretar(
        {"data": [{"id": "gpt-4o", "object": "model", "owned_by": "openai"}]}
    )

    assert modelo.clave == "gpt-4o"
    assert modelo.etiqueta == "gpt-4o"
    assert modelo.vision is None


def test_id_vacio_cae_al_name_y_no_se_confunde_con_ausente() -> None:
    """`id: ""` no es un identificador válido — cae a `name`, igual que si
    `id` faltara del todo, no se cuela como clave vacía."""
    (modelo,) = descubrimiento.interpretar({"data": [{"id": "", "name": "modelo-x"}]})

    assert modelo.clave == "modelo-x"


def test_dos_entradas_con_id_vacio_no_colisionan_entre_si() -> None:
    """Regresión: si `""` se usara tal cual como clave de deduplicación, la
    segunda entrada pisaría a la primera y se perdería un modelo real."""
    modelos = descubrimiento.interpretar(
        {"data": [{"id": "", "name": "modelo-a"}, {"id": "", "name": "modelo-b"}]}
    )

    assert {modelo.clave for modelo in modelos} == {"modelo-a", "modelo-b"}


def test_un_cuerpo_sin_listado_reconocible_no_se_interpreta() -> None:
    for cuerpo in ({"error": "nope"}, [], {"data": []}, {"data": [{"sin": "id"}]}):
        with pytest.raises(descubrimiento.ListadoNoDisponible) as fallo:
            descubrimiento.interpretar(cuerpo)
        assert fallo.value.motivo == descubrimiento.RESPUESTA_INESPERADA


def test_el_listado_esta_acotado() -> None:
    cuerpo = {"data": [{"id": f"modelo-{indice:04d}"} for indice in range(1200)]}

    modelos = descubrimiento.interpretar(cuerpo)

    assert len(modelos) == descubrimiento.MAXIMO_MODELOS


# --- Resolución de la marca de visión ------------------------------------------


def test_sin_declaracion_la_vision_cae_al_catalogo_estatico() -> None:
    # `openai/gpt-4o` está anotado a mano con visión en `proveedores.py`.
    resuelto = descubrimiento.resolver_vision(
        "openrouter",
        descubrimiento.ModeloDescubierto(clave="openai/gpt-4o", etiqueta="GPT-4o", vision=None),
    )

    assert resuelto.vision is True


def test_un_modelo_nuevo_sin_declaracion_queda_sin_vision() -> None:
    resuelto = descubrimiento.resolver_vision(
        "openai",
        descubrimiento.ModeloDescubierto(
            clave="gpt-inventado-9", etiqueta="GPT inventado", vision=None
        ),
    )

    assert resuelto.vision is False


def test_la_declaracion_del_proveedor_manda_sobre_el_catalogo_estatico() -> None:
    resuelto = descubrimiento.resolver_vision(
        "openai",
        descubrimiento.ModeloDescubierto(clave="gpt-4o", etiqueta="GPT-4o", vision=False),
    )

    assert resuelto.vision is False


# --- Petición saliente: direcciones, cabeceras y secreto ----------------------


async def test_cada_proveedor_sale_a_su_direccion_y_con_su_autenticacion(
    listado_simulado: ListadoSimulado, dns_publico: None
) -> None:
    esperado = {
        "nan_builders": ("https://api.nan.builders/v1/models", "authorization"),
        "cheaper_inference": ("https://api.cheaperinference.com/v1/models", "authorization"),
        "openrouter": ("https://openrouter.ai/api/v1/models", "authorization"),
        "openai": ("https://api.openai.com/v1/models", "authorization"),
        "anthropic": ("https://api.anthropic.com/v1/models", "x-api-key"),
        "gemini": (
            "https://generativelanguage.googleapis.com/v1beta/models",
            "x-goog-api-key",
        ),
    }

    for proveedor, (url, cabecera) in esperado.items():
        await descubrimiento.listar_modelos(proveedor, api_key=CLAVE_DE_PROVEEDOR)
        peticion = listado_simulado.ultima
        assert str(peticion.url) == url, proveedor
        assert peticion.headers[cabecera] == (
            CLAVE_DE_PROVEEDOR if cabecera != "authorization" else f"Bearer {CLAVE_DE_PROVEEDOR}"
        ), proveedor
        # La clave nunca viaja en la URL, ni siquiera en Gemini, cuyos
        # ejemplos oficiales usan `?key=`.
        assert CLAVE_DE_PROVEEDOR not in str(peticion.url), proveedor

    assert listado_simulado.peticiones[4].headers["anthropic-version"] == "2023-06-01"


async def test_un_proveedor_personalizado_sale_a_su_propia_direccion(
    listado_simulado: ListadoSimulado, dns_publico: None
) -> None:
    await descubrimiento.listar_modelos(
        "custom", api_key=CLAVE_DE_PROVEEDOR, api_base="https://modelos.example.com/v1/"
    )

    assert str(listado_simulado.ultima.url) == "https://modelos.example.com/v1/models"


async def test_un_proveedor_personalizado_hacia_la_red_interna_se_rechaza(
    listado_simulado: ListadoSimulado, dns_interno: None
) -> None:
    from app.modules.ai_gateway.validacion import ApiBaseInvalido

    with pytest.raises(ApiBaseInvalido):
        await descubrimiento.listar_modelos(
            "custom", api_key=CLAVE_DE_PROVEEDOR, api_base="https://interno.example.com/v1"
        )

    assert not listado_simulado.peticiones, "no debe salir ninguna petición"


async def test_un_proveedor_personalizado_sin_direccion_es_entrada_invalida(
    listado_simulado: ListadoSimulado,
) -> None:
    from app.modules.ai_gateway.errores import ApiBaseRequerido

    with pytest.raises(ApiBaseRequerido):
        await descubrimiento.listar_modelos("custom", api_key=CLAVE_DE_PROVEEDOR, api_base=None)


async def test_sin_clave_no_se_llama_salvo_en_el_listado_publico_de_openrouter(
    listado_simulado: ListadoSimulado,
) -> None:
    with pytest.raises(descubrimiento.ListadoNoDisponible) as fallo:
        await descubrimiento.listar_modelos("openai", api_key=None)
    assert fallo.value.motivo == descubrimiento.SIN_CLAVE
    assert not listado_simulado.peticiones

    await descubrimiento.listar_modelos("openrouter", api_key=None)

    assert "authorization" not in listado_simulado.ultima.headers


@pytest.mark.parametrize(
    ("estado", "motivo"),
    [(401, "clave_rechazada"), (403, "clave_rechazada"), (500, "proveedor_error")],
)
async def test_el_estado_del_proveedor_se_traduce_a_un_motivo(
    listado_simulado: ListadoSimulado, estado: int, motivo: str
) -> None:
    listado_simulado.estado = estado
    listado_simulado.cuerpo = {"error": {"message": f"Invalid API key {CLAVE_DE_PROVEEDOR}"}}

    with pytest.raises(descubrimiento.ListadoNoDisponible) as fallo:
        await descubrimiento.listar_modelos("openai", api_key=CLAVE_DE_PROVEEDOR)

    assert fallo.value.motivo == motivo


async def test_un_tiempo_agotado_tiene_su_propio_motivo(
    listado_simulado: ListadoSimulado,
) -> None:
    listado_simulado.fallo = httpx.ReadTimeout("agotado")

    with pytest.raises(descubrimiento.ListadoNoDisponible) as fallo:
        await descubrimiento.listar_modelos("openai", api_key=CLAVE_DE_PROVEEDOR)

    assert fallo.value.motivo == descubrimiento.TIEMPO_AGOTADO


async def test_la_clave_no_aparece_en_los_registros(
    listado_simulado: ListadoSimulado, caplog: pytest.LogCaptureFixture
) -> None:
    """El error de red reproduce la clave; el log tiene que salir saneado."""
    listado_simulado.fallo = httpx.ConnectError(
        f"fallo al conectar con Authorization: Bearer {CLAVE_DE_PROVEEDOR}"
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(descubrimiento.ListadoNoDisponible):
            await descubrimiento.listar_modelos("openai", api_key=CLAVE_DE_PROVEEDOR)

    registrado = caplog.text
    assert CLAVE_DE_PROVEEDOR not in registrado
    assert "***" in registrado


# --- Cota del cuerpo que se descarga ------------------------------------------


def _transporte_de_cuerpo(monkeypatch: pytest.MonkeyPatch, manejar: Any) -> None:
    """Sustituye el cliente del módulo por uno con este transporte falso."""
    original = httpx.AsyncClient

    def _cliente(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(manejar)
        return original(*args, **kwargs)

    monkeypatch.setattr(descubrimiento.httpx, "AsyncClient", _cliente)


async def test_un_cuerpo_enorme_se_corta_a_mitad_de_descarga(
    monkeypatch: pytest.MonkeyPatch, dns_publico: None
) -> None:
    """La cota actúa mientras baja el cuerpo, no después de tenerlo entero."""
    trozo = b"x" * (512 * 1024)
    veces = 3 * descubrimiento.MAXIMO_BYTES // len(trozo)
    emitidos = 0

    async def _cuerpo() -> AsyncIterator[bytes]:
        nonlocal emitidos
        for _ in range(veces):
            emitidos += 1
            yield trozo

    async def _manejar(_peticion: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_cuerpo())

    _transporte_de_cuerpo(monkeypatch, _manejar)

    with pytest.raises(descubrimiento.ListadoNoDisponible) as fallo:
        await descubrimiento.listar_modelos("openai", api_key=CLAVE_DE_PROVEEDOR)

    assert fallo.value.motivo == descubrimiento.RESPUESTA_INESPERADA
    # Se deja de leer en cuanto se pasa de la cota: ni un trozo más.
    assert emitidos == descubrimiento.MAXIMO_BYTES // len(trozo) + 1
    assert emitidos < veces


async def test_un_content_length_mayor_que_la_cota_se_rechaza_sin_leer(
    monkeypatch: pytest.MonkeyPatch, dns_publico: None
) -> None:
    leido = False

    async def _cuerpo() -> AsyncIterator[bytes]:
        nonlocal leido
        leido = True
        yield b"{}"

    async def _manejar(_peticion: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_cuerpo(),
            headers={"content-length": str(descubrimiento.MAXIMO_BYTES + 1)},
        )

    _transporte_de_cuerpo(monkeypatch, _manejar)

    with pytest.raises(descubrimiento.ListadoNoDisponible) as fallo:
        await descubrimiento.listar_modelos("openai", api_key=CLAVE_DE_PROVEEDOR)

    assert fallo.value.motivo == descubrimiento.RESPUESTA_INESPERADA
    assert not leido, "no debe leerse nada de un cuerpo que ya se declara enorme"


# --- Endpoint del desplegable --------------------------------------------------


async def test_el_desplegable_sirve_los_modelos_en_vivo(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    await configurar_organizacion(organizacion.id, provider="openai", default_model="gpt-4o")
    listado_simulado.cuerpo = {"data": [{"id": "gpt-4o"}, {"id": "gpt-6-nuevo"}]}
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get(MODELOS.format(proveedor="openai"), headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["en_vivo"] is True
    assert cuerpo["motivo"] is None
    assert [modelo["clave"] for modelo in cuerpo["modelos"]] == ["gpt-4o", "gpt-6-nuevo"]
    # OpenAI no declara capacidades: `gpt-4o` hereda la marca del catálogo
    # estático y el modelo nuevo se queda sin visión, conservador.
    por_clave = {modelo["clave"]: modelo for modelo in cuerpo["modelos"]}
    assert por_clave["gpt-4o"]["vision"] is True
    assert por_clave["gpt-6-nuevo"]["vision"] is False
    # La clave no sale por ningún lado de la respuesta.
    assert CLAVE_DE_PROVEEDOR not in respuesta.text


async def test_la_segunda_llamada_dentro_del_ttl_no_vuelve_a_salir(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    await configurar_organizacion(organizacion.id, provider="openai", default_model="gpt-4o")
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    url = MODELOS.format(proveedor="openai")

    primera = await cliente.get(url, headers=cabeceras)
    segunda = await cliente.get(url, headers=cabeceras)

    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert segunda.json() == primera.json()
    assert len(listado_simulado.peticiones) == 1, "la segunda salió a la red"


async def test_guardar_un_modelo_que_solo_esta_en_el_listado_en_vivo_se_acepta(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    """Regresión: `service._validar_modelo_en_vivo` debe aceptar un modelo
    que el proveedor sí ofrece aunque `proveedores.py` (catálogo anotado a
    mano) no lo tenga anotado — el caso real que lo motivó: `gemma4` es un
    modelo de `nan_builders` con visión que el catálogo no conocía, y el
    guardado lo rechazaba pese a que «Probar conexión» ya lo enseñaba en el
    desplegable con esa misma clave (hallazgo del usuario)."""
    listado_simulado.cuerpo = {"data": [{"id": "gemma4", "capabilities": {"vision": True}}]}
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    guardado = await cliente.put(
        "/api/v1/organizations/me/ai-settings",
        headers=cabeceras,
        json={
            "provider": "nan_builders",
            "default_model": "gemma4",
            "api_key": CLAVE_DE_PROVEEDOR,
        },
    )
    assert guardado.status_code == 200, guardado.text
    assert guardado.json()["default_model"] == "gemma4"


async def test_guardar_un_modelo_ausente_del_listado_en_vivo_se_rechaza(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    """La otra cara: un modelo que ni el catálogo estático ni el proveedor
    reconocen se sigue rechazando (no basta con "cualquier cosa vale")."""
    listado_simulado.cuerpo = {"data": [{"id": "gemma4"}]}
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    guardado = await cliente.put(
        "/api/v1/organizations/me/ai-settings",
        headers=cabeceras,
        json={
            "provider": "nan_builders",
            "default_model": "modelo-que-no-existe",
            "api_key": CLAVE_DE_PROVEEDOR,
        },
    )
    assert guardado.status_code == 422, guardado.text
    assert guardado.json()["code"] == "modelo_desconocido"


async def test_guardar_se_degrada_al_catalogo_estatico_si_el_proveedor_no_responde(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    """Si el listado en vivo falla, se valida contra el catálogo estático —
    mismo criterio que el desplegable (`catalogo_dinamico.modelos_de_proveedor`):
    un modelo YA conocido (`deepseek-v4-flash`) se sigue aceptando aunque el
    proveedor esté caído en ese instante."""
    listado_simulado.estado = 503
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    guardado = await cliente.put(
        "/api/v1/organizations/me/ai-settings",
        headers=cabeceras,
        json={
            "provider": "nan_builders",
            "default_model": "deepseek-v4-flash",
            "api_key": CLAVE_DE_PROVEEDOR,
        },
    )
    assert guardado.status_code == 200, guardado.text


async def test_cambiar_solo_el_modelo_tambien_valida_en_vivo_con_la_clave_ya_guardada(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    """`elif "default_model" in enviados` (sin `api_key` en la petición):
    la validación en vivo tiene que descifrar y usar la clave YA guardada,
    no quedarse sin clave y degradar de más."""
    listado_simulado.cuerpo = {"data": [{"id": "deepseek-v4-flash"}]}
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    creado = await cliente.put(
        "/api/v1/organizations/me/ai-settings",
        headers=cabeceras,
        json={
            "provider": "nan_builders",
            "default_model": "deepseek-v4-flash",
            "api_key": CLAVE_DE_PROVEEDOR,
        },
    )
    assert creado.status_code == 200, creado.text

    listado_simulado.cuerpo = {"data": [{"id": "gemma4"}]}
    cambiado = await cliente.put(
        "/api/v1/organizations/me/ai-settings",
        headers=cabeceras,
        json={"default_model": "gemma4"},
    )
    assert cambiado.status_code == 200, cambiado.text
    assert cambiado.json()["default_model"] == "gemma4"
    # La petición en vivo llevaba la clave ya guardada, no vacía.
    assert listado_simulado.ultima.headers.get("authorization") == f"Bearer {CLAVE_DE_PROVEEDOR}"


async def test_guardar_la_configuracion_invalida_lo_cacheado(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    await configurar_organizacion(organizacion.id, provider="openai", default_model="gpt-4o")
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    url = MODELOS.format(proveedor="openai")
    await cliente.get(url, headers=cabeceras)

    # El modelo nuevo tiene que estar en lo que "responde" el proveedor: el
    # `PUT` ahora valida el modelo en vivo con la clave que se está guardando
    # (ver `service._validar_modelo_en_vivo`), no solo el catálogo estático.
    listado_simulado.cuerpo = {"data": [{"id": "gpt-4o-mini"}]}
    guardado = await cliente.put(
        "/api/v1/organizations/me/ai-settings",
        headers=cabeceras,
        json={
            "provider": "openai",
            "default_model": "gpt-4o-mini",
            "api_key": "sk-otra-clave-de-prueba-9999",
        },
    )
    await cliente.get(url, headers=cabeceras)

    assert guardado.status_code == 200, guardado.text
    assert len(listado_simulado.peticiones) == 3, "la clave nueva debe reconsultar"


async def test_si_el_proveedor_falla_se_degrada_al_catalogo_conocido(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    await configurar_organizacion(organizacion.id, provider="openai", default_model="gpt-4o")
    listado_simulado.estado = 503
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get(MODELOS.format(proveedor="openai"), headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["en_vivo"] is False
    assert cuerpo["motivo"] == "proveedor_error"
    assert [modelo["clave"] for modelo in cuerpo["modelos"]] == [
        modelo.clave for modelo in PROVEEDORES["openai"].modelos
    ]


async def test_un_fallo_no_se_cachea(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    await configurar_organizacion(organizacion.id, provider="openai", default_model="gpt-4o")
    listado_simulado.estado = 503
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    url = MODELOS.format(proveedor="openai")

    await cliente.get(url, headers=cabeceras)
    listado_simulado.estado = 200
    segunda = await cliente.get(url, headers=cabeceras)

    assert segunda.json()["en_vivo"] is True
    assert len(listado_simulado.peticiones) == 2


async def test_sin_clave_para_ese_proveedor_se_degrada_sin_llamar(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    """La clave guardada es de OpenAI: no se manda a Anthropic."""
    await configurar_organizacion(organizacion.id, provider="openai", default_model="gpt-4o")
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get(MODELOS.format(proveedor="anthropic"), headers=cabeceras)

    cuerpo = respuesta.json()
    assert cuerpo["en_vivo"] is False
    assert cuerpo["motivo"] == "sin_clave"
    assert not listado_simulado.peticiones


async def test_quien_hereda_usa_la_clave_de_plataforma(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    await configurar_plataforma(provider="openai", default_model="gpt-4o")
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get(MODELOS.format(proveedor="openai"), headers=cabeceras)

    assert respuesta.json()["en_vivo"] is True
    assert listado_simulado.ultima.headers["authorization"] == f"Bearer {CLAVE_DE_PROVEEDOR}"
    # Se cachea en el ámbito compartido, no en el de la organización.
    assert await cache_modelos.leer(None, "openai") is not None
    assert await cache_modelos.leer(organizacion.id, "openai") is None


async def test_un_proveedor_fuera_del_catalogo_es_un_422(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get(MODELOS.format(proveedor="inventado"), headers=cabeceras)

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "proveedor_desconocido"


async def test_el_desplegable_exige_sesion(cliente: AsyncClient) -> None:
    respuesta = await cliente.get(MODELOS.format(proveedor="openai"))

    assert respuesta.status_code == 401


# --- Prueba de conexión --------------------------------------------------------


async def test_la_prueba_de_conexion_usa_la_clave_enviada_sin_guardarla(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    """No hay ninguna configuración guardada: la clave es la del cuerpo."""
    listado_simulado.cuerpo = {"data": [{"id": "gpt-4o"}]}
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        PRUEBA,
        headers=cabeceras,
        json={"provider": "openai", "api_key": "sk-clave-recien-escrita-4321"},
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["ok"] is True
    assert cuerpo["motivo"] is None
    assert [modelo["clave"] for modelo in cuerpo["modelos"]] == ["gpt-4o"]
    assert listado_simulado.ultima.headers["authorization"] == "Bearer sk-clave-recien-escrita-4321"
    assert "sk-clave-recien-escrita-4321" not in respuesta.text

    # Comprobar no guarda: la organización sigue sin configuración propia.
    ajustes = await cliente.get("/api/v1/organizations/me/ai-settings", headers=cabeceras)
    assert ajustes.json()["origen"] == "sin_configuracion"


async def test_la_prueba_de_conexion_sin_clave_usa_la_ya_guardada_de_la_organizacion(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    """El botón «Probar conexión» con el campo de clave vacío prueba la que
    ya está guardada — sin esto, comprobar que una clave ya guardada seguía
    siendo válida exigía volver a escribirla en el formulario (hallazgo del
    usuario: el botón se quedaba deshabilitado con el campo vacío)."""
    await configurar_organizacion(
        organizacion.id, provider="openai", default_model="gpt-4o", clave="sk-clave-guardada-org-1"
    )
    listado_simulado.cuerpo = {"data": [{"id": "gpt-4o"}]}
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(PRUEBA, headers=cabeceras, json={"provider": "openai"})

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["ok"] is True
    assert listado_simulado.ultima.headers["authorization"] == "Bearer sk-clave-guardada-org-1"


async def test_la_prueba_de_conexion_sin_clave_usa_la_de_plataforma_si_es_superadmin(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    await configurar_plataforma(
        provider="openai", default_model="gpt-4o", clave="sk-clave-guardada-plataforma-1"
    )
    miembro = await crear_miembro(organizacion, "organizer", email="plataforma2@acme.com")
    await hacer_superadmin(miembro.email)
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, miembro.email, miembro.password)
    listado_simulado.cuerpo = {"data": [{"id": "gpt-4o"}]}

    respuesta = await cliente.post(PRUEBA, headers=cabeceras, json={"provider": "openai"})

    assert respuesta.status_code == 200, respuesta.text
    autorizacion = listado_simulado.ultima.headers["authorization"]
    assert autorizacion == "Bearer sk-clave-guardada-plataforma-1"


async def test_la_prueba_de_conexion_sin_clave_ni_guardada_es_422(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(PRUEBA, headers=cabeceras, json={"provider": "openai"})
    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == "clave_requerida"


async def test_la_prueba_de_conexion_sin_clave_no_reutiliza_la_de_otro_proveedor(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    """La clave guardada es de `openai`; probar `openrouter` sin escribir una
    nueva no debe reutilizarla — la mandaría a un endpoint que no es el
    suyo."""
    await configurar_organizacion(
        organizacion.id, provider="openai", default_model="gpt-4o", clave="sk-clave-guardada-org-1"
    )
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(PRUEBA, headers=cabeceras, json={"provider": "openrouter"})

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == "clave_requerida"
    assert len(listado_simulado.peticiones) == 0


async def test_una_clave_rechazada_es_un_resultado_no_un_error(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    listado_simulado.estado = 401
    listado_simulado.cuerpo = {"error": {"message": "Invalid API key."}}
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        PRUEBA, headers=cabeceras, json={"provider": "openai", "api_key": "sk-clave-mala-0001"}
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"ok": False, "motivo": "clave_rechazada", "modelos": []}


async def test_la_prueba_no_cachea_nada(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    cuerpo = {"provider": "openai", "api_key": "sk-clave-recien-escrita-4321"}

    await cliente.post(PRUEBA, headers=cabeceras, json=cuerpo)
    await cliente.post(PRUEBA, headers=cabeceras, json=cuerpo)

    assert len(listado_simulado.peticiones) == 2
    assert await cache_modelos.leer(organizacion.id, "openai") is None
    assert await cache_modelos.leer(None, "openai") is None


async def test_la_prueba_de_un_personalizado_valida_su_direccion(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    listado_simulado: ListadoSimulado,
    dns_interno: None,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        PRUEBA,
        headers=cabeceras,
        json={
            "provider": "custom",
            "api_base": "https://interno.example.com/v1",
            "api_key": "sk-clave-recien-escrita-4321",
        },
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "api_base_invalido"
    assert not listado_simulado.peticiones


async def test_la_prueba_exige_sesion(cliente: AsyncClient) -> None:
    respuesta = await cliente.post(
        PRUEBA, json={"provider": "openai", "api_key": "sk-clave-recien-escrita-4321"}
    )

    assert respuesta.status_code == 401


# --- Quién puede provocar la llamada saliente ---------------------------------


async def test_un_miembro_sin_rol_owner_no_puede_provocar_la_llamada_saliente(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    listado_simulado: ListadoSimulado,
) -> None:
    """Estar autenticado no basta: gastaría la clave de su organización y, con
    `custom`, saldría a un host elegido por él con la cabecera que quisiera."""
    miembro = await crear_miembro(organizacion, "organizer")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, miembro.email, miembro.password)

    modelos = await cliente.get(MODELOS.format(proveedor="openai"), headers=cabeceras)
    prueba = await cliente.post(
        PRUEBA,
        headers=cabeceras,
        json={
            "provider": "custom",
            "api_base": "https://host-elegido.example.com/v1",
            "api_key": "sk-clave-recien-escrita-4321",
        },
    )

    assert modelos.status_code == 403, modelos.text
    assert prueba.status_code == 403, prueba.text
    assert not listado_simulado.peticiones, "no debe salir ninguna petición"


async def test_el_owner_de_su_organizacion_si_puede(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    modelos = await cliente.get(MODELOS.format(proveedor="openrouter"), headers=cabeceras)
    prueba = await cliente.post(
        PRUEBA, headers=cabeceras, json={"provider": "openai", "api_key": "sk-clave-0001"}
    )

    assert modelos.status_code == 200, modelos.text
    assert prueba.status_code == 200, prueba.text


async def test_el_personal_de_plataforma_pasa_sin_ser_owner_de_nada(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    listado_simulado: ListadoSimulado,
    dns_publico: None,
) -> None:
    """El panel de plataforma usa los mismos dos endpoints, y su gate es
    `is_superadmin`: quien lo es no tiene por qué ser `owner` de ninguna
    organización."""
    miembro = await crear_miembro(organizacion, "organizer", email="plataforma@acme.com")
    await hacer_superadmin(miembro.email)
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, miembro.email, miembro.password)

    modelos = await cliente.get(MODELOS.format(proveedor="openrouter"), headers=cabeceras)
    prueba = await cliente.post(
        PRUEBA, headers=cabeceras, json={"provider": "openai", "api_key": "sk-clave-0001"}
    )

    assert modelos.status_code == 200, modelos.text
    assert prueba.status_code == 200, prueba.text
