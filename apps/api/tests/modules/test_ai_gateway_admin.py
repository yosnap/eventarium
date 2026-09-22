"""Nivel plataforma de la pasarela de IA: configuración, servicios y privilegios."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionApp, SessionMaintenance
from app.modules.ai_gateway import servicios
from app.modules.ai_gateway.models import PlatformAiSettings
from tests.ai_gateway_test_helpers import CLAVE_DE_PROVEEDOR, cabeceras_de_superadmin
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

AJUSTES = "/api/v1/admin/ai-settings"
SERVICIOS = "/api/v1/admin/services"


@pytest.fixture(autouse=True)
def _sin_red_al_guardar(validacion_en_vivo_sin_red: None) -> None:
    """Todo este módulo guarda configuración (`PUT {AJUSTES}`), que desde
    `service._validar_modelo_en_vivo` consulta el listado real del proveedor
    — ver el docstring de `validacion_en_vivo_sin_red`."""

CONFIG_NAN = {
    "provider": "nan_builders",
    "default_model": "deepseek-v4-flash",
    "api_key": CLAVE_DE_PROVEEDOR,
    "monthly_ceiling_usd": "50.000000",
}


async def _fila_de_plataforma() -> PlatformAiSettings | None:
    async with SessionMaintenance() as session:
        return await session.scalar(select(PlatformAiSettings))


async def test_el_admin_guarda_la_configuracion_y_el_get_no_devuelve_la_clave(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)

    guardado = await cliente.put(AJUSTES, headers=cabeceras, json=CONFIG_NAN)
    assert guardado.status_code == 200, guardado.text

    leido = await cliente.get(AJUSTES, headers=cabeceras)
    assert leido.status_code == 200
    cuerpo = leido.json()
    assert cuerpo["provider"] == "nan_builders"
    assert cuerpo["default_model"] == "deepseek-v4-flash"
    assert cuerpo["has_key"] is True
    assert cuerpo["api_key_hint"] == CLAVE_DE_PROVEEDOR[-4:]
    # La base URL se muestra como informativa y no editable: sale del catálogo.
    assert cuerpo["api_base"] == "https://api.nan.builders/v1"
    assert cuerpo["api_base_editable"] is False
    assert "api_key" not in cuerpo
    assert CLAVE_DE_PROVEEDOR not in leido.text


async def test_la_clave_se_guarda_cifrada_y_el_api_base_queda_nulo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    await cliente.put(AJUSTES, headers=cabeceras, json=CONFIG_NAN)

    fila = await _fila_de_plataforma()
    assert fila is not None
    assert fila.api_key_encrypted is not None
    assert CLAVE_DE_PROVEEDOR not in fila.api_key_encrypted
    # Si el proveedor cambiara de base URL se cambia en el catálogo, no aquí.
    assert fila.api_base is None


async def test_un_owner_sin_superadmin_recibe_403(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Ser propietario de una organización no da acceso al nivel plataforma."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    assert (await cliente.get(AJUSTES, headers=cabeceras)).status_code == 403
    assert (await cliente.get(SERVICIOS, headers=cabeceras)).status_code == 403
    assert (await cliente.put(AJUSTES, headers=cabeceras, json=CONFIG_NAN)).status_code == 403


@pytest.mark.parametrize(
    ("cuerpo", "codigo"),
    [
        (
            {"provider": "inventado", "default_model": "x", "api_key": CLAVE_DE_PROVEEDOR},
            "proveedor_desconocido",
        ),
        (
            {
                "provider": "nan_builders",
                "default_model": "no-existe",
                "api_key": CLAVE_DE_PROVEEDOR,
            },
            "modelo_desconocido",
        ),
        (
            {
                "provider": "nan_builders",
                "default_model": "deepseek-v4-flash",
                "api_base": "https://mi-host-malicioso.example/v1",
                "api_key": CLAVE_DE_PROVEEDOR,
            },
            "api_base_no_permitido",
        ),
        (
            {"provider": "custom", "default_model": "mi-modelo", "api_key": CLAVE_DE_PROVEEDOR},
            "api_base_requerido",
        ),
        (
            {"provider": "nan_builders", "default_model": "deepseek-v4-flash"},
            "clave_requerida",
        ),
        ({"api_key": CLAVE_DE_PROVEEDOR}, "proveedor_requerido"),
    ],
)
async def test_las_reglas_del_put_dan_422_con_su_codigo(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    cuerpo: dict[str, object],
    codigo: str,
) -> None:
    """Nunca un 500 ni un error de integridad: siempre un 422 con motivo."""
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)

    respuesta = await cliente.put(AJUSTES, headers=cabeceras, json=cuerpo)
    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == codigo

    fila = await _fila_de_plataforma()
    assert fila is None or fila.api_key_encrypted is None


async def test_un_api_base_personalizado_interno_se_rechaza(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    respuesta = await cliente.put(
        AJUSTES,
        headers=cabeceras,
        json={
            "provider": "custom",
            "default_model": "mi-modelo",
            "api_base": "https://10.0.0.5/v1",
            "api_key": CLAVE_DE_PROVEEDOR,
        },
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "api_base_invalido"
    fila = await _fila_de_plataforma()
    assert fila is None or fila.api_key_encrypted is None


async def test_sin_clave_de_cifrado_el_put_falla_con_error_de_dominio(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, sin_cifrado: None
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    respuesta = await cliente.put(AJUSTES, headers=cabeceras, json=CONFIG_NAN)
    assert respuesta.status_code == 503, respuesta.text
    assert respuesta.json()["code"] == "cifrado_no_configurado"


async def test_el_techo_se_puede_fijar_sin_credenciales(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    respuesta = await cliente.put(
        AJUSTES, headers=cabeceras, json={"monthly_ceiling_usd": "12.500000"}
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["monthly_ceiling_usd"] == "12.500000"
    assert cuerpo["has_key"] is False


async def test_los_interruptores_globales_se_leen_y_se_cambian(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)

    inicial = await cliente.get(SERVICIOS, headers=cabeceras)
    assert inicial.status_code == 200
    assert {s["service_key"]: s["enabled"] for s in inicial.json()} == {"ai": True}

    apagado = await cliente.put(
        SERVICIOS, headers=cabeceras, json={"services": [{"service_key": "ai", "enabled": False}]}
    )
    assert apagado.status_code == 200
    assert apagado.json()[0]["enabled"] is False


async def test_un_service_key_desconocido_da_422(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    respuesta = await cliente.put(
        SERVICIOS,
        headers=cabeceras,
        json={"services": [{"service_key": "inventado", "enabled": False}]},
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "service_key_desconocido"


async def test_el_override_de_organizacion_lo_escribe_el_admin(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    url = f"/api/v1/admin/organizations/{organizacion.id}/services"

    forzado = await cliente.put(
        url, headers=cabeceras, json={"services": [{"service_key": "ai", "enabled": False}]}
    )
    assert forzado.status_code == 200, forzado.text
    estado = forzado.json()[0]
    assert estado["global_enabled"] is True
    assert estado["overridden_off"] is True
    assert estado["enabled"] is False

    heredando = await cliente.put(
        url, headers=cabeceras, json={"services": [{"service_key": "ai", "enabled": True}]}
    )
    assert heredando.json()[0] == {
        "service_key": "ai",
        "etiqueta": estado["etiqueta"],
        "global_enabled": True,
        "overridden_off": False,
        "enabled": True,
    }


async def test_el_apagado_global_manda_sobre_el_override(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """«Volver a heredar» no enciende nada si el global está apagado."""
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    await cliente.put(
        SERVICIOS, headers=cabeceras, json={"services": [{"service_key": "ai", "enabled": False}]}
    )
    respuesta = await cliente.put(
        f"/api/v1/admin/organizations/{organizacion.id}/services",
        headers=cabeceras,
        json={"services": [{"service_key": "ai", "enabled": True}]},
    )
    assert respuesta.json()[0]["enabled"] is False


async def test_todo_servicio_del_catalogo_esta_sembrado_en_la_base_de_datos() -> None:
    """Añadir una clave al catálogo de código exige migración que la siembre.

    `organization_services.service_key` tiene FK contra `platform_services`:
    una clave solo en código haría reventar la FK al forzarla a apagado. Esto
    falla aquí, en integración continua, y no en producción.
    """
    async with SessionMaintenance() as session:
        filas = await session.execute(text("SELECT service_key FROM platform_services"))
        sembradas = {fila[0] for fila in filas}
    assert set(servicios.CLAVES_DE_SERVICIO) <= sembradas


async def test_forzar_a_apagado_un_servicio_sin_fila_global_no_revienta_la_fk(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red de seguridad del desfase catálogo ↔ `platform_services`.

    Simula una clave añadida al catálogo sin migración que la siembre: el
    `PUT` debe funcionar (sembrando la fila global activa), no dar un 500 por
    `IntegrityError`.
    """
    monkeypatch.setitem(
        servicios.SERVICIOS,
        "servicio_sin_sembrar",
        servicios.Servicio(
            clave="servicio_sin_sembrar", etiqueta="Sin sembrar", descripcion="Solo en código."
        ),
    )
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)

    respuesta = await cliente.put(
        f"/api/v1/admin/organizations/{organizacion.id}/services",
        headers=cabeceras,
        json={"services": [{"service_key": "servicio_sin_sembrar", "enabled": False}]},
    )
    assert respuesta.status_code == 200, respuesta.text
    estado = {fila["service_key"]: fila for fila in respuesta.json()}["servicio_sin_sembrar"]
    assert estado["global_enabled"] is True
    assert estado["enabled"] is False

    async with SessionMaintenance() as session:
        filas = await session.execute(text("SELECT service_key FROM platform_services"))
        assert "servicio_sin_sembrar" in {fila[0] for fila in filas}


