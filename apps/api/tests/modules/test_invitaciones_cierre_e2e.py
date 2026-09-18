"""Cierre del plan de invitaciones (fase 5): el caso entre organizaciones.

Los otros cinco casos de extremo a extremo que pide la fase ya están
cubiertos, cada uno en su fase — no se duplican aquí (`no se rediseña nada:
se verifica y se documenta`, `phase-05-cierre.md`):

- **El caso nunca ejercitado** (invitar sin cuenta, aceptar, fijar
  contraseña, entrar, tener el rol): `test_invitaciones_aceptacion.py::
  test_aceptar_fija_contrasena_nombre_y_crea_la_membresia`, con `login`
  real al final.
- **El caso del correo con cuenta**: `test_invitaciones.py::
  test_invitar_correo_con_cuenta_anade_directamente_sin_invitacion_ni_token`.
- **Los papeles acumulables** (una fila, dos roles): `test_members_roles.py::
  test_una_persona_con_dos_roles_aparece_una_vez_con_los_dos`.
- **El token cruzado**: `test_invitaciones_aceptacion.py::
  test_un_token_de_invitacion_no_sirve_para_recuperar_contrasena` y
  `test_un_token_de_recuperacion_no_sirve_para_invitacion`.
- **El `ON DELETE CASCADE`**: `test_invitaciones.py::
  test_borrar_un_rol_cancela_sus_invitaciones_pendientes`.
- **Aislamiento entre organizaciones** (invitaciones): `test_invitaciones.py::
  test_dos_organizaciones_no_ven_las_invitaciones_de_la_otra` y
  `test_invitaciones_aceptacion.py::
  test_dos_organizaciones_no_ven_la_invitacion_de_la_otra_por_host`.
- **`organizer` no puede invitar `owner`, contra la API**:
  `test_invitaciones.py::test_un_organizer_no_puede_invitar_con_rol_owner`.
- **La pantalla pública no filtra de más**: `test_invitaciones_aceptacion.py::
  test_get_invitation_devuelve_lo_minimo`.

El caso que sí faltaba, porque ninguna fase anterior lo necesitó completo:
la misma persona invitada como ponente en **dos organizaciones distintas**
es un solo usuario, y su ficha (`profile_data`) es independiente en cada una
— justo lo que dice `docs/investigacion.md`/el PRD sobre `users` siendo
global a la instalación.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.core.permissions import Permission
from app.modules.organizations import invitations_service
from app.modules.organizations.models import OrganizationMember
from app.modules.roles.models import Role
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba

CONTRASENA_ACEPTAR = "Acepta-Esta-Invitacion-1!"
CORREO_PONENTE_ITINERANTE = "ponente-itinerante@example.com"


async def _role_id(organizacion: OrganizacionDePrueba, key: str) -> uuid.UUID:
    async with SessionMaintenance() as session:
        rol = await session.scalar(
            select(Role).where(Role.organization_id == organizacion.id, Role.key == key)
        )
        assert rol is not None, f"no existe el rol {key}"
        return rol.id


async def test_la_misma_persona_es_ponente_en_dos_organizaciones_sin_duplicar_cuenta(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    # 1) Invitada como ponente en la primera organización — no tiene cuenta,
    #    así que se crea la invitación y, al aceptar, la cuenta.
    role_id_a = await _role_id(organizacion, "speaker")
    async with SessionMaintenance() as session:
        resultado_a = await invitations_service.create_invitation(
            session,
            organization_id=organizacion.id,
            actor_id=organizacion.owner_id,
            actor_permissions=set(Permission),
            email=CORREO_PONENTE_ITINERANTE,
            role_id=role_id_a,
        )
        await session.commit()
    assert resultado_a.token is not None

    aceptar_a = await cliente.post(
        f"/api/v1/public/invitations/{resultado_a.token}/accept",
        json={"first_name": "Ponente", "last_name": "Itinerante", "password": CONTRASENA_ACEPTAR},
    )
    assert aceptar_a.status_code == 200, aceptar_a.text

    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == CORREO_PONENTE_ITINERANTE))
        assert usuario is not None
        user_id = usuario.id

        miembro_a = await session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organizacion.id,
                OrganizationMember.user_id == user_id,
            )
        )
        assert miembro_a is not None
        miembro_a.profile_data = {"bio": "Bio en la primera organización"}
        await session.commit()

    # 2) Invitada como ponente en la segunda organización — el correo **ya
    #    tiene cuenta** (la que se acaba de crear arriba), así que la regla
    #    dura de la fase 1 aplica: se añade directamente, sin token.
    role_id_b = await _role_id(otra_organizacion, "speaker")
    async with SessionMaintenance() as session:
        resultado_b = await invitations_service.create_invitation(
            session,
            organization_id=otra_organizacion.id,
            actor_id=otra_organizacion.owner_id,
            actor_permissions=set(Permission),
            email=CORREO_PONENTE_ITINERANTE,
            role_id=role_id_b,
        )
        await session.commit()

    assert resultado_b.token is None  # regla dura: correo con cuenta, sin token
    assert resultado_b.member is not None
    assert resultado_b.member.user_id == user_id  # el mismo usuario, no uno nuevo

    async with SessionMaintenance() as session:
        miembro_b = await session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == otra_organizacion.id,
                OrganizationMember.user_id == user_id,
            )
        )
        assert miembro_b is not None
        miembro_b.profile_data = {"bio": "Bio distinta en la segunda organización"}
        await session.commit()

    # 3) Un solo usuario en `users`, dos membresías, dos fichas independientes.
    async with SessionMaintenance() as session:
        usuarios = (
            await session.scalars(select(User).where(User.email == CORREO_PONENTE_ITINERANTE))
        ).all()
        assert len(usuarios) == 1

        miembro_a = await session.get(OrganizationMember, miembro_a.id)
        miembro_b = await session.get(OrganizationMember, miembro_b.id)
        assert miembro_a is not None and miembro_b is not None
        assert miembro_a.profile_data["bio"] != miembro_b.profile_data["bio"]

    # 4) La cuenta única entra con la misma contraseña en las dos organizaciones.
    login_a = await cliente.post(
        "/api/v1/auth/login",
        json={"email": CORREO_PONENTE_ITINERANTE, "password": CONTRASENA_ACEPTAR},
    )
    assert login_a.status_code == 200, login_a.text

    login_b = await cliente.post(
        "/api/v1/auth/login",
        json={"email": CORREO_PONENTE_ITINERANTE, "password": CONTRASENA_ACEPTAR},
    )
    assert login_b.status_code == 200, login_b.text
