"""Aceptación de invitaciones — fase 2 del plan de invitaciones (plan.md).

Cubre el correo propio (nunca «recupera tu contraseña»), la pantalla pública
de token (`GET`/`POST /public/invitations/{token}`), su idempotencia, los
tres mensajes distintos para token caducado/revocado/ya aceptado, y que la
respuesta pública nunca filtra datos de negocio.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.core.permissions import Permission
from app.core.security import hash_password
from app.core.tasks import send_invitation_email
from app.modules.organizations import invitations_service
from app.modules.organizations.invitations_models import OrganizationInvitation
from app.modules.organizations.models import OrganizationMember
from app.modules.roles.models import Role
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba

CONTRASENA_ACEPTAR = "Acepta-Esta-Invitacion-1!"


async def _role_id(organizacion: OrganizacionDePrueba, key: str) -> uuid.UUID:
    async with SessionMaintenance() as session:
        rol = await session.scalar(
            select(Role).where(Role.organization_id == organizacion.id, Role.key == key)
        )
        assert rol is not None, f"no existe el rol {key}"
        return rol.id


async def _crear_invitacion(
    organizacion: OrganizacionDePrueba, *, email: str, role_key: str = "organizer"
) -> tuple[uuid.UUID, str]:
    """Crea una invitación de verdad, saltándose la API, para obtener el token en claro."""
    role_id = await _role_id(organizacion, role_key)
    async with SessionMaintenance() as session:
        resultado = await invitations_service.create_invitation(
            session,
            organization_id=organizacion.id,
            actor_id=organizacion.owner_id,
            actor_permissions=set(Permission),
            email=email,
            role_id=role_id,
        )
        await session.commit()
    assert resultado.invitation is not None
    assert resultado.token is not None
    return resultado.invitation.id, resultado.token


async def test_send_invitation_email_no_dice_recupera_tu_contrasena() -> None:
    with (
        patch("app.core.tasks.get_email_provider") as proveedor_mock,
        patch("app.core.tasks.base_url_de_organizacion", return_value="https://acme.test"),
    ):
        proveedor = AsyncMock()
        proveedor_mock.return_value = proveedor
        await send_invitation_email.original_func(
            "invitada@example.com",
            "token-de-prueba",
            "00000000-0000-0000-0000-000000000000",
            "Acme",
            "Organizador",
        )

    proveedor.send.assert_awaited_once()
    _args, kwargs = proveedor.send.call_args
    asunto = kwargs.get("subject", "")
    cuerpo = kwargs.get("body", "")
    texto_completo = f"{asunto} {cuerpo}".lower()

    assert "te han invitado" in texto_completo or "invitado" in texto_completo
    assert "recupera tu contraseña" not in texto_completo
    assert "/invitacion?token=token-de-prueba" in cuerpo
    assert "/recuperar-contrasena" not in cuerpo


async def test_get_invitation_devuelve_lo_minimo(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _invitation_id, token = await _crear_invitacion(organizacion, email="pendiente@example.com")

    respuesta = await cliente.get(f"/api/v1/public/invitations/{token}")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert set(cuerpo.keys()) == {"organization_name", "role_name", "account_has_password"}
    assert cuerpo["role_name"] == "Organizador"
    assert cuerpo["account_has_password"] is False


async def test_aceptar_fija_contrasena_nombre_y_crea_la_membresia(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    invitation_id, token = await _crear_invitacion(organizacion, email="nueva-persona@example.com")

    respuesta = await cliente.post(
        f"/api/v1/public/invitations/{token}/accept",
        json={"first_name": "Ada", "last_name": "Lovelace", "password": CONTRASENA_ACEPTAR},
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"organization_slug": organizacion.slug}

    async with SessionMaintenance() as session:
        usuario = await session.scalar(
            select(User).where(User.email == "nueva-persona@example.com")
        )
        assert usuario is not None
        assert usuario.password_hash is not None
        assert usuario.first_name == "Ada"
        assert usuario.last_name == "Lovelace"
        assert usuario.email_verified_at is not None

        miembro = await session.scalar(
            select(OrganizationMember).where(OrganizationMember.user_id == usuario.id)
        )
        assert miembro is not None
        assert miembro.organization_id == organizacion.id

    login = await cliente.post(
        "/api/v1/auth/login",
        json={"email": "nueva-persona@example.com", "password": CONTRASENA_ACEPTAR},
    )
    assert login.status_code == 200, login.text

    # El token consumido con `GET` ahora refleja el estado «ya aceptada».
    tras_aceptar = await cliente.get(f"/api/v1/public/invitations/{token}")
    assert tras_aceptar.status_code == 404
    assert "ya se aceptó" in tras_aceptar.json()["detail"]


async def test_aceptar_dos_veces_no_duplica_la_membresia(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _invitation_id, token = await _crear_invitacion(organizacion, email="doble-clic@example.com")
    datos = {"first_name": "Doble", "last_name": "Clic", "password": CONTRASENA_ACEPTAR}

    primera = await cliente.post(
        f"/api/v1/public/invitations/{token}/accept",
        json=datos,
    )
    segunda = await cliente.post(
        f"/api/v1/public/invitations/{token}/accept",
        json=datos,
    )

    assert primera.status_code == 200, primera.text
    assert segunda.status_code == 200, segunda.text

    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == "doble-clic@example.com"))
        assert usuario is not None
        membresias = (
            await session.scalars(
                select(OrganizationMember).where(OrganizationMember.user_id == usuario.id)
            )
        ).all()
        assert len(membresias) == 1


async def test_aceptar_con_locale_valido_lo_persiste(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Fase 2 (plan `261019-1343`): `locale` explícito en la aceptación se guarda
    en la cuenta, igual que en el registro de fase 1."""
    _invitation_id, token = await _crear_invitacion(organizacion, email="con-idioma@example.com")

    respuesta = await cliente.post(
        f"/api/v1/public/invitations/{token}/accept",
        json={
            "first_name": "Con",
            "last_name": "Idioma",
            "password": CONTRASENA_ACEPTAR,
            "locale": "en-US",
        },
    )
    assert respuesta.status_code == 200, respuesta.text

    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == "con-idioma@example.com"))
    assert usuario is not None
    assert usuario.locale == "en-US"


