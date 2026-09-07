"""Autoservicio de creación de organizaciones: de una cuenta verificada a `owner`."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.core.tasks import send_verification_email
from app.modules.auth.verification import PROPOSITO_VERIFICACION_CORREO, generate_token
from tests.conftest import OrganizacionDePrueba

REGISTER = "/api/v1/auth/register"
VERIFY = "/api/v1/auth/verify-email"
CHECK_SLUG = "/api/v1/organizations/check-slug"
CREAR = "/api/v1/organizations"
LOGIN = "/api/v1/auth/login"

CONTRASENA = "OrgFuerte1!"


async def _registrar_y_verificar(
    cliente: AsyncClient, host: str, app_db: AsyncSession, email: str
) -> str:
    """Registra, verifica y devuelve el access token puente (sin organización)."""
    with (
        patch("app.modules.auth.service._password_filtrada", return_value=False),
        patch.object(send_verification_email, "kiq", new_callable=AsyncMock),
    ):
        respuesta = await cliente.post(
            REGISTER,
            json={"email": email, "password": CONTRASENA, "turnstile_token": ""},
            headers={"Host": host},
        )
        assert respuesta.status_code == 202, respuesta.text

    fila = (
        await app_db.execute(
            text("SELECT id FROM app_find_user_by_email(:email)"), {"email": email}
        )
    ).first()
    assert fila is not None
    token = await generate_token(PROPOSITO_VERIFICACION_CORREO, fila[0])

    verificacion = await cliente.get(VERIFY, params={"token": token}, headers={"Host": host})
    assert verificacion.status_code == 200, verificacion.text
    return str(verificacion.json()["access_token"])


async def test_flujo_completo_deja_a_la_persona_como_owner(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, app_db: AsyncSession
) -> None:
    """De cuenta verificada a organización operativa: crea, y después inicia sesión."""
    email = "nueva-organizadora@example.com"
    bridge = await _registrar_y_verificar(cliente, organizacion.host, app_db, email)

    disponible = await cliente.get(
        CHECK_SLUG, params={"slug": "org-completa"}, headers={"Host": organizacion.host}
    )
    assert disponible.status_code == 200
    assert disponible.json()["available"] is True

    creacion = await cliente.post(
        CREAR,
        headers={"Host": organizacion.host, "Authorization": f"Bearer {bridge}"},
        json={
            "name": "Org Completa",
            "slug": "org-completa",
            "first_name": "Nueva",
            "last_name": "Organizadora",
            "turnstile_token": "",
        },
    )
    assert creacion.status_code == 201, creacion.text
    cuerpo = creacion.json()
    assert cuerpo["slug"] == "org-completa"
    assert "access_token" not in cuerpo  # ver docstring de SelfServiceOrganizationResponse

    entrada = await cliente.post(
        LOGIN,
        json={"email": email, "password": CONTRASENA},
        headers={"Host": cuerpo["host"]},
    )
    assert entrada.status_code == 200, entrada.text
    assert entrada.json()["user"]["first_name"] == "Nueva"

    perfil = await cliente.get(
        "/api/v1/users/me",
        headers={
            "Host": cuerpo["host"],
            "Authorization": f"Bearer {entrada.json()['access_token']}",
        },
    )
    assert perfil.status_code == 200
    assert perfil.json()["roles"] == ["owner"]


async def test_un_slug_repetido_devuelve_409(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, app_db: AsyncSession
) -> None:
    email = "duplicado@example.com"
    bridge = await _registrar_y_verificar(cliente, organizacion.host, app_db, email)

    datos = {
        "name": "Duplicado",
        "slug": organizacion.slug,  # ya existe: la organización de la fixture
        "first_name": "A",
        "last_name": "B",
        "turnstile_token": "",
    }
    respuesta = await cliente.post(
        CREAR, headers={"Host": organizacion.host, "Authorization": f"Bearer {bridge}"}, json=datos
    )
    assert respuesta.status_code == 409


async def test_un_slug_reservado_es_rechazado_en_creacion_y_en_check_slug(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, app_db: AsyncSession
) -> None:
    email = "reservado@example.com"
    bridge = await _registrar_y_verificar(cliente, organizacion.host, app_db, email)

    comprobacion = await cliente.get(
        CHECK_SLUG, params={"slug": "admin"}, headers={"Host": organizacion.host}
    )
    assert comprobacion.json()["available"] is False

    creacion = await cliente.post(
        CREAR,
        headers={"Host": organizacion.host, "Authorization": f"Bearer {bridge}"},
        json={
            "name": "Intento",
            "slug": "admin",
            "first_name": "A",
            "last_name": "B",
            "turnstile_token": "",
        },
    )
    assert creacion.status_code == 422


async def test_sin_correo_verificado_no_puede_crear_organizacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, app_db: AsyncSession
) -> None:
    email = "sin-verificar@example.com"
    with (
        patch("app.modules.auth.service._password_filtrada", return_value=False),
        patch.object(send_verification_email, "kiq", new_callable=AsyncMock),
    ):
        await cliente.post(
            REGISTER,
            json={"email": email, "password": CONTRASENA, "turnstile_token": ""},
            headers={"Host": organizacion.host},
        )

    # Token con `sub` de un usuario real pero sin pasar por verify-email: se simula
    # generando el token de acceso directamente, igual que si alguien capturara un
    # JWT válido antes de que la cuenta se verificara.
    fila = (
        await app_db.execute(
            text("SELECT id FROM app_find_user_by_email(:email)"), {"email": email}
        )
    ).first()
    token_no_verificado = create_access_token(fila[0], None, is_superadmin=False)

    respuesta = await cliente.post(
        CREAR,
        headers={"Host": organizacion.host, "Authorization": f"Bearer {token_no_verificado}"},
        json={
            "name": "Sin Verificar",
            "slug": "sin-verificar-org",
            "first_name": "A",
            "last_name": "B",
            "turnstile_token": "",
        },
    )
    assert respuesta.status_code == 403


async def test_no_se_puede_crear_organizacion_a_nombre_de_otro(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    app_db: AsyncSession,
    maintenance_db: AsyncSession,
) -> None:
    """El `user_id` sale siempre del token, nunca de un campo del cuerpo."""
    email = "legitima@example.com"
    bridge = await _registrar_y_verificar(cliente, organizacion.host, app_db, email)

    creacion = await cliente.post(
        CREAR,
        headers={"Host": organizacion.host, "Authorization": f"Bearer {bridge}"},
        json={
            "name": "Legítima",
            "slug": "org-legitima",
            "first_name": "A",
            "last_name": "B",
            "turnstile_token": "",
        },
    )
    assert creacion.status_code == 201

    # El propietario de la organización es quien poseía el token, no un id ajeno: no
    # hay ningún campo en el cuerpo de la petición por el que colar otro usuario. Se
    # comprueba con el motor de mantenimiento porque `app_db` no tiene fijado el
    # contexto de esta organización nueva y RLS no le dejaría ver la membresía.
    perfil_dueno = (
        await maintenance_db.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": email}
        )
    ).first()
    miembro = (
        await maintenance_db.execute(
            text("SELECT user_id FROM organization_members WHERE organization_id = :org"),
            {"org": creacion.json()["id"]},
        )
    ).first()
    assert perfil_dueno is not None and miembro is not None
    assert str(miembro[0]) == str(perfil_dueno[0])


async def test_check_slug_sin_credenciales_funciona(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """check-slug es solo ayuda de UX: no exige token."""
    respuesta = await cliente.get(
        CHECK_SLUG, params={"slug": "cualquiera"}, headers={"Host": organizacion.host}
    )
    assert respuesta.status_code == 200


async def test_turnstile_invalido_rechaza_la_creacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, app_db: AsyncSession
) -> None:
    email = "turnstile@example.com"
    bridge = await _registrar_y_verificar(cliente, organizacion.host, app_db, email)

    with (
        patch("app.core.turnstile.get_settings") as settings_falso,
        patch("app.core.turnstile.verify_turnstile_token", return_value=False),
    ):
        settings_falso.return_value.turnstile_enabled = True
        respuesta = await cliente.post(
            CREAR,
            headers={"Host": organizacion.host, "Authorization": f"Bearer {bridge}"},
            json={
                "name": "Con Turnstile",
                "slug": "con-turnstile",
                "first_name": "A",
                "last_name": "B",
                "turnstile_token": "invalido",
            },
        )
    assert respuesta.status_code == 422
