"""Directorio de usuarios de plataforma (`admin/users_router.py`).

Fase 1-2 de `plans/260916-0810-usuarios-y-permisos-plataforma/`. Cubre los
Success Criteria del plan: listado sin `password_hash`, borrado suave sin
tocar organizaciones/inscripciones, `soporte` nunca alcanza escritura
sensible, nadie se desactiva/retira el rol a sí mismo.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.database import SessionMaintenance
from app.modules.auth.router import COOKIE_NOMBRE
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, crear_miembro, iniciar_sesion, iniciar_sesion_con

ADMIN_USERS = "/api/v1/admin/users"


async def _hacer_superadmin(email: str) -> None:
    async with SessionMaintenance() as session:
        await session.execute(update(User).where(User.email == email).values(is_superadmin=True))
        await session.commit()


async def _hacer_soporte(email: str) -> None:
    async with SessionMaintenance() as session:
        await session.execute(update(User).where(User.email == email).values(platform_role="soporte"))
        await session.commit()


async def _superadmin_headers(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> dict[str, str]:
    await _hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    return cabeceras


# --- Listado -----------------------------------------------------------


async def test_listar_no_expone_password_hash(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    respuesta = await cliente.get(ADMIN_USERS, headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["items"], "debería incluir al menos al propio superadmin"
    for fila in cuerpo["items"]:
        assert "password_hash" not in fila


async def test_listar_filtra_por_organizacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    otra = await crear_miembro(organizacion, "organizer")
    cabeceras = await _superadmin_headers(cliente, organizacion)

    respuesta = await cliente.get(
        ADMIN_USERS, headers=cabeceras, params={"organization_id": str(organizacion.id)}
    )
    assert respuesta.status_code == 200, respuesta.text
    ids = {fila["id"] for fila in respuesta.json()["items"]}
    assert str(otra.user_id) in ids
    assert str(organizacion.owner_id) in ids


async def test_listar_filtra_por_busqueda(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    respuesta = await cliente.get(
        ADMIN_USERS, headers=cabeceras, params={"q": organizacion.owner_email}
    )
    assert respuesta.status_code == 200, respuesta.text
    correos = {fila["email"] for fila in respuesta.json()["items"]}
    assert organizacion.owner_email in correos


async def test_soporte_puede_listar_y_ver_detalle(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _hacer_soporte(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    listado = await cliente.get(ADMIN_USERS, headers=cabeceras)
    assert listado.status_code == 200, listado.text

    detalle = await cliente.get(f"{ADMIN_USERS}/{organizacion.owner_id}", headers=cabeceras)
    assert detalle.status_code == 200, detalle.text


async def test_endpoints_rechazan_a_quien_no_tiene_rol_de_plataforma(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    assert (await cliente.get(ADMIN_USERS, headers=cabeceras)).status_code == 403


# --- Detalle -------------------------------------------------------------


async def test_detalle_incluye_organizacion_y_rol(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    respuesta = await cliente.get(f"{ADMIN_USERS}/{organizacion.owner_id}", headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert any(o["organization_id"] == str(organizacion.id) for o in cuerpo["organizations"])


async def test_detalle_de_usuario_inexistente_da_404(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    respuesta = await cliente.get(f"{ADMIN_USERS}/{uuid.uuid4()}", headers=cabeceras)
    assert respuesta.status_code == 404, respuesta.text


# --- Desactivar ------------------------------------------------------------


async def test_desactivar_impide_el_login_y_anonimiza_sin_tocar_organizaciones(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    objetivo = await crear_miembro(organizacion, "organizer")
    cabeceras = await _superadmin_headers(cliente, organizacion)

    respuesta = await cliente.post(f"{ADMIN_USERS}/{objetivo.user_id}/deactivate", headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["is_active"] is False
    assert cuerpo["first_name"] is None
    assert cuerpo["last_name"] is None
    assert cuerpo["email"] == objetivo.email  # el email se mantiene, decisión cerrada del plan

    # No puede volver a entrar.
    login = await cliente.post(
        "/api/v1/auth/login", json={"email": objetivo.email, "password": objetivo.password}
    )
    assert login.status_code in (401, 403), login.text

    # Sigue siendo miembro de la organización (borrado suave, no físico).
    async with SessionMaintenance() as session:
        from app.modules.organizations.models import OrganizationMember

        miembro = await session.scalar(
            select(OrganizationMember).where(OrganizationMember.id == objetivo.member_id)
        )
        assert miembro is not None


async def test_no_se_puede_desactivar_la_propia_cuenta(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    respuesta = await cliente.post(
        f"{ADMIN_USERS}/{organizacion.owner_id}/deactivate", headers=cabeceras
    )
    assert respuesta.status_code == 403, respuesta.text


async def test_soporte_no_puede_desactivar(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    objetivo = await crear_miembro(organizacion, "organizer")
    await _hacer_soporte(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(f"{ADMIN_USERS}/{objetivo.user_id}/deactivate", headers=cabeceras)
    assert respuesta.status_code == 403, respuesta.text


async def test_desactivar_revoca_las_sesiones_activas(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    objetivo = await crear_miembro(organizacion, "organizer")
    login_objetivo = await cliente.post(
        "/api/v1/auth/login",
        json={"email": objetivo.email, "password": objetivo.password},
    )
    assert login_objetivo.status_code == 200, login_objetivo.text
    refresh_objetivo = login_objetivo.cookies[COOKIE_NOMBRE]

    cabeceras_admin = await _superadmin_headers(cliente, organizacion)

    respuesta = await cliente.post(
        f"{ADMIN_USERS}/{objetivo.user_id}/deactivate", headers=cabeceras_admin
    )
    assert respuesta.status_code == 200, respuesta.text

    refresco = await cliente.post(
        "/api/v1/auth/refresh", cookies={COOKIE_NOMBRE: refresh_objetivo}
    )
    assert refresco.status_code in (401, 403), refresco.text


# --- Rol de plataforma -----------------------------------------------------


async def test_asignar_y_retirar_soporte(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    objetivo = await crear_miembro(organizacion, "organizer")
    cabeceras = await _superadmin_headers(cliente, organizacion)

    asignar = await cliente.put(
        f"{ADMIN_USERS}/{objetivo.user_id}/platform-role",
        headers=cabeceras,
        json={"platform_role": "soporte"},
    )
    assert asignar.status_code == 200, asignar.text
    assert asignar.json()["platform_role"] == "soporte"

    retirar = await cliente.put(
        f"{ADMIN_USERS}/{objetivo.user_id}/platform-role",
        headers=cabeceras,
        json={"platform_role": None},
    )
    assert retirar.status_code == 200, retirar.text
    assert retirar.json()["platform_role"] is None


async def test_rechaza_asignar_superadmin_por_este_endpoint(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    objetivo = await crear_miembro(organizacion, "organizer")
    cabeceras = await _superadmin_headers(cliente, organizacion)

    respuesta = await cliente.put(
        f"{ADMIN_USERS}/{objetivo.user_id}/platform-role",
        headers=cabeceras,
        json={"platform_role": "superadmin"},
    )
    assert respuesta.status_code == 422, respuesta.text


async def test_no_se_puede_retirar_el_propio_rol_de_plataforma(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    cabeceras = await _superadmin_headers(cliente, organizacion)
    respuesta = await cliente.put(
        f"{ADMIN_USERS}/{organizacion.owner_id}/platform-role",
        headers=cabeceras,
        json={"platform_role": None},
    )
    assert respuesta.status_code == 403, respuesta.text


async def test_soporte_no_puede_cambiar_roles_de_plataforma(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    objetivo = await crear_miembro(organizacion, "organizer")
    await _hacer_soporte(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.put(
        f"{ADMIN_USERS}/{objetivo.user_id}/platform-role",
        headers=cabeceras,
        json={"platform_role": "soporte"},
    )
    assert respuesta.status_code == 403, respuesta.text


async def test_soporte_recien_asignado_accede_sin_volver_a_iniciar_sesion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Hallazgo S-2 del red-team: lectura en base de datos, no en el claim."""
    objetivo = await crear_miembro(organizacion, "organizer")
    _, cabeceras_objetivo = await iniciar_sesion_con(
        cliente, organizacion, objetivo.email, objetivo.password
    )
    cabeceras_admin = await _superadmin_headers(cliente, organizacion)

    await cliente.put(
        f"{ADMIN_USERS}/{objetivo.user_id}/platform-role",
        headers=cabeceras_admin,
        json={"platform_role": "soporte"},
    )

    respuesta = await cliente.get(ADMIN_USERS, headers=cabeceras_objetivo)
    assert respuesta.status_code == 200, respuesta.text