async def test_app_user_solo_tiene_select_sobre_las_tablas_de_plataforma(
    app_db: AsyncSession,
) -> None:
    """V-2: `REVOKE ALL` + `GRANT SELECT` sobre las tablas de instalación.

    Sin el `REVOKE`, `ALTER DEFAULT PRIVILEGES` (`infra/postgres/sql/roles.sql`)
    dejaría a `app_user` leer, sobrescribir y **borrar** la clave de
    plataforma y los interruptores globales.
    """
    for tabla in ("platform_ai_settings", "platform_services"):
        for privilegio, esperado in (
            ("SELECT", True),
            ("INSERT", False),
            ("UPDATE", False),
            ("DELETE", False),
        ):
            concedido = await app_db.scalar(
                text("SELECT has_table_privilege('app_user', :tabla, :privilegio)"),
                {"tabla": tabla, "privilegio": privilegio},
            )
            assert concedido is esperado, f"{tabla}.{privilegio}"


@pytest.mark.parametrize(
    "sentencia",
    [
        "INSERT INTO platform_ai_settings (id) VALUES (1)",
        "UPDATE platform_ai_settings SET api_key_encrypted = 'x'",
        "DELETE FROM platform_ai_settings",
        "UPDATE platform_services SET enabled = false",
        "DELETE FROM platform_services",
    ],
)
async def test_una_sesion_de_organizacion_no_puede_escribir_las_tablas_de_plataforma(
    sentencia: str,
) -> None:
    """La otra cara del test anterior: la escritura falla de verdad.

    Una sesión por sentencia: el error deja la transacción abortada, así que
    no se pueden encadenar dentro de la misma."""
    async with SessionApp() as session, session.begin():
        with pytest.raises(ProgrammingError):
            await session.execute(text(sentencia))


async def test_una_sesion_de_organizacion_si_puede_leer_la_config_de_plataforma(
    app_db: AsyncSession,
) -> None:
    """V-3/V-4: la organización heredera y el worker la leen en su **propia**
    sesión, sin abrir una segunda con el rol de mantenimiento."""
    await app_db.execute(text("SELECT api_key_encrypted FROM platform_ai_settings"))
    await app_db.execute(text("SELECT enabled FROM platform_services"))
