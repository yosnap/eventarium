"""Estadísticas de GA4 en el panel (fase 2 del plan
`260916-2246-cookies-analitica-externa`).

Lo que se fija aquí: el endpoint **nunca** responde 500/503 — credencial
ausente, JSON corrupto o API caída salen como `estado` explícito con 200,
para que la pantalla del panel se renderice igual; ningún mensaje (log o
respuesta) contiene fragmentos del JSON de la credencial; `dias` solo acepta
el enum 7|30; y el resultado exitoso queda en la caché de Redis (una segunda
petición no vuelve a hablar con Google). La API real de Google jamás se
llama en la suite.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest
from google.api_core.exceptions import GoogleAPIError, NotFound, PermissionDenied, ResourceExhausted
from google.auth.exceptions import RefreshError
from httpx import AsyncClient
from sqlalchemy import update

from app.core.config import get_settings
from app.core.database import SessionMaintenance
from app.core.redis_client import get_redis
from app.modules.admin import ga4_client
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

GA4_STATS = "/api/v1/admin/analytics-providers/ga4-stats"
JSON_CREDENCIAL = (
    '{"type": "service_account", "project_id": "prueba", '
    '"private_key": "no-es-una-clave", "client_email": "lector@prueba.iam"}'
)
FRAGMENTO_SECRETO = "FRAGMENTO-SECRETO-QUE-NO-DEBE-FUGARSE"


class ClienteFalso:
    """Sustituto de `BetaAnalyticsDataAsyncClient`: devuelve la respuesta o
    lanza el error configurado, y cuenta las llamadas (para la caché)."""

    def __init__(self, respuesta: Any = None, error: Exception | None = None) -> None:
        self.respuesta = respuesta
        self.error = error
        self.llamadas = 0

    async def run_report(self, *, request: Any, timeout: float | None = None) -> Any:
        self.llamadas += 1
        if self.error is not None:
            raise self.error
        return self.respuesta


def _respuesta_con_datos(usuarios: str = "12", sesiones: str = "34", vistas: str = "56") -> Any:
    return SimpleNamespace(
        rows=[
            SimpleNamespace(
                metric_values=[
                    SimpleNamespace(value=usuarios),
                    SimpleNamespace(value=sesiones),
                    SimpleNamespace(value=vistas),
                ]
            )
        ]
    )


@pytest.fixture(autouse=True)
def _entorno_ga4_limpio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin credencial ni property de entorno, y sin cliente gRPC cacheado:
    cada test monta lo suyo y monkeypatch lo restaura al salir."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ga4_service_account_json", "")
    monkeypatch.setattr(settings, "ga4_property_id", "")
    monkeypatch.setattr(ga4_client, "_cliente", None)


def _simular_credencial_valida(monkeypatch: pytest.MonkeyPatch) -> None:
    """Credencial y property informados; el parseo devuelve un sustituto (la
    clave privada de prueba no es real, así que la carga real fallaría)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ga4_service_account_json", JSON_CREDENCIAL)
    monkeypatch.setattr(settings, "ga4_property_id", "123456789")
    monkeypatch.setattr(ga4_client, "_cargar_credenciales", lambda _: SimpleNamespace())


async def _hacer_superadmin(email: str) -> None:
    async with SessionMaintenance() as session:
        await session.execute(update(User).where(User.email == email).values(is_superadmin=True))
        await session.commit()


async def _hacer_soporte(email: str) -> None:
    async with SessionMaintenance() as session:
        await session.execute(
            update(User).where(User.email == email).values(platform_role="soporte")
        )
        await session.commit()


