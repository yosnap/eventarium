"""Proveedor de correo de la plataforma: panel del admin y envío real."""

from __future__ import annotations

import asyncio
import socket
import ssl
from typing import Any
from unittest.mock import AsyncMock, patch

import aiosmtplib
import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core import email
from app.core.audit import AuditLog
from app.core.config import get_settings
from app.core.database import SessionMaintenance
from app.core.email import (
    configuracion_de_entorno,
    configuracion_efectiva,
    invalidar_configuracion_en_cache,
    parametros_tls,
)
from app.modules.email_settings import presets
from app.modules.email_settings.models import PlatformEmailSettings
from tests.ai_gateway_test_helpers import cabeceras_de_superadmin
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

AJUSTES = "/api/v1/admin/email-settings"
PRUEBA = "/api/v1/admin/email-settings/test"
API_KEY = "re_clave_de_prueba_ABCD1234"
RESEND = {"provider": "resend", "password": API_KEY, "from_address": "hola@eventarium.org"}


async def _fila() -> PlatformEmailSettings | None:
    async with SessionMaintenance() as session:
        return await session.scalar(select(PlatformEmailSettings))


# --- Reglas puras -------------------------------------------------------------


@pytest.mark.parametrize(
    ("modo", "esperado"),
    [
        ("implicit", {"use_tls": True, "start_tls": False}),
        ("starttls", {"use_tls": False, "start_tls": True}),
        ("none", {"use_tls": False, "start_tls": None}),
    ],
)
def test_parametros_tls_nunca_combinan_tls_implicito_y_starttls(
    modo: presets.ModoTls, esperado: dict[str, Any]
) -> None:
    assert parametros_tls(modo) == esperado


