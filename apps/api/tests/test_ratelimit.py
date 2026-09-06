"""Límite de peticiones en los endpoints de autenticación."""

from __future__ import annotations

from unittest.mock import patch

from httpx import AsyncClient

from app.core.ratelimit import LOGIN_POR_IP
from app.shared.errors import ServiceUnavailableError
from tests.conftest import OrganizacionDePrueba

LOGIN = "/api/v1/auth/login"


async def test_el_login_se_bloquea_tras_superar_el_limite(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    datos = {"email": organizacion.owner_email, "password": "incorrecta"}
    cabeceras = {"Host": organizacion.host}

    for _ in range(LOGIN_POR_IP):
        respuesta = await cliente.post(LOGIN, json=datos, headers=cabeceras)
        assert respuesta.status_code == 401

    bloqueada = await cliente.post(LOGIN, json=datos, headers=cabeceras)
    assert bloqueada.status_code == 429
    assert bloqueada.json()["retry_after"] > 0


async def test_sin_redis_el_login_devuelve_503(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """No se puede contar sin Redis, así que se rechaza en lugar de dejar pasar."""
    with patch(
        "app.core.ratelimit.require_redis",
        side_effect=ServiceUnavailableError("Redis caído"),
    ):
        respuesta = await cliente.post(
            LOGIN,
            json={"email": organizacion.owner_email, "password": organizacion.owner_password},
            headers={"Host": organizacion.host},
        )
    assert respuesta.status_code == 503
