"""Autenticación: login, rotación de refresh, reutilización y cierre de sesión."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.modules.auth.router import COOKIE_NOMBRE
from app.shared.errors import ServiceUnavailableError
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"


async def test_login_correcto_devuelve_token_y_cookie(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await cliente.post(
        LOGIN,
        json={"email": organizacion.owner_email, "password": organizacion.owner_password},
        headers={"Host": organizacion.host},
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["access_token"]
    assert cuerpo["user"]["email"] == organizacion.owner_email

    cookie = respuesta.cookies.get(COOKIE_NOMBRE)
    assert cookie, "el refresh token debe viajar en la cookie"
    cabecera = respuesta.headers["set-cookie"]
    minusculas = cabecera.lower()
    assert "httponly" in minusculas
    assert "path=/api/v1/auth" in minusculas
    assert "samesite=lax" in minusculas
    # Sin atributo Domain: web y API comparten host tras Caddy.
    assert "domain=" not in minusculas
    # El refresh nunca debe aparecer en el cuerpo de la respuesta.
    assert cookie not in respuesta.text


async def test_login_con_contraseña_incorrecta_devuelve_401(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await cliente.post(
        LOGIN,
        json={"email": organizacion.owner_email, "password": "no-es-la-buena"},
        headers={"Host": organizacion.host},
    )
    assert respuesta.status_code == 401


async def test_login_con_usuario_de_otra_organizacion_devuelve_401(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    """Las credenciales de una organización no valen en el host de otra."""
    respuesta = await cliente.post(
        LOGIN,
        json={
            "email": otra_organizacion.owner_email,
            "password": otra_organizacion.owner_password,
        },
        headers={"Host": organizacion.host},
    )
    assert respuesta.status_code == 401


async def test_refresh_rota_el_token(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    login = await cliente.post(
        LOGIN,
        json={"email": organizacion.owner_email, "password": organizacion.owner_password},
        headers={"Host": organizacion.host},
    )
    primero = login.cookies[COOKIE_NOMBRE]

    respuesta = await cliente.post(REFRESH, headers={"Host": organizacion.host})
    assert respuesta.status_code == 200
    assert respuesta.json()["access_token"]
    segundo = respuesta.cookies[COOKIE_NOMBRE]
    assert segundo != primero, "cada refresco debe emitir un token nuevo"


async def test_reutilizar_un_refresh_rotado_invalida_la_familia(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    login = await cliente.post(
        LOGIN,
        json={"email": organizacion.owner_email, "password": organizacion.owner_password},
        headers={"Host": organizacion.host},
    )
    robado = login.cookies[COOKIE_NOMBRE]

    primero = await cliente.post(REFRESH, headers={"Host": organizacion.host})
    assert primero.status_code == 200
    vigente = primero.cookies[COOKIE_NOMBRE]

    # El atacante reutiliza el token antiguo.
    cliente.cookies.set(COOKIE_NOMBRE, robado, path="/api/v1/auth")
    reutilizacion = await cliente.post(REFRESH, headers={"Host": organizacion.host})
    assert reutilizacion.status_code == 401

    # Y el token legítimo también queda invalidado: la familia entera se revoca.
    cliente.cookies.set(COOKIE_NOMBRE, vigente, path="/api/v1/auth")
    posterior = await cliente.post(REFRESH, headers={"Host": organizacion.host})
    assert posterior.status_code == 401


async def test_logout_revoca_la_sesion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await cliente.post(
        LOGIN,
        json={"email": organizacion.owner_email, "password": organizacion.owner_password},
        headers={"Host": organizacion.host},
    )
    salida = await cliente.post(LOGOUT, headers={"Host": organizacion.host})
    assert salida.status_code == 204

    posterior = await cliente.post(REFRESH, headers={"Host": organizacion.host})
    assert posterior.status_code == 401


async def test_refresh_sin_redis_devuelve_503(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Sin Redis no se puede comprobar la revocación: se falla cerrado, no abierto."""
    await cliente.post(
        LOGIN,
        json={"email": organizacion.owner_email, "password": organizacion.owner_password},
        headers={"Host": organizacion.host},
    )
    with patch(
        "app.modules.auth.service.require_redis",
        side_effect=ServiceUnavailableError("Redis caído"),
    ):
        respuesta = await cliente.post(REFRESH, headers={"Host": organizacion.host})
    assert respuesta.status_code == 503


async def test_endpoint_protegido_sin_token_devuelve_401(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    respuesta = await cliente.get("/api/v1/users/me", headers={"Host": organizacion.host})
    assert respuesta.status_code == 401


async def test_token_de_otra_organizacion_devuelve_403(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    """Cambiar el Host con un token válido de otra organización no da acceso."""
    _, _ = await iniciar_sesion(cliente, organizacion)
    token, _ = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get(
        "/api/v1/users/me",
        headers={"Host": otra_organizacion.host, "Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 403


@pytest.mark.parametrize("token", ["", "no-es-un-jwt", "a.b.c"])
async def test_token_invalido_devuelve_401(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, token: str
) -> None:
    respuesta = await cliente.get(
        "/api/v1/users/me",
        headers={"Host": organizacion.host, "Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 401
