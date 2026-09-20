"""Batería transversal de seguridad del plan de cookies y analítica externa
(fase 5 del plan `260916-2246-cookies-analitica-externa`).

Atraviesa las fases 1-4 en lo que toca a exposición y permisos: la
credencial de la API de Datos de GA4 no sale por ninguna respuesta, el
agregado de consentimientos no permite reconstruir una fila individual,
`soporte` lee pero no escribe, y una sesión de suplantación no alcanza
ningún endpoint del plan.
"""

from __future__ import annotations

import pytest
from google.api_core.exceptions import GoogleAPIError
from httpx import AsyncClient
from sqlalchemy import text, update

from app.core.config import get_settings
from app.core.database import SessionMaintenance
from app.core.permissions import Permission
from app.modules.admin import ga4_client
from app.modules.users.models import User
from tests.conftest import (
    OrganizacionDePrueba,
    crear_miembro,
    crear_rol,
    iniciar_sesion,
)

SETTINGS = "/api/v1/admin/analytics-settings"
STATS = "/api/v1/admin/cookie-consents/stats"
GA4 = "/api/v1/admin/analytics-providers/ga4-stats"
IMPERSONATE = "/api/v1/admin/impersonate"

# Marcadores que NO pueden aparecer en ninguna respuesta: en la credencial
# representan el secreto de entrada; en el error simulado del proveedor, lo
# crudo de Google.
FRAGMENTO_CREDENCIAL = "PRIVATE-KEY-BINGO"
FRAGMENTO_ERROR = "MENSAJE-CRUDO-BINGO"
JSON_CREDENCIAL = (
    '{"type": "service_account", "project_id": "prueba", '
    f'"private_key": "{FRAGMENTO_CREDENCIAL}", "client_email": "lector@prueba.iam"}}'
)


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


async def _sembrar_consentimiento(categorias: list[str]) -> None:
    from app.modules.legal.models import CookieConsent

    async with SessionMaintenance() as session:
        session.add(CookieConsent(categories_accepted=categorias))
        await session.commit()


