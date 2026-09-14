"""Invitación de equipo — fase 1 del plan de invitaciones (plan.md).

Cubre las dos reglas duras del hallazgo S-1 del red-team (correo con cuenta
nunca emite token; correo sin cuenta crea invitación + cuenta sin
contraseña), la separación de propósitos de token, las reglas anti-escalada
compartidas con `add_member`, el aislamiento RLS, el reenvío que invalida el
token anterior, y el `ON DELETE CASCADE` de `role_id`.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.core.permissions import Permission
from app.core.security import hash_password
from app.modules.auth.verification import (
    PROPOSITO_INVITACION,
    PROPOSITO_RECUPERAR_CONTRASENA,
    consume_token,
    generate_token,
    peek_token,
)
from app.modules.organizations import invitations_service
from app.modules.organizations.invitations_models import OrganizationInvitation
from app.modules.organizations.models import OrganizationMember
from app.modules.roles.models import Role
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, crear_rol, iniciar_sesion, iniciar_sesion_como

INVITACIONES = "/api/v1/organizations/me/invitations"
RESET = "/api/v1/auth/reset-password"
ROLES = "/api/v1/roles"


async def _role_id(organizacion: OrganizacionDePrueba, key: str) -> uuid.UUID:
    async with SessionMaintenance() as session:
        rol = await session.scalar(
            select(Role).where(Role.organization_id == organizacion.id, Role.key == key)
        )
        assert rol is not None, f"no existe el rol {key}"
        return rol.id


async def test_invitar_correo_sin_cuenta_crea_invitacion_y_cuenta_sin_contrasena(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    role_id = await _role_id(organizacion, "organizer")

    respuesta = await cliente.post(
        INVITACIONES,
        json={"email": "nueva@ejemplo.com", "role_id": str(role_id)},
        headers=cabeceras,
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "invited"
    assert cuerpo["invitation"]["email"] == "nueva@ejemplo.com"
    assert cuerpo["invitation"]["estado"] == "pendiente"
    assert cuerpo["invitation"]["role_key"] == "organizer"

    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == "nueva@ejemplo.com"))
        assert usuario is not None
        assert usuario.password_hash is None  # cuenta sin contraseña, como `add_member`

        miembro = await session.scalar(
            select(OrganizationMember).where(OrganizationMember.user_id == usuario.id)
        )
        assert miembro is None  # la membresía nace al aceptar (fase 2), no aquí

        invitacion = await session.scalar(
            select(OrganizationInvitation).where(
                OrganizationInvitation.email == "nueva@ejemplo.com"
            )
        )
        assert invitacion is not None
        assert invitacion.estado == "pendiente"
        assert invitacion.token_hash is not None  # huella guardada, no el token


async def test_invitar_correo_con_cuenta_anade_directamente_sin_invitacion_ni_token(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    async with SessionMaintenance() as session:
        usuario = User(
            email="yatiene@ejemplo.com",
            first_name="Ya",
            last_name="Tiene",
            password_hash=hash_password("una-contraseña-cualquiera"),
            is_active=True,
        )
        session.add(usuario)
        await session.commit()

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    role_id = await _role_id(organizacion, "organizer")

    respuesta = await cliente.post(
        INVITACIONES,
        json={"email": "yatiene@ejemplo.com", "role_id": str(role_id)},
        headers=cabeceras,
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "added"
    assert cuerpo["invitation"] is None
    assert cuerpo["member"]["email"] == "yatiene@ejemplo.com"

    async with SessionMaintenance() as session:
        invitaciones = (
            await session.scalars(
                select(OrganizationInvitation).where(
                    OrganizationInvitation.email == "yatiene@ejemplo.com"
                )
            )
        ).all()
        assert len(invitaciones) == 0  # regla dura: ninguna invitación, ningún token


async def test_la_respuesta_no_incluye_el_token_en_ningun_caso(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    role_id = await _role_id(organizacion, "organizer")

    with patch(
        "app.modules.organizations.invitations_service.generate_token",
        new=AsyncMock(return_value="token-secreto-de-prueba-1234567890"),
    ):
        respuesta = await cliente.post(
            INVITACIONES,
            json={"email": "sinfiltrar@ejemplo.com", "role_id": str(role_id)},
            headers=cabeceras,
        )

    assert respuesta.status_code == 201, respuesta.text
    assert "token-secreto-de-prueba-1234567890" not in respuesta.text
    assert "token" not in respuesta.json()["invitation"]


async def test_un_token_de_invitacion_no_sirve_para_recuperar_contrasena(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    token = await generate_token(PROPOSITO_INVITACION, "cualquier-payload")
    respuesta = await cliente.post(
        RESET,
        json={"token": token, "new_password": "Otra-Contraseña-Larga-1!"},
    )
    assert respuesta.status_code == 422


async def test_un_token_de_recuperacion_no_sirve_para_invitacion() -> None:
    token = await generate_token(PROPOSITO_RECUPERAR_CONTRASENA, "cualquier-payload")
    assert await consume_token(PROPOSITO_INVITACION, token) is None


async def test_un_organizer_no_puede_invitar_con_rol_owner(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion_como(cliente, organizacion, "organizer")
    owner_role_id = await _role_id(organizacion, "owner")

    respuesta = await cliente.post(
        INVITACIONES,
        json={"email": "aspirante-a-owner@ejemplo.com", "role_id": str(owner_role_id)},
        headers=cabeceras,
    )
    assert respuesta.status_code == 403, respuesta.text


async def test_no_se_puede_invitar_con_un_rol_de_otra_organizacion(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    role_id_ajeno = await _role_id(otra_organizacion, "organizer")

    respuesta = await cliente.post(
        INVITACIONES,
        json={"email": "quien-sea@ejemplo.com", "role_id": str(role_id_ajeno)},
        headers=cabeceras,
    )
    assert respuesta.status_code == 404, respuesta.text


async def test_dos_organizaciones_no_ven_las_invitaciones_de_la_otra(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    role_id = await _role_id(organizacion, "organizer")
    await cliente.post(
        INVITACIONES,
        json={"email": "aislada@ejemplo.com", "role_id": str(role_id)},
        headers=cabeceras,
    )

    propias = await cliente.get(INVITACIONES, headers=cabeceras)
    assert propias.status_code == 200
    assert any(fila["email"] == "aislada@ejemplo.com" for fila in propias.json())

    _, cabeceras_ajenas = await iniciar_sesion(cliente, otra_organizacion)
    ajenas = await cliente.get(INVITACIONES, headers=cabeceras_ajenas)
    assert ajenas.status_code == 200
    assert all(fila["email"] != "aislada@ejemplo.com" for fila in ajenas.json())


async def test_reenviar_emite_un_token_nuevo_e_invalida_el_anterior(
    organizacion: OrganizacionDePrueba,
) -> None:
    async with SessionMaintenance() as session:
        role_id = await _role_id(organizacion, "organizer")
        resultado = await invitations_service.create_invitation(
            session,
            organization_id=organizacion.id,
            actor_id=organizacion.owner_id,
            actor_permissions=set(Permission),
            email="reenviada@ejemplo.com",
            role_id=role_id,
        )
        await session.commit()
        assert resultado.invitation is not None
        assert resultado.token is not None
        token_viejo = resultado.token
        invitation_id = resultado.invitation.id

    assert await peek_token(PROPOSITO_INVITACION, token_viejo) is not None

    async with SessionMaintenance() as session:
        invitacion_nueva, token_nuevo = await invitations_service.resend_invitation(
            session, organization_id=organizacion.id, invitation_id=invitation_id
        )
        await session.commit()

    assert token_nuevo != token_viejo
    assert await peek_token(PROPOSITO_INVITACION, token_viejo) is None  # invalidado
    assert await peek_token(PROPOSITO_INVITACION, token_nuevo) is not None
    assert invitacion_nueva.token_hash is not None


async def test_borrar_un_rol_cancela_sus_invitaciones_pendientes(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    role_id = await crear_rol(
        organizacion, key="finanzas", permisos=[Permission.ACCOUNTING_READ]
    )

    async with SessionMaintenance() as session:
        resultado = await invitations_service.create_invitation(
            session,
            organization_id=organizacion.id,
            actor_id=organizacion.owner_id,
            actor_permissions=set(Permission),
            email="futuro-finanzas@ejemplo.com",
            role_id=role_id,
        )
        await session.commit()
        invitation_id = resultado.invitation.id  # type: ignore[union-attr]

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.delete(f"{ROLES}/{role_id}", headers=cabeceras)
    assert respuesta.status_code == 204, respuesta.text

    async with SessionMaintenance() as session:
        invitacion = await session.scalar(
            select(OrganizationInvitation).where(OrganizationInvitation.id == invitation_id)
        )
        assert invitacion is None  # `ON DELETE CASCADE` de `role_id`
