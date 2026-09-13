"""Varios roles por persona en la interfaz — fase 4 del plan de invitaciones.

El listado agrupa por persona (`MemberResponse.roles`), no por fila de
membresía: cubre que una persona con dos roles aparezca una vez, que la
paginación cuente personas, y el alta/baja de un rol sin sacar a nadie de la
organización — con el último rol bloqueado.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.core.permissions import Permission
from app.modules.organizations import members_service
from app.modules.organizations.models import OrganizationMember
from app.modules.roles.models import Role
from tests.conftest import OrganizacionDePrueba, iniciar_sesion, iniciar_sesion_como

MIEMBROS = "/api/v1/organizations/me/members"


async def _role_id(organizacion: OrganizacionDePrueba, key: str) -> uuid.UUID:
    async with SessionMaintenance() as session:
        rol = await session.scalar(
            select(Role).where(Role.organization_id == organizacion.id, Role.key == key)
        )
        assert rol is not None, f"no existe el rol {key}"
        return rol.id


async def _anadir_rol(
    organizacion: OrganizacionDePrueba, *, email: str, role_key: str
) -> uuid.UUID:
    """Añade un rol a una persona (nueva o existente), saltándose la API."""
    role_id = await _role_id(organizacion, role_key)
    async with SessionMaintenance() as session:
        miembro = await members_service.add_member(
            session,
            organization_id=organizacion.id,
            actor_id=organizacion.owner_id,
            actor_permissions=set(Permission),
            email=email,
            first_name="Persona",
            last_name="De Prueba",
            role_id=role_id,
            profile_data={},
        )
        await session.commit()
        return miembro.id


async def test_una_persona_con_dos_roles_aparece_una_vez_con_los_dos(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _anadir_rol(organizacion, email="doble-rol@example.com", role_key="organizer")
    await _anadir_rol(organizacion, email="doble-rol@example.com", role_key="volunteer")

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.get(MIEMBROS, headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text

    filas = [item for item in respuesta.json()["items"] if item["email"] == "doble-rol@example.com"]
    assert len(filas) == 1
    claves = sorted(rol["role_key"] for rol in filas[0]["roles"])
    assert claves == ["organizer", "volunteer"]


async def test_anadir_un_rol_a_alguien_existente_no_lo_duplica_en_la_lista(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    role_id_speaker = await _role_id(organizacion, "speaker")

    primera = await cliente.post(
        MIEMBROS,
        headers=cabeceras,
        json={
            "email": "acumula-roles@example.com",
            "first_name": "Acumula",
            "last_name": "Roles",
            "role_id": str(role_id_speaker),
            "profile_data": {
                "bio": "Bio",
                "web": "https://ejemplo.com",
                "contacto": "acumula@example.com",
            },
        },
    )
    assert primera.status_code == 201, primera.text
    assert len(primera.json()["roles"]) == 1

    role_id_volunteer = await _role_id(organizacion, "volunteer")
    segunda = await cliente.post(
        MIEMBROS,
        headers=cabeceras,
        json={
            "email": "acumula-roles@example.com",
            "first_name": "Acumula",
            "last_name": "Roles",
            "role_id": str(role_id_volunteer),
        },
    )
    assert segunda.status_code == 201, segunda.text
    # La respuesta ya trae a la persona con sus dos roles, no solo el nuevo.
    assert sorted(r["role_key"] for r in segunda.json()["roles"]) == ["speaker", "volunteer"]

    listado = await cliente.get(MIEMBROS, headers=cabeceras)
    filas = [
        item for item in listado.json()["items"] if item["email"] == "acumula-roles@example.com"
    ]
    assert len(filas) == 1


async def test_la_paginacion_cuenta_personas_no_membresias(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    # La organización ya trae al owner (1 persona). Añadimos 19 personas más de
    # un solo rol y una con dos roles: 21 personas, 22 filas de membresía.
    for indice in range(19):
        await _anadir_rol(organizacion, email=f"persona-{indice}@example.com", role_key="attendee")
    await _anadir_rol(organizacion, email="con-dos@example.com", role_key="organizer")
    await _anadir_rol(organizacion, email="con-dos@example.com", role_key="volunteer")

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.get(MIEMBROS, headers=cabeceras, params={"limit": 20, "offset": 0})
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()

    assert cuerpo["total"] == 21  # personas, no las 22 filas de membresía
    assert len(cuerpo["items"]) == 20  # la página se llena de personas completas

    segunda_pagina = await cliente.get(
        MIEMBROS, headers=cabeceras, params={"limit": 20, "offset": 20}
    )
    assert len(segunda_pagina.json()["items"]) == 1


async def test_quitar_un_rol_deja_los_demas_intactos(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _anadir_rol(organizacion, email="dos-roles-quitar@example.com", role_key="organizer")
    membership_id_volunteer = await _anadir_rol(
        organizacion, email="dos-roles-quitar@example.com", role_key="volunteer"
    )

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.delete(
        f"{MIEMBROS}/{membership_id_volunteer}", headers=cabeceras
    )
    assert respuesta.status_code == 204, respuesta.text

    listado = await cliente.get(MIEMBROS, headers=cabeceras)
    fila = next(
        item
        for item in listado.json()["items"]
        if item["email"] == "dos-roles-quitar@example.com"
    )
    assert [r["role_key"] for r in fila["roles"]] == ["organizer"]


async def test_quitar_el_ultimo_rol_esta_bloqueado(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    membership_id = await _anadir_rol(
        organizacion, email="un-solo-rol@example.com", role_key="attendee"
    )

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.delete(f"{MIEMBROS}/{membership_id}", headers=cabeceras)
    assert respuesta.status_code == 409, respuesta.text

    async with SessionMaintenance() as session:
        miembro = await session.get(OrganizationMember, membership_id)
        assert miembro is not None  # sigue ahí: no se ha borrado nada


async def test_no_se_puede_quitar_un_rol_de_otra_organizacion(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    membership_id_ajeno = await _anadir_rol(
        otra_organizacion, email="ajena@example.com", role_key="organizer"
    )
    await _anadir_rol(otra_organizacion, email="ajena@example.com", role_key="volunteer")

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.delete(f"{MIEMBROS}/{membership_id_ajeno}", headers=cabeceras)
    assert respuesta.status_code == 404, respuesta.text


async def test_un_organizer_no_puede_quitar_el_rol_owner_de_otra_persona(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    membership_id_owner = await _anadir_rol(
        organizacion, email="segunda-owner@example.com", role_key="owner"
    )
    await _anadir_rol(organizacion, email="segunda-owner@example.com", role_key="volunteer")

    _, cabeceras = await iniciar_sesion_como(cliente, organizacion, "organizer")
    respuesta = await cliente.delete(f"{MIEMBROS}/{membership_id_owner}", headers=cabeceras)
    assert respuesta.status_code == 403, respuesta.text
