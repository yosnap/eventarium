"""Alta y listado de miembros, con validación de los campos de perfil del rol."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionApp, set_organization_context
from app.core.security import hash_password
from app.modules.organizations.models import OrganizationMember
from app.modules.roles.models import Role
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

MIEMBROS = "/api/v1/organizations/me/members"
ROLES = "/api/v1/roles"


async def _rol(cliente: AsyncClient, cabeceras: dict[str, str], clave: str) -> str:
    roles = (await cliente.get(ROLES, headers=cabeceras)).json()
    return next(rol for rol in roles if rol["key"] == clave)["id"]


async def test_alta_de_miembro_con_perfil_valido(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    rol = await _rol(cliente, cabeceras, "speaker")

    respuesta = await cliente.post(
        MIEMBROS,
        headers=cabeceras,
        json={
            "email": "ponente@example.com",
            "first_name": "Ana Ponente",
            "last_name": "Prueba",
            "role_id": rol,
            "profile_data": {
                "bio": "Ingeniera de datos",
                "web": "https://ejemplo.com",
                "contacto": "ana@example.com",
            },
        },
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["roles"][0]["role_key"] == "speaker"
    assert cuerpo["profile_data"]["bio"] == "Ingeniera de datos"


async def test_listar_miembro_con_email_de_dominio_reservado(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    # Un email con dominio reservado (example.test) puede colarse en la base
    # de datos por vías que no pasan por MemberCreate (datos importados,
    # semillas, cambios de criterio del validador): el listado de miembros no
    # puede revientar al serializar, así que el email de salida es un str.
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organizacion.id)
            rol = await session.scalar(
                select(Role).where(Role.organization_id == organizacion.id, Role.key == "speaker")
            )
            assert rol is not None
            usuario = User(
                email="andres.vidal.demo@example.test",
                first_name="Andrés",
                last_name="Vidal",
                password_hash=hash_password("ClaveDePrueba-2026!"),
                is_active=True,
            )
            session.add(usuario)
            await session.flush()
            session.add(
                OrganizationMember(
                    organization_id=organizacion.id,
                    user_id=usuario.id,
                    role_id=rol.id,
                    profile_data={},
                )
            )

    listado = await cliente.get(MIEMBROS, headers=cabeceras)
    assert listado.status_code == 200, listado.text
    emails = [persona["email"] for persona in listado.json()["items"]]
    assert "andres.vidal.demo@example.test" in emails


async def test_falta_un_campo_obligatorio_del_rol(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    rol = await _rol(cliente, cabeceras, "speaker")

    respuesta = await cliente.post(
        MIEMBROS,
        headers=cabeceras,
        json={
            "email": "sin-bio@example.com",
            "first_name": "Sin Bio",
            "last_name": "Prueba",
            "role_id": rol,
        },
    )
    assert respuesta.status_code == 422


async def test_url_mal_formada_en_un_campo_de_tipo_url(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    rol = await _rol(cliente, cabeceras, "speaker")

    respuesta = await cliente.post(
        MIEMBROS,
        headers=cabeceras,
        json={
            "email": "mala-url@example.com",
            "first_name": "Mala URL",
            "last_name": "Prueba",
            "role_id": rol,
            "profile_data": {"bio": "Hola", "web": "no-es-una-url"},
        },
    )
    assert respuesta.status_code == 422


async def test_campo_no_definido_para_el_rol(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    rol = await _rol(cliente, cabeceras, "attendee")

    respuesta = await cliente.post(
        MIEMBROS,
        headers=cabeceras,
        json={
            "email": "curiosa@example.com",
            "first_name": "Curiosa",
            "last_name": "Prueba",
            "role_id": rol,
            "profile_data": {"campo_inventado": "valor"},
        },
    )
    assert respuesta.status_code == 422
    assert "campo_inventado" in respuesta.json()["campos_desconocidos"]


async def test_opcion_no_valida_en_un_campo_de_seleccion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    rol = await _rol(cliente, cabeceras, "volunteer")

    respuesta = await cliente.post(
        MIEMBROS,
        headers=cabeceras,
        json={
            "email": "voluntaria@example.com",
            "first_name": "Voluntaria",
            "last_name": "Prueba",
            "role_id": rol,
            "profile_data": {"talla_camiseta": "XXXXL"},
        },
    )
    assert respuesta.status_code == 422


async def test_no_se_puede_repetir_persona_y_rol(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    rol = await _rol(cliente, cabeceras, "attendee")
    datos = {
        "email": "repetida@example.com",
        "first_name": "Repetida",
        "last_name": "Prueba",
        "role_id": rol,
    }

    assert (await cliente.post(MIEMBROS, headers=cabeceras, json=datos)).status_code == 201
    assert (await cliente.post(MIEMBROS, headers=cabeceras, json=datos)).status_code == 409


async def test_el_listado_solo_muestra_miembros_propios(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.get(MIEMBROS, headers=cabeceras)
    assert respuesta.status_code == 200

    correos = {item["email"] for item in respuesta.json()["items"]}
    assert organizacion.owner_email in correos
    assert otra_organizacion.owner_email not in correos


async def test_no_se_puede_usar_un_rol_de_otra_organizacion(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        MIEMBROS,
        headers=cabeceras,
        json={
            "email": "intrusa@example.com",
            "first_name": "Intrusa",
            "last_name": "Prueba",
            "role_id": str(otra_organizacion.owner_role_id),
        },
    )
    assert respuesta.status_code == 404