def test_el_respaldo_de_entorno_con_587_usa_starttls_y_no_tls_implicito(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La combinación que tumbó el correo de producción el 25-sep."""
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USE_TLS", "true")
    get_settings.cache_clear()
    try:
        assert configuracion_de_entorno().tls_mode == "starttls"
        monkeypatch.setenv("SMTP_PORT", "465")
        get_settings.cache_clear()
        assert configuracion_de_entorno().tls_mode == "implicit"
    finally:
        get_settings.cache_clear()


def test_none_solo_en_custom_y_fuera_de_produccion() -> None:
    assert presets.resolver_tls("custom", 1025, "none", es_produccion=False) == "none"
    with pytest.raises(presets.ConfiguracionDeCorreoInvalida):
        presets.resolver_tls("custom", 1025, "none", es_produccion=True)
    with pytest.raises(presets.ConfiguracionDeCorreoInvalida):
        presets.resolver_tls("resend", 587, "none", es_produccion=False)


async def test_en_produccion_se_rechazan_puertos_de_desarrollo_y_hosts_internos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(presets.ConfiguracionDeCorreoInvalida):
        presets.validar_puerto(6379, es_produccion=False)
    with pytest.raises(presets.ConfiguracionDeCorreoInvalida):
        presets.validar_puerto(1025, es_produccion=True)

    respuesta = [("172.22.0.5", 0)]

    async def _resolver(_: Any, *__: Any, **___: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", r) for r in respuesta]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", _resolver)
    with pytest.raises(presets.ConfiguracionDeCorreoInvalida):
        await presets.validar_host("redis", es_produccion=True)
    await presets.validar_host("redis", es_produccion=False)

    # Una IP con zona IPv6 no se interpreta: cuenta como insegura, no da 500.
    respuesta[:] = [("fe80::1%eth0", 0, 0, 0)]
    with pytest.raises(presets.ConfiguracionDeCorreoInvalida):
        await presets.validar_host("raro", es_produccion=True)


def test_ses_solo_acepta_regiones_del_catalogo() -> None:
    assert presets.host_de_ses("eu-west-1") == "email-smtp.eu-west-1.amazonaws.com"
    with pytest.raises(presets.ConfiguracionDeCorreoInvalida):
        presets.host_de_ses("169.254.169.254")


# --- Panel del admin ----------------------------------------------------------


async def test_sin_fila_el_get_describe_el_entorno_sin_secretos(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    respuesta = await cliente.get(AJUSTES, headers=cabeceras)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["source"] == "environment"
    assert cuerpo["password_hint"] is None
    assert {p["provider"] for p in cuerpo["presets"]} == {"resend", "acumbamail", "ses", "custom"}


async def test_el_admin_guarda_resend_cifrado_y_el_get_no_devuelve_la_clave(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    guardado = await cliente.put(AJUSTES, headers=cabeceras, json=RESEND)
    assert guardado.status_code == 200, guardado.text

    leido = await cliente.get(AJUSTES, headers=cabeceras)
    cuerpo = leido.json()
    assert cuerpo["source"] == "database"
    assert (cuerpo["host"], cuerpo["port"], cuerpo["tls_mode"]) == (
        "smtp.resend.com",
        465,
        "implicit",
    )
    assert cuerpo["username"] == "resend"
    assert cuerpo["has_password"] is True
    assert cuerpo["password_hint"] == API_KEY[-4:]
    assert API_KEY not in leido.text

    fila = await _fila()
    assert fila is not None
    assert API_KEY not in fila.password_encrypted

    async with SessionMaintenance() as session:
        acciones = (await session.scalars(select(AuditLog.action))).all()
    assert "platform_email_settings.updated" in acciones


async def test_un_owner_sin_superadmin_recibe_403(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    assert (await cliente.get(AJUSTES, headers=cabeceras)).status_code == 403
    assert (await cliente.put(AJUSTES, headers=cabeceras, json=RESEND)).status_code == 403
    assert (await cliente.post(PRUEBA, headers=cabeceras, json=RESEND)).status_code == 403
    assert await _fila() is None


async def test_sin_clave_de_cifrado_no_se_guarda_nada(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, sin_cifrado: None
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    respuesta = await cliente.put(AJUSTES, headers=cabeceras, json=RESEND)
    assert respuesta.status_code == 503
    assert await _fila() is None


async def test_la_contrasena_omitida_solo_se_reutiliza_con_el_mismo_proveedor(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    await cliente.put(AJUSTES, headers=cabeceras, json=RESEND)

    sin_clave = {k: v for k, v in RESEND.items() if k != "password"}
    mismo = await cliente.put(AJUSTES, headers=cabeceras, json=sin_clave)
    assert mismo.status_code == 200, mismo.text

    otro = await cliente.put(
        AJUSTES,
        headers=cabeceras,
        json={**sin_clave, "provider": "acumbamail", "username": "cuenta@eventarium.org"},
    )
    assert otro.status_code == 422
    fila = await _fila()
    assert fila is not None and fila.provider == "resend"


async def test_el_delete_vuelve_al_entorno(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    await cliente.put(AJUSTES, headers=cabeceras, json=RESEND)
    assert (await cliente.delete(AJUSTES, headers=cabeceras)).status_code == 204
    assert await _fila() is None
    assert (await cliente.get(AJUSTES, headers=cabeceras)).json()["source"] == "environment"


async def test_la_tabla_es_de_solo_lectura_para_app_user() -> None:
    async with SessionMaintenance() as session:
        permisos = (
            await session.execute(
                text(
                    "SELECT has_table_privilege('app_user', 'platform_email_settings', 'SELECT'),"
                    " has_table_privilege('app_user', 'platform_email_settings', 'INSERT')"
                )
            )
        ).one()
    assert tuple(permisos) == (True, False)


# --- Prueba de envío ----------------------------------------------------------


async def test_la_prueba_va_siempre_al_superadmin_y_no_guarda(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    with patch("app.core.email.aiosmtplib.send", new=AsyncMock()) as enviar:
        respuesta = await cliente.post(PRUEBA, headers=cabeceras, json=RESEND)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"ok": True, "sent_to": organizacion.owner_email, "motivo": None}
    mensaje = enviar.await_args.args[0]
    assert mensaje["To"] == organizacion.owner_email
    assert enviar.await_args.kwargs["use_tls"] is True
    assert enviar.await_args.kwargs["timeout"] == email.TIMEOUT_SMTP_SEGUNDOS
    assert await _fila() is None


async def test_la_prueba_traduce_el_fallo_de_autenticacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    fallo = AsyncMock(side_effect=aiosmtplib.SMTPAuthenticationError(535, "bad key"))
    with patch("app.core.email.aiosmtplib.send", new=fallo):
        respuesta = await cliente.post(PRUEBA, headers=cabeceras, json=RESEND)
    assert respuesta.json()["ok"] is False
    assert respuesta.json()["motivo"] == "autenticacion"
    assert "bad key" not in respuesta.text


# --- Envío real -----------------------------------------------------------------


async def test_el_envio_usa_la_fila_guardada_y_vuelve_al_entorno_al_borrarla(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    await cliente.put(AJUSTES, headers=cabeceras, json=RESEND)

    config = await configuracion_efectiva()
    assert (config.host, config.password, config.tls_mode) == (
        "smtp.resend.com",
        API_KEY,
        "implicit",
    )

    await cliente.delete(AJUSTES, headers=cabeceras)
    assert (await configuracion_efectiva()).host == get_settings().smtp_host


async def test_guardar_refresca_la_cache_del_propio_proceso(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    assert (await configuracion_efectiva()).host == get_settings().smtp_host
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    await cliente.put(AJUSTES, headers=cabeceras, json=RESEND)
    assert (await configuracion_efectiva()).host == "smtp.resend.com"


async def test_una_credencial_ilegible_cae_al_entorno_en_vez_de_dejar_sin_correo(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clave de cifrado rotada sin re-cifrar: el correo sigue saliendo por el entorno."""
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    await cliente.put(AJUSTES, headers=cabeceras, json=RESEND)
    invalidar_configuracion_en_cache()
    monkeypatch.setenv("AI_SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    try:
        assert (await configuracion_efectiva()).host == get_settings().smtp_host
    finally:
        get_settings.cache_clear()
        invalidar_configuracion_en_cache()


async def test_la_prueba_distingue_el_fallo_de_tls(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, cifrado: str
) -> None:
    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    fallo = AsyncMock(side_effect=ssl.SSLError("WRONG_VERSION_NUMBER"))
    with patch("app.core.email.aiosmtplib.send", new=fallo):
        respuesta = await cliente.post(PRUEBA, headers=cabeceras, json=RESEND)
    assert respuesta.json()["motivo"] == "tls"


async def test_otro_proceso_ve_el_cambio_cuando_caduca_la_cache(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El worker no recibe aviso del panel: relee cuando caduca su caché."""
    reloj = [1000.0]
    monkeypatch.setattr(email.time, "monotonic", lambda: reloj[0])
    assert (await configuracion_efectiva()).host == get_settings().smtp_host

    cabeceras = await cabeceras_de_superadmin(cliente, organizacion)
    await cliente.put(AJUSTES, headers=cabeceras, json=RESEND)
    # Simula el otro proceso: su caché sigue viva con el valor viejo.
    email._cache = (reloj[0] + email.TTL_CONFIGURACION_SEGUNDOS, configuracion_de_entorno())
    assert (await configuracion_efectiva()).host == get_settings().smtp_host

    reloj[0] += email.TTL_CONFIGURACION_SEGUNDOS + 1
    assert (await configuracion_efectiva()).host == "smtp.resend.com"
    invalidar_configuracion_en_cache()
