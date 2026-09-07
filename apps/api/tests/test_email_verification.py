"""Registro, verificación de correo y reenvío."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.tasks import send_verification_email
from app.modules.auth.verification import PROPOSITO_VERIFICACION_CORREO, generate_token
from app.shared.errors import ServiceUnavailableError
from tests.conftest import OrganizacionDePrueba

REGISTER = "/api/v1/auth/register"
VERIFY = "/api/v1/auth/verify-email"
RESEND = "/api/v1/auth/resend-verification"

DATOS_REGISTRO = {
    "email": "nueva-persona@example.com",
    "password": "Una-Contraseña-Larga-1!",
    "full_name": "Persona Nueva",
    "turnstile_token": "token-de-prueba",
}


@pytest.fixture(autouse=True)
def _sin_verificacion_de_contrasena_filtrada():
    """El chequeo de HIBP es una llamada externa; se aísla en todos los tests de aquí."""
    with patch("app.modules.auth.service._password_filtrada", return_value=False):
        yield


@pytest.fixture(autouse=True)
def _correo_encolado_sincrono():
    """Evita depender del worker de Taskiq: solo se comprueba que se encola."""
    with patch.object(send_verification_email, "kiq", new_callable=AsyncMock) as tarea:
        yield tarea


async def test_registro_crea_usuario_no_verificado_y_encola_correo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, _correo_encolado_sincrono: AsyncMock
) -> None:
    respuesta = await cliente.post(
        REGISTER, json=DATOS_REGISTRO, headers={"Host": organizacion.host}
    )
    assert respuesta.status_code == 202

    _correo_encolado_sincrono.assert_awaited_once()
    correo_enviado, _token = _correo_encolado_sincrono.call_args.args
    assert correo_enviado == DATOS_REGISTRO["email"]


async def test_registro_dos_veces_responde_igual_y_no_duplica(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, _correo_encolado_sincrono: AsyncMock
) -> None:
    primera = await cliente.post(REGISTER, json=DATOS_REGISTRO, headers={"Host": organizacion.host})
    segunda = await cliente.post(REGISTER, json=DATOS_REGISTRO, headers={"Host": organizacion.host})

    assert primera.status_code == segunda.status_code == 202
    assert primera.json() == segunda.json()
    assert _correo_encolado_sincrono.await_count == 1


async def test_verificar_token_marca_el_correo_y_el_segundo_intento_falla(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, app_db
) -> None:
    await cliente.post(REGISTER, json=DATOS_REGISTRO, headers={"Host": organizacion.host})
    fila = (
        await app_db.execute(
            text("SELECT id FROM app_find_user_by_email(:email)"),
            {"email": DATOS_REGISTRO["email"]},
        )
    ).first()
    assert fila is not None
    token = await generate_token(PROPOSITO_VERIFICACION_CORREO, fila[0])

    primera = await cliente.get(
        VERIFY, params={"token": token}, headers={"Host": organizacion.host}
    )
    assert primera.status_code == 200

    segunda = await cliente.get(
        VERIFY, params={"token": token}, headers={"Host": organizacion.host}
    )
    assert segunda.status_code == 422


async def test_token_no_existente_devuelve_422(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await cliente.get(
        VERIFY, params={"token": "no-existe"}, headers={"Host": organizacion.host}
    )
    assert respuesta.status_code == 422


async def test_reenvio_responde_igual_exista_o_no_la_cuenta(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, _correo_encolado_sincrono: AsyncMock
) -> None:
    datos = {"email": "nadie@example.com", "turnstile_token": "token-de-prueba"}
    respuesta = await cliente.post(RESEND, json=datos, headers={"Host": organizacion.host})
    assert respuesta.status_code == 202
    _correo_encolado_sincrono.assert_not_awaited()

    await cliente.post(REGISTER, json=DATOS_REGISTRO, headers={"Host": organizacion.host})
    _correo_encolado_sincrono.reset_mock()

    reenvio = await cliente.post(
        RESEND,
        json={"email": DATOS_REGISTRO["email"], "turnstile_token": "token-de-prueba"},
        headers={"Host": organizacion.host},
    )
    assert reenvio.status_code == 202
    _correo_encolado_sincrono.assert_awaited_once()


async def test_reenvio_de_cuenta_ya_verificada_no_encola_correo(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    app_db,
    _correo_encolado_sincrono: AsyncMock,
) -> None:
    await cliente.post(REGISTER, json=DATOS_REGISTRO, headers={"Host": organizacion.host})
    fila = (
        await app_db.execute(
            text("SELECT id FROM app_find_user_by_email(:email)"),
            {"email": DATOS_REGISTRO["email"]},
        )
    ).first()
    token = await generate_token(PROPOSITO_VERIFICACION_CORREO, fila[0])
    await cliente.get(VERIFY, params={"token": token}, headers={"Host": organizacion.host})
    _correo_encolado_sincrono.reset_mock()

    reenvio = await cliente.post(
        RESEND,
        json={"email": DATOS_REGISTRO["email"], "turnstile_token": "token-de-prueba"},
        headers={"Host": organizacion.host},
    )
    assert reenvio.status_code == 202
    _correo_encolado_sincrono.assert_not_awaited()


async def test_registro_sin_redis_devuelve_503(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    with patch(
        "app.modules.auth.verification.require_redis",
        side_effect=ServiceUnavailableError("Redis caído"),
    ):
        respuesta = await cliente.post(
            REGISTER, json=DATOS_REGISTRO, headers={"Host": organizacion.host}
        )
    assert respuesta.status_code == 503


async def test_contrasena_filtrada_rechaza_el_registro(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    with patch("app.modules.auth.service._password_filtrada", return_value=True):
        respuesta = await cliente.post(
            REGISTER, json=DATOS_REGISTRO, headers={"Host": organizacion.host}
        )
    assert respuesta.status_code == 422


async def test_contrasena_sin_complejidad_rechaza_el_registro(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    datos = {**DATOS_REGISTRO, "password": "sin-mayuscula-ni-simbolo-1"}
    respuesta = await cliente.post(REGISTER, json=datos, headers={"Host": organizacion.host})
    assert respuesta.status_code == 422


async def test_turnstile_invalido_rechaza_el_registro(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    with (
        patch("app.core.turnstile.get_settings") as settings_falso,
        patch("app.core.turnstile.verify_turnstile_token", return_value=False),
    ):
        settings_falso.return_value.turnstile_enabled = True
        respuesta = await cliente.post(
            REGISTER, json=DATOS_REGISTRO, headers={"Host": organizacion.host}
        )
    assert respuesta.status_code == 422


async def test_turnstile_caido_devuelve_503(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    with (
        patch("app.core.turnstile.get_settings") as settings_falso,
        patch(
            "app.core.turnstile.verify_turnstile_token",
            side_effect=ServiceUnavailableError("Turnstile caído"),
        ),
    ):
        settings_falso.return_value.turnstile_enabled = True
        respuesta = await cliente.post(
            REGISTER, json=DATOS_REGISTRO, headers={"Host": organizacion.host}
        )
    assert respuesta.status_code == 503
