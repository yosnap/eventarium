"""`POST /auth/switch-organization`: cambio de organización activa sin volver a
loguearse, y las tres garantías de seguridad del red-team de la fase 1 del plan
«organización sin dominio» (`plans/260914-0741-organizacion-sin-dominio/`):

- S-1: no es una puerta trasera para que un superadmin entre en una
  organización de la que no es miembro (ese camino, auditado, es la
  impersonación).
- S-2: el mismo mensaje de error si la organización no existe o si existe
  pero no se pertenece a ella, para no poder enumerarlas.
- Verificación de impacto: una sesión de impersonación no puede llamar a este
  endpoint en ningún caso.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.core.permissions import Permission
from app.modules.organizations.models import OrganizationMember
from app.modules.roles.models import Role
from app.modules.roles.system_roles import OWNER_KEY
from app.modules.users.models import User
from tests.conftest import (
    OrganizacionDePrueba,
    crear_miembro,
    crear_rol,
    iniciar_sesion,
)

SWITCH = "/api/v1/auth/switch-organization"
IMPERSONATE = "/api/v1/admin/impersonate"


async def _hacer_superadmin(email: str) -> None:
    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == email))
        assert usuario is not None
        usuario.is_superadmin = True
        await session.commit()


async def _anadir_como_miembro(organizacion: OrganizacionDePrueba, email: str) -> None:
    """Añade a alguien que ya existe (de otra organización) como `owner` de esta."""
    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == email))
        assert usuario is not None
        rol = await session.scalar(
            select(Role).where(Role.organization_id == organizacion.id, Role.key == OWNER_KEY)
        )
        assert rol is not None
        session.add(
            OrganizationMember(
                organization_id=organizacion.id,
                user_id=usuario.id,
                role_id=rol.id,
                profile_data={},
            )
        )
        await session.commit()


async def _organization_id_del_token(cliente: AsyncClient, token: str) -> str:
    respuesta = await cliente.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert respuesta.status_code == 200, respuesta.text
    return str(respuesta.json()["organization_id"])


async def test_cambia_a_una_organizacion_a_la_que_se_pertenece(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    await _anadir_como_miembro(otra_organizacion, organizacion.owner_email)
    token, cabeceras = await iniciar_sesion(cliente, organizacion)
    assert await _organization_id_del_token(cliente, token) == str(organizacion.id)

    respuesta = await cliente.post(
        SWITCH, headers=cabeceras, json={"organization_id": str(otra_organizacion.id)}
    )
    assert respuesta.status_code == 200, respuesta.text
    nuevo_token = respuesta.json()["access_token"]
    assert await _organization_id_del_token(cliente, nuevo_token) == str(otra_organizacion.id)


async def test_cambiar_a_una_organizacion_ajena_da_el_mismo_error_que_una_inexistente(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    """No se pertenece a `otra_organizacion`: mismo 403 y mismo mensaje que un
    id que no corresponde a ninguna organización real."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    ajena = await cliente.post(
        SWITCH, headers=cabeceras, json={"organization_id": str(otra_organizacion.id)}
    )
    inexistente = await cliente.post(
        SWITCH, headers=cabeceras, json={"organization_id": str(uuid.uuid4())}
    )

    assert ajena.status_code == 403
    assert inexistente.status_code == 403
    assert ajena.json()["detail"] == inexistente.json()["detail"]


async def test_un_superadmin_sin_membresia_no_puede_cambiar_a_una_organizacion_ajena(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    """El único camino auditado para que un superadmin vea una organización
    de la que no es miembro es la impersonación, nunca `switch-organization`
    (red-team S-1)."""
    await _hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        SWITCH, headers=cabeceras, json={"organization_id": str(otra_organizacion.id)}
    )
    assert respuesta.status_code == 403


async def test_una_sesion_de_impersonacion_no_puede_cambiar_de_organizacion(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    """La persona suplantada pertenece **también** a `otra_organizacion`: si
    el bloqueo de la impersonación no existiera, `switch-organization`
    tendría todo lo que necesita para aceptar el cambio (membresía real). Que
    aun así se rechace prueba que el bloqueo es lo que realmente lo impide,
    no la falta de pertenencia."""
    await _hacer_superadmin(organizacion.owner_email)
    await crear_rol(organizacion, key="organizador_plano", permisos=[Permission.EVENTS_READ])
    persona = await crear_miembro(organizacion, "organizador_plano")
    await _anadir_como_miembro(otra_organizacion, persona.email)
    _, cabeceras_admin = await iniciar_sesion(cliente, organizacion)

    impersonacion = await cliente.post(
        IMPERSONATE,
        headers=cabeceras_admin,
        json={
            "user_id": str(persona.user_id),
            "organization_id": str(organizacion.id),
            "reason": "Comprobación de seguridad",
            "password": organizacion.owner_password,
        },
    )
    assert impersonacion.status_code == 201, impersonacion.text
    token_impersonado = impersonacion.json()["access_token"]

    respuesta = await cliente.post(
        SWITCH,
        headers={"Authorization": f"Bearer {token_impersonado}"},
        json={"organization_id": str(otra_organizacion.id)},
    )
    # 403 tanto si lo rechaza el bloqueo global de escritura durante la
    # impersonación (`bloquear_escritura_si_impersona`, que cubre toda la API)
    # como si lo rechazara la comprobación propia del endpoint: lo que importa
    # es que ninguna de las dos capas deje pasar el cambio, no cuál de ellas
    # responde primero.
    assert respuesta.status_code == 403
