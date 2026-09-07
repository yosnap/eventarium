"""Recuperación de contraseña: `forgot-password` / `reset-password`."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.tasks import send_password_reset_email
from app.modules.auth.router import COOKIE_NOMBRE
from app.modules.auth.verification import (
    PROPOSITO_RECUPERAR_CONTRASENA,
    PROPOSITO_VERIFICACION_CORREO,
    generate_token,
)
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

FORGOT = "/api/v1/auth/forgot-password"
RESET = "/api/v1/auth/reset-password"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
MIEMBROS = "/api/v1/organizations/me/members"
ROLES = "/api/v1/roles"
CREAR_ORGANIZACION = "/api/v1/organizations"

NUEVA_CONTRASENA = "Otra-Contraseña-Larga-1!"


@pytest.fixture(autouse=True)
def _sin_verificacion_de_contrasena_filtrada():
    with patch("app.modules.auth.service._password_filtrada", return_value=False):
        yield


@pytest.fixture(autouse=True)
def _correo_de_recuperacion_encolado_sincrono():
    with patch.object(send_password_reset_email, "kiq", new_callable=AsyncMock) as tarea:
        yield tarea


async def test_forgot_password_exige_turnstile(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    with (
        patch("app.core.turnstile.get_settings") as settings_falso,
        patch("app.core.turnstile.verify_turnstile_token", return_value=False),
    ):
        settings_falso.return_value.turnstile_enabled = True
        respuesta = await cliente.post(
            FORGOT,
            json={"email": organizacion.owner_email, "turnstile_token": "token-de-prueba"},
            headers={"Host": organizacion.host},
        )
    assert respuesta.status_code == 422


async def test_forgot_password_responde_igual_exista_o_no_la_cuenta(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    _correo_de_recuperacion_encolado_sincrono: AsyncMock,
) -> None:
    inexistente = await cliente.post(
        FORGOT,
        json={"email": "nadie@example.com", "turnstile_token": "token-de-prueba"},
        headers={"Host": organizacion.host},
    )
    existente = await cliente.post(
        FORGOT,
        json={"email": organizacion.owner_email, "turnstile_token": "token-de-prueba"},
        headers={"Host": organizacion.host},
    )
    assert inexistente.status_code == existente.status_code == 202
    assert inexistente.json() == existente.json()
    _correo_de_recuperacion_encolado_sincrono.assert_awaited_once()


async def test_reset_password_cambia_la_contrasena_y_consume_el_token(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    token = await generate_token(PROPOSITO_RECUPERAR_CONTRASENA, str(organizacion.owner_id))

    respuesta = await cliente.post(
        RESET,
        json={"token": token, "new_password": NUEVA_CONTRASENA},
        headers={"Host": organizacion.host},
    )
    assert respuesta.status_code == 200

    login_nueva = await cliente.post(
        LOGIN,
        json={"email": organizacion.owner_email, "password": NUEVA_CONTRASENA},
        headers={"Host": organizacion.host},
    )
    assert login_nueva.status_code == 200

    login_vieja = await cliente.post(
        LOGIN,
        json={"email": organizacion.owner_email, "password": organizacion.owner_password},
        headers={"Host": organizacion.host},
    )
    assert login_vieja.status_code == 401

    reutilizado = await cliente.post(
        RESET,
        json={"token": token, "new_password": NUEVA_CONTRASENA},
        headers={"Host": organizacion.host},
    )
    assert reutilizado.status_code == 422


async def test_reset_password_revoca_las_sesiones_existentes(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    login = await cliente.post(
        LOGIN,
        json={"email": organizacion.owner_email, "password": organizacion.owner_password},
        headers={"Host": organizacion.host},
    )
    refresh_previo = login.cookies[COOKIE_NOMBRE]

    token = await generate_token(PROPOSITO_RECUPERAR_CONTRASENA, str(organizacion.owner_id))
    await cliente.post(
        RESET,
        json={"token": token, "new_password": NUEVA_CONTRASENA},
        headers={"Host": organizacion.host},
    )

    respuesta = await cliente.post(
        REFRESH,
        headers={"Host": organizacion.host},
        cookies={COOKIE_NOMBRE: refresh_previo},
    )
    assert respuesta.status_code == 401


async def test_un_token_de_otro_proposito_no_sirve_para_recuperar(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    token_de_verificacion = await generate_token(
        PROPOSITO_VERIFICACION_CORREO, str(organizacion.owner_id)
    )
    respuesta = await cliente.post(
        RESET,
        json={"token": token_de_verificacion, "new_password": NUEVA_CONTRASENA},
        headers={"Host": organizacion.host},
    )
    assert respuesta.status_code == 422


async def test_un_token_de_recuperacion_no_sirve_para_verificar_correo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    token = await generate_token(PROPOSITO_RECUPERAR_CONTRASENA, str(organizacion.owner_id))
    respuesta = await cliente.get(
        "/api/v1/auth/verify-email",
        params={"token": token},
        headers={"Host": organizacion.host},
    )
    assert respuesta.status_code == 422


async def test_miembro_invitado_completa_recuperacion_y_queda_verificado(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, app_db
) -> None:
    """Un miembro invitado (`password_hash` nulo, sin verificar) nunca pasa por
    `/auth/register`; completar la recuperación de contraseña lo verifica igual que
    `verify-email`, y puede crear su propia organización después."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    roles = (await cliente.get(ROLES, headers=cabeceras)).json()
    rol_id = next(rol for rol in roles if rol["key"] == "attendee")["id"]

    correo_invitado = "invitada@example.com"
    alta = await cliente.post(
        MIEMBROS,
        headers=cabeceras,
        json={
            "email": correo_invitado,
            "first_name": "Invitada",
            "last_name": "De prueba",
            "role_id": rol_id,
            "profile_data": {},
        },
    )
    assert alta.status_code == 201

    fila = (
        await app_db.execute(
            text("SELECT id, email_verified_at FROM app_find_user_by_email(:email)"),
            {"email": correo_invitado},
        )
    ).first()
    assert fila is not None
    assert fila[1] is None, "un miembro invitado empieza sin correo verificado"

    token = await generate_token(PROPOSITO_RECUPERAR_CONTRASENA, str(fila[0]))
    respuesta = await cliente.post(
        RESET,
        json={"token": token, "new_password": NUEVA_CONTRASENA},
        headers={"Host": organizacion.host},
    )
    assert respuesta.status_code == 200

    verificada = (
        await app_db.execute(
            text("SELECT email_verified_at FROM app_find_user_by_email(:email)"),
            {"email": correo_invitado},
        )
    ).first()
    assert verificada[0] is not None

    login = await cliente.post(
        LOGIN,
        json={"email": correo_invitado, "password": NUEVA_CONTRASENA},
        headers={"Host": organizacion.host},
    )
    assert login.status_code == 200
    token_acceso = login.json()["access_token"]

    creacion = await cliente.post(
        CREAR_ORGANIZACION,
        json={
            "name": "Organización de Invitada",
            "slug": "org-de-invitada",
            "first_name": "Invitada",
            "last_name": "De prueba",
            "turnstile_token": "token-de-prueba",
        },
        headers={"Authorization": f"Bearer {token_acceso}"},
    )
    assert creacion.status_code == 201, creacion.text
