"""Cuenta propia: perfil, cambio de correo, cambio de contraseña, enlaces sociales y
el selector de organizaciones (fase 5 del PRD)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import SessionApp, set_organization_context
from app.core.tasks import send_email_change_confirmation, send_email_change_warning
from app.modules.auth import service as auth_service
from app.modules.auth.router import COOKIE_NOMBRE
from app.modules.auth.verification import PROPOSITO_CAMBIO_CORREO, generate_token
from app.shared.errors import ConflictError
from tests.conftest import OrganizacionDePrueba, crear_organizacion, iniciar_sesion

ME = "/api/v1/users/me"
CHANGE_EMAIL = "/api/v1/users/me/change-email"
CHANGE_EMAIL_CONFIRM = "/api/v1/users/me/change-email/confirm"
CHANGE_PASSWORD = "/api/v1/users/me/change-password"
SOCIAL_LINKS = "/api/v1/users/me/social-links"
ORGANIZATIONS = "/api/v1/users/me/organizations"
REFRESH = "/api/v1/auth/refresh"
LOGIN = "/api/v1/auth/login"

NUEVA_CONTRASENA = "Otra-Contraseña-Larga-1!"


@pytest.fixture(autouse=True)
def _sin_verificacion_de_contrasena_filtrada():
    with patch("app.modules.auth.service._password_filtrada", return_value=False):
        yield


@pytest.fixture(autouse=True)
def _correo_de_cambio_encolado_sincrono():
    with (
        patch.object(send_email_change_warning, "kiq", new_callable=AsyncMock) as aviso,
        patch.object(send_email_change_confirmation, "kiq", new_callable=AsyncMock) as confirmacion,
    ):
        yield aviso, confirmacion


async def test_patch_me_actualiza_nombre_y_locale(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.patch(
        ME, headers=cabeceras, json={"first_name": "Nuevo", "last_name": "Nombre"}
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["first_name"] == "Nuevo"
    assert cuerpo["last_name"] == "Nombre"


async def test_change_email_exige_la_contrasena_actual(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        CHANGE_EMAIL,
        headers=cabeceras,
        json={"new_email": "nuevo@example.com", "password": "no-es-la-buena"},
    )
    assert respuesta.status_code == 401


async def test_change_email_con_correo_ya_en_uso_devuelve_409(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        CHANGE_EMAIL,
        headers=cabeceras,
        json={
            "new_email": otra_organizacion.owner_email,
            "password": organizacion.owner_password,
        },
    )
    assert respuesta.status_code == 409


async def test_change_email_avisa_al_correo_viejo_y_no_se_aplica_hasta_confirmar(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    _correo_de_cambio_encolado_sincrono: tuple[AsyncMock, AsyncMock],
) -> None:
    aviso, confirmacion = _correo_de_cambio_encolado_sincrono
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    solicitud = await cliente.post(
        CHANGE_EMAIL,
        headers=cabeceras,
        json={"new_email": "nuevo@example.com", "password": organizacion.owner_password},
    )
    assert solicitud.status_code == 202
    aviso.assert_awaited_once()
    assert aviso.call_args.args[0] == organizacion.owner_email
    confirmacion.assert_awaited_once()

    # Sin confirmar todavía: el correo actual sigue siendo el de antes.
    actual = await cliente.get(ME, headers=cabeceras)
    assert actual.json()["email"] == organizacion.owner_email


async def test_change_email_confirmar_aplica_el_cambio_y_revoca_las_sesiones(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    login = await cliente.post(
        LOGIN,
        json={"email": organizacion.owner_email, "password": organizacion.owner_password},
        headers={"Host": organizacion.host},
    )
    refresh_previo = login.cookies[COOKIE_NOMBRE]

    token = await generate_token(
        PROPOSITO_CAMBIO_CORREO, f"{organizacion.owner_id}:nuevo@example.com"
    )
    confirmacion = await cliente.post(
        CHANGE_EMAIL_CONFIRM, json={"token": token}, headers={"Host": organizacion.host}
    )
    assert confirmacion.status_code == 200

    login_con_el_nuevo = await cliente.post(
        LOGIN,
        json={"email": "nuevo@example.com", "password": organizacion.owner_password},
        headers={"Host": organizacion.host},
    )
    assert login_con_el_nuevo.status_code == 200

    revocado = await cliente.post(
        REFRESH, headers={"Host": organizacion.host}, cookies={COOKIE_NOMBRE: refresh_previo}
    )
    assert revocado.status_code == 401


async def test_confirmar_dos_cambios_de_correo_concurrentes_al_mismo_correo_da_409(
    organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    """La comprobación previa de disponibilidad no cierra la carrera: dos
    confirmaciones distintas pueden pasarla a la vez si corren en paralelo. El
    `UNIQUE` de `users.email` es quien de verdad decide, y el resultado debe ser un
    409 controlado, no una excepción sin capturar."""
    correo_disputado = "disputado@example.com"
    token_a = await generate_token(
        PROPOSITO_CAMBIO_CORREO, f"{organizacion.owner_id}:{correo_disputado}"
    )
    token_b = await generate_token(
        PROPOSITO_CAMBIO_CORREO, f"{otra_organizacion.owner_id}:{correo_disputado}"
    )

    async def confirmar(token: str):  # type: ignore[no-untyped-def]
        async with SessionApp() as session:
            async with session.begin():
                await set_organization_context(session, None)
                return await auth_service.change_email_confirm(session, token=token)

    resultados = await asyncio.gather(
        confirmar(token_a), confirmar(token_b), return_exceptions=True
    )

    errores = [r for r in resultados if isinstance(r, BaseException)]
    exitos = [r for r in resultados if not isinstance(r, BaseException)]
    assert len(exitos) == 1, "una de las dos confirmaciones debe aplicarse"
    assert len(errores) == 1, "la otra debe fallar, no aplicarse silenciosamente"
    assert isinstance(errores[0], ConflictError), (
        f"se esperaba ConflictError (409), se obtuvo {type(errores[0])!r}"
    )


async def test_change_password_exige_la_actual(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        CHANGE_PASSWORD,
        headers=cabeceras,
        json={"current_password": "no-es-la-buena", "new_password": NUEVA_CONTRASENA},
    )
    assert respuesta.status_code == 401


async def test_change_password_revoca_las_demas_sesiones_pero_conserva_la_actual(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    otro_login = await cliente.post(
        LOGIN,
        json={"email": organizacion.owner_email, "password": organizacion.owner_password},
        headers={"Host": organizacion.host},
    )
    refresh_de_otra_sesion = otro_login.cookies[COOKIE_NOMBRE]

    token, cabeceras = await iniciar_sesion(cliente, organizacion)
    login_actual = await cliente.post(
        LOGIN,
        json={"email": organizacion.owner_email, "password": organizacion.owner_password},
        headers={"Host": organizacion.host},
    )
    refresh_actual = login_actual.cookies[COOKIE_NOMBRE]
    cabeceras_actuales = {
        "Host": organizacion.host,
        "Authorization": f"Bearer {login_actual.json()['access_token']}",
    }

    cambio = await cliente.post(
        CHANGE_PASSWORD,
        headers=cabeceras_actuales,
        json={
            "current_password": organizacion.owner_password,
            "new_password": NUEVA_CONTRASENA,
        },
    )
    assert cambio.status_code == 200

    sesion_actual = await cliente.post(
        REFRESH, headers={"Host": organizacion.host}, cookies={COOKIE_NOMBRE: refresh_actual}
    )
    assert sesion_actual.status_code == 200, "la sesión que hizo el cambio debe seguir viva"

    otra_sesion = await cliente.post(
        REFRESH,
        headers={"Host": organizacion.host},
        cookies={COOKIE_NOMBRE: refresh_de_otra_sesion},
    )
    assert otra_sesion.status_code == 401, "las demás sesiones deben quedar revocadas"


async def test_social_links_crud(cliente: AsyncClient, organizacion: OrganizacionDePrueba) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    vacio = await cliente.get(SOCIAL_LINKS, headers=cabeceras)
    assert vacio.json() == []

    creado = await cliente.put(
        f"{SOCIAL_LINKS}/twitter",
        headers=cabeceras,
        json={"url": "https://twitter.com/ejemplo"},
    )
    assert creado.status_code == 200
    assert creado.json() == {"kind": "twitter", "url": "https://twitter.com/ejemplo"}

    actualizado = await cliente.put(
        f"{SOCIAL_LINKS}/twitter",
        headers=cabeceras,
        json={"url": "https://twitter.com/otro"},
    )
    assert actualizado.json()["url"] == "https://twitter.com/otro"

    listado = await cliente.get(SOCIAL_LINKS, headers=cabeceras)
    assert len(listado.json()) == 1

    borrado = await cliente.delete(f"{SOCIAL_LINKS}/twitter", headers=cabeceras)
    assert borrado.status_code == 204

    listado_final = await cliente.get(SOCIAL_LINKS, headers=cabeceras)
    assert listado_final.json() == []


async def test_get_organizations_lista_solo_las_propias(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    segunda = await crear_organizacion(
        "segunda-org", "segunda.test", owner_password=organizacion.owner_password
    )
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get(ORGANIZATIONS, headers=cabeceras)
    assert respuesta.status_code == 200
    slugs = {fila["slug"] for fila in respuesta.json()}
    assert slugs == {organizacion.slug}
    assert segunda.slug not in slugs


async def test_app_user_organizations_no_devuelve_organizaciones_ajenas(
    app_db, organizacion: OrganizacionDePrueba, otra_organizacion: OrganizacionDePrueba
) -> None:
    """La función SECURITY DEFINER solo responde para `app.user_id`, nunca para un
    `p_user_id` arbitrario pasado por parámetro."""
    from app.core.database import set_organization_context

    await set_organization_context(app_db, organizacion.id, organizacion.owner_id)
    filas = (
        await app_db.execute(
            text("SELECT organization_id FROM app_user_organizations(:id)"),
            {"id": otra_organizacion.owner_id},
        )
    ).all()
    assert filas == []
