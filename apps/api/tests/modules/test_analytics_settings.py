"""Analítica externa de plataforma: configuración de proveedores y agregados
de consentimientos (fase 1 del plan `260916-2246-cookies-analitica-externa`).

Lo que se fija aquí: `soporte` lee (config y agregados) pero nunca escribe la
configuración; el `PUT` de `superadmin` queda auditado; el agregado es
semanal × categoría con supresión de celdas por debajo del umbral (nunca una
fila individual ni un identificador de visita en la respuesta); y los
identificadores son legibles públicamente en `/tenant/analytics` — es el
mismo nivel de exposición que el HTML que cargaría los scripts.
"""

from __future__ import annotations

import pytest
from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select, text, update

from app.core.database import SessionMaintenance
from app.modules.legal.models import CookieConsent
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

ADMIN_SETTINGS = "/api/v1/admin/analytics-settings"
ADMIN_STATS = "/api/v1/admin/cookie-consents/stats"
PUBLICO = "/api/v1/tenant/analytics"


async def _hacer_superadmin(email: str) -> None:
    async with SessionMaintenance() as session:
        await session.execute(
            update(User).where(User.email == email).values(is_superadmin=True)
        )
        await session.commit()


async def _hacer_soporte(email: str) -> None:
    async with SessionMaintenance() as session:
        await session.execute(
            update(User).where(User.email == email).values(platform_role="soporte")
        )
        await session.commit()


async def _superadmin_headers(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> dict[str, str]:
    await _hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    return cabeceras


async def _soporte_headers(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> dict[str, str]:
    await _hacer_soporte(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    return cabeceras


async def _sembrar_consentimiento(dia: datetime, categorias: list[str]) -> None:
    async with SessionMaintenance() as session:
        session.add(CookieConsent(categories_accepted=categorias, created_at=dia))
        await session.commit()


async def _restaurar_settings() -> None:
    """Deja la fila única sin identificadores, como la siembra `0041` (la
    tabla no está en el truncado global del conftest)."""
    async with SessionMaintenance() as session:
        await session.execute(
            text(
                "UPDATE platform_analytics_settings SET ga4_measurement_id = null, "
                "meta_pixel_id = null, cloudflare_analytics_token = null"
            )
        )
        await session.commit()


@pytest.fixture(autouse=True)
async def _limpiar_settings_tras_cada_test() -> None:
    yield
    await _restaurar_settings()


# --- Configuración de proveedores -----------------------------------------


async def test_superadmin_lee_y_escribe_la_configuracion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)

    vacia = await cliente.get(ADMIN_SETTINGS, headers=cabeceras)
    assert vacia.status_code == 200
    assert vacia.json() == {
        "ga4_measurement_id": None,
        "meta_pixel_id": None,
        "cloudflare_analytics_token": None,
    }

    escritura = await cliente.put(
        ADMIN_SETTINGS,
        headers=cabeceras,
        json={
            "ga4_measurement_id": "G-TEST123",
            "meta_pixel_id": "1234567890",
            "cloudflare_analytics_token": "abc123",
        },
    )
    assert escritura.status_code == 200, escritura.text
    assert escritura.json()["ga4_measurement_id"] == "G-TEST123"

    # El `PUT` queda en la auditoría de la instalación.
    async with SessionMaintenance() as session:
        acciones = (
            await session.execute(
                text(
                    "SELECT action FROM audit_log "
                    "WHERE action = 'platform.analytics_settings.update'"
                )
            )
        ).all()
    assert len(acciones) == 1


async def test_soporte_lee_pero_no_escribe(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _soporte_headers(cliente, organizacion)

    assert (await cliente.get(ADMIN_SETTINGS, headers=cabeceras)).status_code == 200
    escritura = await cliente.put(
        ADMIN_SETTINGS,
        headers=cabeceras,
        json={"ga4_measurement_id": "G-HACK", "meta_pixel_id": None, "cloudflare_analytics_token": None},
    )
    assert escritura.status_code == 403


async def test_sin_sesion_no_hay_nada(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    assert (await cliente.get(ADMIN_SETTINGS)).status_code == 401
    assert (await cliente.get(ADMIN_STATS)).status_code == 401
    assert (
        await cliente.put(
            ADMIN_SETTINGS,
            json={"ga4_measurement_id": None, "meta_pixel_id": None, "cloudflare_analytics_token": None},
        )
    ).status_code == 401


# --- Agregados de consentimientos ------------------------------------------


async def test_agregado_semanal_por_categoria_con_supresion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)

    hoy = datetime.now(UTC)
    lunes = hoy - timedelta(days=hoy.weekday())
    semana_pasada = lunes - timedelta(days=7)
    # Semana actual: 6 consentimientos con `analytics` (celda completa), 2 de
    # ellos solo con `marketing` (celda suprimida) y `necessary` acumula los 8.
    for _ in range(6):
        await _sembrar_consentimiento(lunes, ["necessary", "analytics"])
    for _ in range(2):
        await _sembrar_consentimiento(lunes + timedelta(hours=1), ["necessary", "marketing"])
    # Semana pasada: un único consentimiento → todas sus celdas se suprimen.
    await _sembrar_consentimiento(semana_pasada, ["necessary", "marketing"])

    respuesta = await cliente.get(
        ADMIN_STATS, headers=cabeceras, params={"desde": semana_pasada.date().isoformat()}
    )
    assert respuesta.status_code == 200, respuesta.text

    cuerpo = respuesta.json()
    assert set(cuerpo) == {"celdas"}  # nunca filas individuales ni ids
    celdas = {
        (celda["semana"], celda["categoria"]): celda["total"] for celda in cuerpo["celdas"]
    }

    semana_actual = lunes.date().isoformat()
    assert celdas[(semana_actual, "necessary")] == 8
    assert celdas[(semana_actual, "analytics")] == 6
    assert celdas[(semana_actual, "marketing")] is None  # 2 < umbral → suprimida

    # La semana con un solo consentimiento: suprimida (no expone el «1»).
    assert celdas[(semana_pasada.date().isoformat(), "necessary")] is None
    assert celdas[(semana_pasada.date().isoformat(), "marketing")] is None


async def test_rango_invalido_se_rechaza_con_422(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)

    rango_largo = await cliente.get(
        ADMIN_STATS,
        headers=cabeceras,
        params={"desde": "2020-01-01", "hasta": "2026-12-31"},
    )
    assert rango_largo.status_code == 422

    invertido = await cliente.get(
        ADMIN_STATS,
        headers=cabeceras,
        params={"desde": "2026-06-01", "hasta": "2026-05-01"},
    )
    assert invertido.status_code == 422


# --- Endpoint público de identificadores -----------------------------------


async def test_identificadores_publicos_sin_sesion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    await cliente.put(
        ADMIN_SETTINGS,
        headers=cabeceras,
        json={
            "ga4_measurement_id": "G-PUB123",
            "meta_pixel_id": None,
            "cloudflare_analytics_token": "tok-publico",
        },
    )

    respuesta = await cliente.get(PUBLICO)  # sin cabeceras de sesión
    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "ga4_measurement_id": "G-PUB123",
        "meta_pixel_id": None,
        "cloudflare_analytics_token": "tok-publico",
    }