async def test_aceptar_sin_locale_usa_es_es_por_defecto(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Fase 2: si se omite `locale`, la cuenta queda en `'es-ES'`."""
    _invitation_id, token = await _crear_invitacion(organizacion, email="sin-idioma@example.com")

    respuesta = await cliente.post(
        f"/api/v1/public/invitations/{token}/accept",
        json={"first_name": "Sin", "last_name": "Idioma", "password": CONTRASENA_ACEPTAR},
    )
    assert respuesta.status_code == 200, respuesta.text

    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == "sin-idioma@example.com"))
    assert usuario is not None
    assert usuario.locale == "es-ES"


async def test_aceptar_con_locale_invalido_devuelve_422(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Fase 2: `locale` fuera del catálogo `Literal["es-ES", "en-US"]` es 422."""
    _invitation_id, token = await _crear_invitacion(organizacion, email="idioma-malo@example.com")

    respuesta = await cliente.post(
        f"/api/v1/public/invitations/{token}/accept",
        json={
            "first_name": "Idioma",
            "last_name": "Malo",
            "password": CONTRASENA_ACEPTAR,
            "locale": "fr-FR",
        },
    )
    assert respuesta.status_code == 422


async def test_aceptar_dos_veces_con_locale_distinto_no_cambia_el_ya_fijado(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Fase 2, idempotencia: la segunda aceptación (rama temprana de
    `invitations_service.py`, invitación ya `aceptada`) no reescribe la cuenta,
    así que el `locale` de la primera llamada se mantiene aunque la segunda pida
    otro distinto."""
    _invitation_id, token = await _crear_invitacion(
        organizacion, email="doble-clic-idioma@example.com"
    )
    datos_base = {"first_name": "Doble", "last_name": "Idioma", "password": CONTRASENA_ACEPTAR}

    primera = await cliente.post(
        f"/api/v1/public/invitations/{token}/accept",
        json={**datos_base, "locale": "en-US"},
    )
    segunda = await cliente.post(
        f"/api/v1/public/invitations/{token}/accept",
        json={**datos_base, "locale": "es-ES"},
    )
    assert primera.status_code == 200, primera.text
    assert segunda.status_code == 200, segunda.text

    async with SessionMaintenance() as session:
        usuario = await session.scalar(
            select(User).where(User.email == "doble-clic-idioma@example.com")
        )
    assert usuario is not None
    assert usuario.locale == "en-US"


async def test_token_caducado_revocado_y_aceptado_dan_mensajes_distintos(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _id_caducada, token_caducado = await _crear_invitacion(
        organizacion, email="caducada@example.com"
    )
    async with SessionMaintenance() as session:
        invitacion = await session.get(OrganizationInvitation, _id_caducada)
        assert invitacion is not None
        invitacion.expires_at = datetime.now(UTC) - timedelta(days=1)
        await session.commit()

    id_revocada, token_revocado = await _crear_invitacion(
        organizacion, email="revocada@example.com"
    )
    async with SessionMaintenance() as session:
        await invitations_service.revoke_invitation(
            session, organization_id=organizacion.id, invitation_id=id_revocada
        )
        await session.commit()

    _id_aceptada, token_aceptado = await _crear_invitacion(
        organizacion, email="ya-aceptada@example.com"
    )
    await cliente.post(
        f"/api/v1/public/invitations/{token_aceptado}/accept",
        json={"first_name": "Ya", "last_name": "Aceptada", "password": CONTRASENA_ACEPTAR},
    )

    respuesta_caducada = await cliente.get(f"/api/v1/public/invitations/{token_caducado}")
    respuesta_revocada = await cliente.get(f"/api/v1/public/invitations/{token_revocado}")
    respuesta_aceptada = await cliente.get(f"/api/v1/public/invitations/{token_aceptado}")
    respuesta_invalida = await cliente.get("/api/v1/public/invitations/token-que-nunca-existio")

    mensajes = {
        r.json()["detail"]
        for r in (respuesta_caducada, respuesta_revocada, respuesta_aceptada, respuesta_invalida)
    }
    assert all(
        r.status_code == 404
        for r in (respuesta_caducada, respuesta_revocada, respuesta_aceptada, respuesta_invalida)
    )
    assert len(mensajes) == 4  # las cuatro respuestas dicen algo distinto


async def test_correo_con_contrasena_ya_puesta_no_puede_aceptar(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Caso anómalo: la fase 1 no emite token con cuenta existente, pero
    puede ganar contraseña después por otra vía (p. ej. una recuperación)."""
    invitation_id, token = await _crear_invitacion(organizacion, email="con-clave@example.com")
    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == "con-clave@example.com"))
        assert usuario is not None
        usuario.password_hash = hash_password("ya-tengo-contraseña-1A!")
        await session.commit()

    consulta = await cliente.get(f"/api/v1/public/invitations/{token}")
    assert consulta.status_code == 200
    assert consulta.json()["account_has_password"] is True

    aceptar = await cliente.post(
        f"/api/v1/public/invitations/{token}/accept",
        json={"first_name": "Con", "last_name": "Clave", "password": CONTRASENA_ACEPTAR},
    )
    assert aceptar.status_code == 409, aceptar.text
