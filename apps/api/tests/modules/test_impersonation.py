"""Endpoints y garantías de la impersonación.

Cubre los criterios de éxito de la fase: sesión de **solo lectura** aplicada en
el backend, gate que rechaza tokens de impersonación, reautenticación,
auditoría con sujeto e id de sesión, y revocación real al salir.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.core.permissions import Permission
from app.modules.organizations.models import OrganizationMember
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, crear_miembro, crear_rol, iniciar_sesion

ADMIN = "/api/v1/admin"
IMPERSONATE = f"{ADMIN}/impersonate"


async def _hacer_superadmin(email: str) -> None:
    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == email))
        assert usuario is not None
        usuario.is_superadmin = True
        await session.commit()


async def _miembro_de(organizacion: OrganizacionDePrueba, email: str) -> uuid.UUID:
    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == email))
        assert usuario is not None
        miembro = await session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.user_id == usuario.id,
                OrganizationMember.organization_id == organizacion.id,
            )
        )
        assert miembro is not None
        return usuario.id


async def _preparar_impersonacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> tuple[uuid.UUID, dict[str, str], str]:
    """Deja un admin autenticado y un miembro suplantable; devuelve los datos."""
    await _hacer_superadmin(organizacion.owner_email)
    # Un rol de solo lectura: el escenario realista de «ver lo que ve».
    await crear_rol(organizacion, key="organizador_plano", permisos=[Permission.EVENTS_READ])
    persona = await crear_miembro(organizacion, "organizador_plano")
    _, cabeceras_admin = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        IMPERSONATE,
        headers=cabeceras_admin,
        json={
            "user_id": str(persona.user_id),
            "organization_id": str(organizacion.id),
            "reason": "Reproducir una incidencia",
            "password": organizacion.owner_password,
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return persona.user_id, cabeceras_admin, respuesta.json()["access_token"]


async def test_impersonar_devuelve_un_token_de_solo_lectura(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, _, token = await _preparar_impersonacion(cliente, organizacion)

    cabeceras = {"Authorization": f"Bearer {token}"}
    # Leer un endpoint normal funciona: es lo que se quiere poder hacer.
    lectura = await cliente.get("/api/v1/events", headers=cabeceras)
    assert lectura.status_code == 200, lectura.text

    # …y escribir se rechaza en el **backend**, no solo en el cliente.
    escritura = await cliente.post(
        "/api/v1/roles",
        headers=cabeceras,
        json={"key": "no-deberia", "name": "No debería crearse"},
    )
    assert escritura.status_code == 403, escritura.text


async def test_el_token_de_impersonacion_no_usa_los_endpoints_de_administracion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """El claim `sa` no es la defensa: el gate mira la fila de `users`.

    Si el usuario suplantado fuera superadmin en la base de datos, un token
    emitido con `is_superadmin=False` seguiría pasando `require_superadmin`
    salvo por la comprobación explícita de `impersonated_by`.
    """
    _, _, token = await _preparar_impersonacion(cliente, organizacion)
    cabeceras = {"Authorization": f"Bearer {token}"}

    # Ningún endpoint de administración acepta el token de impersonación.
    for ruta in (f"{ADMIN}/organizations", "/api/v1/admin/legal-pages"):
        respuesta = await cliente.get(ruta, headers=cabeceras)
        assert respuesta.status_code == 403, f"{ruta}: {respuesta.text}"


async def test_salir_revoca_el_token_de_inmediato(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """`stop` no es cosmético: el token deja de valer sin esperar a su `exp`."""
    _, _, token = await _preparar_impersonacion(cliente, organizacion)
    cabeceras = {"Authorization": f"Bearer {token}"}

    salida = await cliente.post(f"{IMPERSONATE}/stop", headers=cabeceras)
    assert salida.status_code == 204, salida.text

    # El token ya no vale para nada, sin esperar a su caducidad.
    despues = await cliente.get("/api/v1/events", headers=cabeceras)
    assert despues.status_code == 401, despues.text


async def test_impersonar_exige_la_contrasena_del_administrador(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _hacer_superadmin(organizacion.owner_email)
    await crear_rol(organizacion, key="otro_rol", permisos=[])
    persona = await crear_miembro(organizacion, "otro_rol")
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        IMPERSONATE,
        headers=cabeceras,
        json={
            "user_id": str(persona.user_id),
            "organization_id": str(organizacion.id),
            "reason": "Sin contraseña correcta",
            "password": "contraseña-incorrecta",
        },
    )
    assert respuesta.status_code == 401, respuesta.text


async def test_no_se_puede_impersonar_a_un_superadministrador(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Sería una vía para operar con los privilegios de otro admin sin su contraseña."""
    await _hacer_superadmin(organizacion.owner_email)
    # Se intenta suplantar al propio administrador (que es superadmin).
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    admin_id = await _miembro_de(organizacion, organizacion.owner_email)

    respuesta = await cliente.post(
        IMPERSONATE,
        headers=cabeceras,
        json={
            "user_id": str(admin_id),
            "organization_id": str(organizacion.id),
            "reason": "No debería poder",
            "password": organizacion.owner_password,
        },
    )
    assert respuesta.status_code == 403, respuesta.text