def _credencial_con_property(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ga4_service_account_json", JSON_CREDENCIAL)
    monkeypatch.setattr(settings, "ga4_property_id", "123456789")
    # La carga real fallaría con la clave de prueba: se sustituye por un
    # objeto cualquiera; lo que se prueba aquí es el camino de error y de
    # respuesta, no la criptografía. El cliente gRPC lo monta cada test
    # (con datos o con el error crudo que quiera provocar).
    monkeypatch.setattr(ga4_client, "_cargar_credenciales", lambda _: object())


@pytest.fixture(autouse=True)
async def _restaurar_settings_tras_cada_test() -> None:
    """La fila única de `platform_analytics_settings` no está en el truncado
    global del conftest: los tests que escriben en ella la dejan limpia, como
    la siembra `0041` (mismo patrón que `test_analytics_settings.py`)."""
    yield
    async with SessionMaintenance() as session:
        await session.execute(
            text(
                "UPDATE platform_analytics_settings SET ga4_measurement_id = null, "
                "meta_pixel_id = null, cloudflare_analytics_token = null"
            )
        )
        await session.commit()


# --- La credencial de GA4 no sale por ninguna respuesta ---------------------


async def test_la_credencial_no_aparece_en_ninguna_respuesta(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _credencial_con_property(monkeypatch)

    async def run_report(*_a: object, **_k: object) -> object:
        # El proveedor falla con su mensaje crudo (lo que en la vida real
        # puede ecoar detalles internos de Google).
        raise GoogleAPIError(FRAGMENTO_ERROR)

    monkeypatch.setattr(
        ga4_client, "_cliente", type("Roto", (), {"run_report": staticmethod(run_report)})
    )

    await _hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    stats_ga4 = await cliente.get(GA4, headers=cabeceras)
    assert stats_ga4.status_code == 200, stats_ga4.text
    assert stats_ga4.json()["estado"] == "error_proveedor"
    assert FRAGMENTO_ERROR not in stats_ga4.text
    assert FRAGMENTO_CREDENCIAL not in stats_ga4.text

    ajustes = await cliente.get(SETTINGS, headers=cabeceras)
    assert ajustes.status_code == 200
    assert FRAGMENTO_CREDENCIAL not in ajustes.text

    escritura = await cliente.put(
        SETTINGS,
        headers=cabeceras,
        json={
            "ga4_measurement_id": "G-NUEVO",
            "meta_pixel_id": None,
            "cloudflare_analytics_token": None,
        },
    )
    assert escritura.status_code == 200
    assert FRAGMENTO_CREDENCIAL not in escritura.text


# --- El agregado no permite reconstruir filas individuales ------------------


async def test_el_agregado_solo_devuelve_celdas_semana_categoria_total(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _sembrar_consentimiento(["necessary", "analytics"])

    await _hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.get(STATS, headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    for celda in respuesta.json()["celdas"]:
        # Ni id de consentimiento, ni timestamp exacto, ni IP: solo la celda
        # semanal agregada.
        assert set(celda) == {"semana", "categoria", "total"}
    # Ningún UUID (id de fila de cookie_consents) en el cuerpo entero.
    cuerpo = respuesta.text
    for fragmento in ("id", "created_at", "ip_address", "user_agent"):
        assert f'"{fragmento}"' not in cuerpo


# --- soporte: lectura sin escritura ------------------------------------------


async def test_soporte_lee_configuracion_agregados_y_estadisticas_y_no_escribe(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _hacer_soporte(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    assert (await cliente.get(SETTINGS, headers=cabeceras)).status_code == 200
    assert (await cliente.get(STATS, headers=cabeceras)).status_code == 200

    _credencial_con_property(monkeypatch)
    datos_ga4 = await cliente.get(GA4, headers=cabeceras)
    assert datos_ga4.status_code == 200, datos_ga4.text
    assert FRAGMENTO_CREDENCIAL not in datos_ga4.text

    escritura = await cliente.put(
        SETTINGS,
        headers=cabeceras,
        json={
            "ga4_measurement_id": None,
            "meta_pixel_id": None,
            "cloudflare_analytics_token": None,
        },
    )
    assert escritura.status_code == 403


# --- La suplantación no alcanza ningún endpoint del plan ---------------------


async def test_una_sesion_de_suplantacion_no_alcanza_ningun_endpoint_del_plan(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _hacer_superadmin(organizacion.owner_email)
    await crear_rol(organizacion, key="organizador_plano", permisos=[Permission.EVENTS_READ])
    persona = await crear_miembro(organizacion, "organizador_plano")
    _, cabeceras_admin = await iniciar_sesion(cliente, organizacion)

    suplantacion = await cliente.post(
        IMPERSONATE,
        headers=cabeceras_admin,
        json={
            "user_id": str(persona.user_id),
            "organization_id": str(organizacion.id),
            "reason": "Ver la analítica que no le toca",
            "password": organizacion.owner_password,
        },
    )
    assert suplantacion.status_code == 201, suplantacion.text
    cabeceras_suplantado = {"Authorization": f"Bearer {suplantacion.json()['access_token']}"}

    # El gate mira el claim de suplantación, no la fila: incluso dándole el
    # rol `soporte` a la cuenta suplantada, ningún endpoint del plan pasa.
    async with SessionMaintenance() as session:
        await session.execute(
            update(User).where(User.id == persona.user_id).values(platform_role="soporte")
        )
        await session.commit()

    for metodo, url, json_ in (
        ("GET", SETTINGS, None),
        ("GET", STATS, None),
        ("GET", GA4, None),
        (
            "PUT",
            SETTINGS,
            {"ga4_measurement_id": None, "meta_pixel_id": None, "cloudflare_analytics_token": None},
        ),
    ):
        if metodo == "GET":
            respuesta = await cliente.get(url, headers=cabeceras_suplantado)
        else:
            respuesta = await cliente.put(url, headers=cabeceras_suplantado, json=json_)
        assert respuesta.status_code == 403, (metodo, url, respuesta.text)
