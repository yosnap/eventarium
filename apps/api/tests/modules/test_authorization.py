"""Reglas anti-escalada de privilegios.

Sin ellas, `roles:write` equivaldría a control total: bastaría con crearse un rol con
todos los permisos y asignárselo.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.database import SessionMaintenance
from app.core.permissions import Permission
from app.modules.organizations.models import OrganizationMember
from app.modules.roles.authorization import (
    ensure_can_grant,
    ensure_can_manage_role,
    ensure_not_self_escalation,
)
from app.modules.roles.models import Role
from app.shared.errors import PermissionDeniedError
from tests.conftest import (
    OrganizacionDePrueba,
    crear_rol,
    iniciar_sesion,
    iniciar_sesion_como,
)


def test_no_se_pueden_conceder_permisos_que_no_se_tienen() -> None:
    with pytest.raises(PermissionDeniedError):
        ensure_can_grant({Permission.ROLES_READ}, {Permission.ROLES_WRITE})


def test_se_pueden_conceder_los_permisos_propios() -> None:
    ensure_can_grant({Permission.ROLES_READ, Permission.ROLES_WRITE}, {Permission.ROLES_READ})


def test_solo_un_owner_gestiona_el_rol_owner() -> None:
    with pytest.raises(PermissionDeniedError):
        ensure_can_manage_role(
            actor_role_keys={"organizer"}, role_key="owner", es_rol_de_sistema=True
        )
    ensure_can_manage_role(actor_role_keys={"owner"}, role_key="owner", es_rol_de_sistema=True)


def test_no_se_pueden_ampliar_los_permisos_propios() -> None:
    actor = uuid.uuid4()
    with pytest.raises(PermissionDeniedError):
        ensure_not_self_escalation(
            actor_id=actor,
            target_user_id=actor,
            permisos_nuevos={Permission.ROLES_WRITE},
            permisos_actor={Permission.ROLES_READ},
        )


def test_ampliar_los_permisos_de_otra_persona_no_es_auto_escalada() -> None:
    ensure_not_self_escalation(
        actor_id=uuid.uuid4(),
        target_user_id=uuid.uuid4(),
        permisos_nuevos={Permission.ROLES_WRITE},
        permisos_actor={Permission.ROLES_READ},
    )


async def test_crear_un_rol_con_permisos_que_el_actor_no_tiene_devuelve_403(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Un coordinador puede gestionar roles, pero no repartir lo que no posee."""
    await crear_rol(
        organizacion,
        key="coordinador",
        permisos=[Permission.ROLES_READ, Permission.ROLES_WRITE, Permission.MEMBERS_READ],
    )
    _, cabeceras = await iniciar_sesion_como(cliente, organizacion, "coordinador")

    respuesta = await cliente.post(
        "/api/v1/roles",
        headers=cabeceras,
        json={
            "key": "superpoderes",
            "name": "Superpoderes",
            "permissions": [Permission.BRANDING_WRITE.value],
        },
    )
    assert respuesta.status_code == 403
    assert Permission.BRANDING_WRITE.value in respuesta.json()["permisos_no_permitidos"]


async def test_un_coordinador_si_puede_conceder_sus_propios_permisos(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await crear_rol(
        organizacion,
        key="coordinador",
        permisos=[Permission.ROLES_READ, Permission.ROLES_WRITE],
    )
    _, cabeceras = await iniciar_sesion_como(cliente, organizacion, "coordinador")

    respuesta = await cliente.post(
        "/api/v1/roles",
        headers=cabeceras,
        json={
            "key": "ayudante",
            "name": "Ayudante",
            "permissions": [Permission.ROLES_READ.value],
        },
    )
    assert respuesta.status_code == 201


async def test_un_asistente_no_puede_crear_roles(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """`attendee` no tiene `roles:write`: se rechaza antes de mirar los permisos pedidos."""
    _, cabeceras = await iniciar_sesion_como(cliente, organizacion, "attendee")
    respuesta = await cliente.post(
        "/api/v1/roles",
        headers=cabeceras,
        json={"key": "presentador", "name": "Presentador"},
    )
    assert respuesta.status_code == 403


async def test_un_organizador_no_puede_asignar_el_rol_owner(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion_como(cliente, organizacion, "organizer")

    async with SessionMaintenance() as session:
        rol_owner = await session.scalar(
            select(Role).where(Role.organization_id == organizacion.id, Role.key == "owner")
        )
        assert rol_owner is not None
        rol_owner_id = rol_owner.id

    respuesta = await cliente.post(
        "/api/v1/organizations/me/members",
        headers=cabeceras,
        json={
            "email": "aspirante@example.com",
            "full_name": "Aspirante",
            "role_id": str(rol_owner_id),
        },
    )
    assert respuesta.status_code == 403

    async with SessionMaintenance() as session:
        propietarios = await session.scalar(
            select(func.count())
            .select_from(OrganizationMember)
            .where(OrganizationMember.role_id == rol_owner_id)
        )
    assert propietarios == 1, "no debe haberse creado un segundo propietario"


async def test_el_owner_si_puede_asignar_el_rol_owner(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        "/api/v1/organizations/me/members",
        headers=cabeceras,
        json={
            "email": "cofundadora@example.com",
            "full_name": "Cofundadora",
            "role_id": str(organizacion.owner_role_id),
        },
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["role_key"] == "owner"