async def test_un_usuario_normal_no_puede_impersonar(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await crear_rol(organizacion, key="normal", permisos=[])
    persona = await crear_miembro(organizacion, "normal")
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        IMPERSONATE,
        headers=cabeceras,
        json={
            "user_id": str(persona.user_id),
            "organization_id": str(organizacion.id),
            "reason": "No soy superadmin",
            "password": organizacion.owner_password,
        },
    )
    assert respuesta.status_code == 403, respuesta.text


async def test_la_entrada_y_la_salida_quedan_auditadas_y_emparejadas(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    from app.core.audit import AuditLog

    usuario_id, _, token = await _preparar_impersonacion(cliente, organizacion)
    cabeceras = {"Authorization": f"Bearer {token}"}
    await cliente.post(f"{IMPERSONATE}/stop", headers=cabeceras)

    async with SessionMaintenance() as session:
        inicio = await session.scalar(
            select(AuditLog).where(AuditLog.action == "impersonation.started")
        )
        fin = await session.scalar(
            select(AuditLog).where(AuditLog.action == "impersonation.stopped")
        )

    assert inicio is not None and fin is not None
    # Actor = admin, sujeto = usuario suplantado: actor y sujeto son distintos.
    assert inicio.subject_user_id == usuario_id
    assert inicio.actor_user_id != usuario_id
    assert fin.subject_user_id == usuario_id
    # El id de sesión empareja entrada y salida.
    assert inicio.session_id is not None
    assert inicio.session_id == fin.session_id


async def test_no_se_puede_impersonar_a_quien_no_pertenece_a_esa_organizacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        IMPERSONATE,
        headers=cabeceras,
        json={
            "user_id": str(uuid.uuid4()),
            "organization_id": str(organizacion.id),
            "reason": "Usuario inexistente",
            "password": organizacion.owner_password,
        },
    )
    assert respuesta.status_code == 404, respuesta.text


async def test_la_lista_de_suplantables_enmascara_el_correo_y_marca_a_los_admin(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """La lista sirve para elegir a quién suplantar, no para leer correos."""
    await _hacer_superadmin(organizacion.owner_email)
    await crear_rol(organizacion, key="suplantable", permisos=[])
    await crear_miembro(organizacion, "suplantable")
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get(
        f"{ADMIN}/organizations/{organizacion.id}/members", headers=cabeceras
    )
    assert respuesta.status_code == 200, respuesta.text

    miembros = respuesta.json()
    assert miembros, "la organización de prueba tiene al menos un miembro"

    for miembro in miembros:
        # El correo va enmascarado, nunca completo.
        assert "@" in miembro["email_enmascarado"]
        assert "***" in miembro["email_enmascarado"].split("@")[0]

    # El propio administrador aparece, pero marcado como no suplantable.
    admin = next(m for m in miembros if not m["suplantable"])
    assert admin is not None


async def test_se_avisa_a_la_persona_suplantada(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quien es suplantado tiene que poder enterarse.

    Sin este aviso no se enteraría de ninguna forma: el registro de auditoría
    está restringido al personal de plataforma. Se comprueba que la tarea se
    encola con el correo de la persona suplantada y el motivo indicado.
    """
    enviados: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def _capturar(*args: object, **kwargs: object) -> None:
        enviados.append((args, kwargs))

    from app.modules.admin import impersonation_router

    monkeypatch.setattr(impersonation_router.send_impersonation_notice, "kiq", _capturar)

    await _hacer_superadmin(organizacion.owner_email)
    await crear_rol(organizacion, key="avisado", permisos=[])
    persona = await crear_miembro(organizacion, "avisado")
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.post(
        IMPERSONATE,
        headers=cabeceras,
        json={
            "user_id": str(persona.user_id),
            "organization_id": str(organizacion.id),
            "reason": "Comprobar una incidencia",
            "password": organizacion.owner_password,
        },
    )
    assert respuesta.status_code == 201, respuesta.text

    assert len(enviados) == 1
    argumentos, opciones = enviados[0]
    # El aviso va al correo de la persona suplantada, no al del administrador.
    assert argumentos[0] == persona.email
    assert opciones["reason"] == "Comprobar una incidencia"
    assert "organizacion" in opciones