async def _cabeceras_de(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, rol: str
) -> dict[str, str]:
    if rol == "superadmin":
        await _hacer_superadmin(organizacion.owner_email)
    else:
        await _hacer_soporte(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    return cabeceras


# --- Estados sin datos (200 explícitos, nunca 500) -------------------------


async def test_sin_credencial_responde_no_configurado(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    cabeceras = await _cabeceras_de(cliente, organizacion, "superadmin")

    # El cliente falso está «instalado»: si el endpoint llegara a hablar con
    # Google sin credencial, el recuento lo delataría.
    falsifico = ClienteFalso(_respuesta_con_datos())
    monkeypatch.setattr(ga4_client, "_cliente", falsifico)

    respuesta = await cliente.get(GA4_STATS, headers=cabeceras, params={"dias": 7})

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "no_configurado"
    assert "GA4_SERVICE_ACCOUNT_JSON" in cuerpo["detalle"]
    assert cuerpo["usuarios_activos"] is None
    assert cuerpo["sesiones"] is None
    assert cuerpo["vistas_pagina"] is None
    assert falsifico.llamadas == 0


async def test_sin_property_responde_no_configurado_con_su_mensaje(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    cabeceras = await _cabeceras_de(cliente, organizacion, "superadmin")
    settings = get_settings()
    monkeypatch.setattr(settings, "ga4_service_account_json", JSON_CREDENCIAL)

    respuesta = await cliente.get(GA4_STATS, headers=cabeceras)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "no_configurado"
    assert "GA4_PROPERTY_ID" in cuerpo["detalle"]


async def test_credencial_corrupta_no_fuga_fragmento(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cabeceras = await _cabeceras_de(cliente, organizacion, "superadmin")
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "ga4_service_account_json",
        f'{{"type": "service_account", "{FRAGMENTO_SECRETO}":',
    )
    # Informado: si faltara, el «no configurado» del property ganaría antes
    # de llegar a parsear la credencial.
    monkeypatch.setattr(settings, "ga4_property_id", "123456789")

    with caplog.at_level(logging.WARNING):
        respuesta = await cliente.get(GA4_STATS, headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "credencial_invalida"
    assert FRAGMENTO_SECRETO not in respuesta.text
    assert FRAGMENTO_SECRETO not in cuerpo["detalle"]
    for registro in caplog.records:
        assert FRAGMENTO_SECRETO not in registro.getMessage()


async def test_cuota_agotada_devuelve_estado_y_no_el_error_crudo(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cabeceras = await _cabeceras_de(cliente, organizacion, "superadmin")
    _simular_credencial_valida(monkeypatch)
    falsifico = ClienteFalso(error=ResourceExhausted("CUOTA-BINGO"))
    monkeypatch.setattr(ga4_client, "_cliente", falsifico)

    with caplog.at_level(logging.WARNING):
        respuesta = await cliente.get(GA4_STATS, headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "cuota_agotada"
    assert "CUOTA-BINGO" not in respuesta.text
    for registro in caplog.records:
        assert "CUOTA-BINGO" not in registro.getMessage()


async def test_property_no_encontrado_o_sin_acceso_tienen_detalle_propio(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NotFound (404) y PermissionDenied (403, el caso habitual cuando la
    cuenta de servicio no tiene la propiedad compartida) comparten el detalle
    de despliegue — code-review de la fase 2, M-1."""
    _simular_credencial_valida(monkeypatch)
    cabeceras = await _cabeceras_de(cliente, organizacion, "superadmin")

    for error in (NotFound("PROPERTY-BINGO"), PermissionDenied("PERMISO-BINGO")):
        monkeypatch.setattr(ga4_client, "_cliente", ClienteFalso(error=error))
        respuesta = await cliente.get(GA4_STATS, headers=cabeceras)

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["estado"] == "error_proveedor"
        assert "property ID" in cuerpo["detalle"]
        assert "BINGO" not in respuesta.text


async def test_google_rechaza_la_credencial_no_produce_500(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """RefreshError/TransportError de google.auth NO son GoogleAPIError: la
    primera llamada real refresca el token y sin salida de red, con la clave
    revocada o con el reloj desfasado, la excepción llegaba hasta el 500
    (code-review de la fase 2, I-1.1)."""
    cabeceras = await _cabeceras_de(cliente, organizacion, "superadmin")
    _simular_credencial_valida(monkeypatch)
    falsifico = ClienteFalso(error=RefreshError("AUTH-BINGO"))
    monkeypatch.setattr(ga4_client, "_cliente", falsifico)

    with caplog.at_level(logging.WARNING):
        respuesta = await cliente.get(GA4_STATS, headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "error_proveedor"
    assert "credencial" in cuerpo["detalle"]
    assert "AUTH-BINGO" not in respuesta.text
    for registro in caplog.records:
        assert "AUTH-BINGO" not in registro.getMessage()


async def test_fallo_generico_de_la_api_da_estado_y_no_500(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    cabeceras = await _cabeceras_de(cliente, organizacion, "superadmin")
    _simular_credencial_valida(monkeypatch)
    falsifico = ClienteFalso(error=GoogleAPIError("GENERICO-BINGO"))
    monkeypatch.setattr(ga4_client, "_cliente", falsifico)

    respuesta = await cliente.get(GA4_STATS, headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "error_proveedor"
    assert "GENERICO-BINGO" not in respuesta.text


async def test_respuesta_con_metricas_incompletas_no_produce_500(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una fila con menos métricas que las pedidas es un contrato roto del
    proveedor, no una razón para romper el panel (code-review fase 2, I-1.3):
    el mapeo de la respuesta va dentro del try que traduce a estado."""
    cabeceras = await _cabeceras_de(cliente, organizacion, "superadmin")
    _simular_credencial_valida(monkeypatch)
    corta = SimpleNamespace(rows=[SimpleNamespace(metric_values=[SimpleNamespace(value="12")])])
    monkeypatch.setattr(ga4_client, "_cliente", ClienteFalso(corta))

    respuesta = await cliente.get(GA4_STATS, headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "error_proveedor"


# --- Caso feliz -------------------------------------------------------------


async def test_reporte_con_datos_y_dias_validos(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    cabeceras = await _cabeceras_de(cliente, organizacion, "superadmin")
    _simular_credencial_valida(monkeypatch)
    falsifico = ClienteFalso(_respuesta_con_datos())
    monkeypatch.setattr(ga4_client, "_cliente", falsifico)

    respuesta = await cliente.get(GA4_STATS, headers=cabeceras, params={"dias": 30})

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {
        "estado": "datos",
        "detalle": None,
        "usuarios_activos": 12,
        "sesiones": 34,
        "vistas_pagina": 56,
    }
    assert falsifico.llamadas == 1


async def test_sin_trafico_responde_ceros_no_error(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un rango sin visitas devuelve filas vacías de GA4: son ceros, no un
    estado de error (un evento pequeño con 0 visitas es información útil)."""
    cabeceras = await _cabeceras_de(cliente, organizacion, "superadmin")
    _simular_credencial_valida(monkeypatch)
    monkeypatch.setattr(ga4_client, "_cliente", ClienteFalso(respuesta=SimpleNamespace(rows=[])))

    respuesta = await cliente.get(GA4_STATS, headers=cabeceras)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "datos"
    assert cuerpo["usuarios_activos"] == 0
    assert cuerpo["sesiones"] == 0
    assert cuerpo["vistas_pagina"] == 0


# --- Caché en Redis ----------------------------------------------------------


async def test_segunda_peticion_sale_de_la_cache(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    cabeceras = await _cabeceras_de(cliente, organizacion, "superadmin")
    _simular_credencial_valida(monkeypatch)
    falsifico = ClienteFalso(_respuesta_con_datos())
    monkeypatch.setattr(ga4_client, "_cliente", falsifico)

    primera = await cliente.get(GA4_STATS, headers=cabeceras)
    assert primera.status_code == 200
    assert primera.json()["usuarios_activos"] == 12

    # Si se consultara de nuevo, el informe daría ceros: si la respuesta
    # sigue siendo 12, ha venido de la caché.
    falsifico.respuesta = SimpleNamespace(rows=[])
    segunda = await cliente.get(GA4_STATS, headers=cabeceras)

    assert segunda.status_code == 200
    assert segunda.json()["usuarios_activos"] == 12
    assert falsifico.llamadas == 1


async def test_cache_corrupta_cuenta_como_miss(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un valor que ya no valida en la clave (esquema anterior de un
    despliegue previo, dato corrupto) no debe romper el panel con un 500:
    se reconsulta la API (code-review de la fase 2, I-1.4)."""
    cabeceras = await _cabeceras_de(cliente, organizacion, "superadmin")
    _simular_credencial_valida(monkeypatch)
    falsifico = ClienteFalso(_respuesta_con_datos())
    monkeypatch.setattr(ga4_client, "_cliente", falsifico)
    await get_redis().set("ga4_stats:30", "{no-es-json-corrupto")

    respuesta = await cliente.get(GA4_STATS, headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "datos"
    assert cuerpo["usuarios_activos"] == 12
    assert falsifico.llamadas == 1


# --- Autorización y validación ----------------------------------------------


async def test_sin_sesion_y_dias_invalido(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    assert (await cliente.get(GA4_STATS)).status_code == 401

    cabeceras = await _cabeceras_de(cliente, organizacion, "superadmin")
    assert (await cliente.get(GA4_STATS, headers=cabeceras, params={"dias": 15})).status_code == 422
    assert (await cliente.get(GA4_STATS, headers=cabeceras, params={"dias": 0})).status_code == 422


async def test_soporte_puede_leer_estadisticas(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    cabeceras = await _cabeceras_de(cliente, organizacion, "soporte")
    _simular_credencial_valida(monkeypatch)
    monkeypatch.setattr(ga4_client, "_cliente", ClienteFalso(_respuesta_con_datos()))

    respuesta = await cliente.get(GA4_STATS, headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "datos"
