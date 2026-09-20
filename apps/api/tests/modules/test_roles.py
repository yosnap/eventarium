"""Roles clonados, roles a medida y campos de perfil."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.audit import AuditLog
from app.core.database import SessionMaintenance
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

ROLES = "/api/v1/roles"


async def _contar_auditoria_de_permisos() -> int:
    async with SessionMaintenance() as session:
        total = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "role.permissions_changed")
        )
    return total or 0


async def test_una_organizacion_nueva_tiene_los_cinco_roles_del_sistema(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.get(ROLES, headers=cabeceras)
    assert respuesta.status_code == 200

    claves = {rol["key"] for rol in respuesta.json()}
    assert claves == {"owner", "organizer", "speaker", "volunteer", "attendee"}
    assert all(rol["is_system"] for rol in respuesta.json())


async def test_el_rol_de_ponente_trae_sus_campos_predefinidos_bloqueados(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    roles = (await cliente.get(ROLES, headers=cabeceras)).json()
    ponente = next(rol for rol in roles if rol["key"] == "speaker")

    campos = {campo["key"]: campo for campo in ponente["profile_fields"]}
    assert {"bio", "curriculum", "web", "contacto"} <= set(campos)
    assert campos["bio"]["is_required"] is True
    assert all(campo["is_locked"] for campo in campos.values())


async def test_crear_un_rol_a_medida_con_sus_campos(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        ROLES,
        headers=cabeceras,
        json={
            "key": "presentador",
            "name": "Presentador",
            "description": "Presenta el evento",
            "permissions": ["organizations:read"],
            "profile_fields": [
                {"key": "experiencia", "label": "Experiencia", "field_type": "textarea"},
                {"key": "demo", "label": "Vídeo de muestra", "field_type": "url"},
            ],
        },
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["is_system"] is False
    assert {c["key"] for c in cuerpo["profile_fields"]} == {"experiencia", "demo"}
    assert all(not c["is_locked"] for c in cuerpo["profile_fields"])


async def test_crear_un_rol_desde_una_plantilla_del_sistema(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        ROLES,
        headers=cabeceras,
        json={"key": "ponente-invitado", "name": "Ponente invitado", "from_template": "speaker"},
    )
    assert respuesta.status_code == 201
    assert "bio" in {c["key"] for c in respuesta.json()["profile_fields"]}


async def test_no_se_puede_repetir_la_clave_de_un_rol(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.post(
        ROLES, headers=cabeceras, json={"key": "speaker", "name": "Otro ponente"}
    )
    assert respuesta.status_code == 409


async def test_borrar_un_rol_del_sistema_devuelve_409(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    roles = (await cliente.get(ROLES, headers=cabeceras)).json()
    ponente = next(rol for rol in roles if rol["key"] == "speaker")

    respuesta = await cliente.delete(f"{ROLES}/{ponente['id']}", headers=cabeceras)
    assert respuesta.status_code == 409


async def test_borrar_un_rol_a_medida_funciona(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    creado = await cliente.post(
        ROLES, headers=cabeceras, json={"key": "cantante", "name": "Cantante"}
    )
    respuesta = await cliente.delete(f"{ROLES}/{creado.json()['id']}", headers=cabeceras)
    assert respuesta.status_code == 204
    assert (
        await cliente.get(f"{ROLES}/{creado.json()['id']}", headers=cabeceras)
    ).status_code == 404


async def test_se_puede_anadir_un_campo_a_un_rol_del_sistema(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    roles = (await cliente.get(ROLES, headers=cabeceras)).json()
    ponente = next(rol for rol in roles if rol["key"] == "speaker")

    campos = [
        {
            "key": campo["key"],
            "label": campo["label"],
            "field_type": campo["field_type"],
            "options": campo["options"],
            "is_required": campo["is_required"],
            "sort_order": campo["sort_order"],
        }
        for campo in ponente["profile_fields"]
    ]
    campos.append({"key": "idioma", "label": "Idioma de la charla", "field_type": "text"})

    respuesta = await cliente.patch(
        f"{ROLES}/{ponente['id']}", headers=cabeceras, json={"profile_fields": campos}
    )
    assert respuesta.status_code == 200
    resultado = {c["key"]: c for c in respuesta.json()["profile_fields"]}
    assert "idioma" in resultado
    assert resultado["idioma"]["is_locked"] is False
    assert resultado["bio"]["is_locked"] is True


async def test_no_se_puede_borrar_un_campo_bloqueado(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    roles = (await cliente.get(ROLES, headers=cabeceras)).json()
    ponente = next(rol for rol in roles if rol["key"] == "speaker")

    respuesta = await cliente.patch(
        f"{ROLES}/{ponente['id']}",
        headers=cabeceras,
        json={"profile_fields": [{"key": "idioma", "label": "Idioma"}]},
    )
    assert respuesta.status_code == 409
    assert "bio" in respuesta.json()["campos_bloqueados"]


async def test_cambio_de_permisos_no_deja_auditoria_si_profile_fields_falla(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Regresión: `role.permissions_changed` se escribía en una
    `maintenance_session` propia que hacía commit inmediato, antes de que
    `profile_fields` pudiera fallar y revertir el cambio real de permisos en
    la transacción principal (`roles/service.py`). Una petición que falla por
    `profile_fields` inválidos no debe dejar ninguna fila en `audit_log`."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    roles = (await cliente.get(ROLES, headers=cabeceras)).json()
    ponente = next(rol for rol in roles if rol["key"] == "speaker")
    permisos_originales = ponente["permissions"]

    assert await _contar_auditoria_de_permisos() == 0

    respuesta = await cliente.patch(
        f"{ROLES}/{ponente['id']}",
        headers=cabeceras,
        json={
            "permissions": ["events:read"],
            # Vacío: le faltan los campos bloqueados del ponente
            # (bio/curriculum/web/contacto) -> 409 antes de terminar.
            "profile_fields": [],
        },
    )
    assert respuesta.status_code == 409, respuesta.text

    # Ni la auditoría del cambio de permisos...
    assert await _contar_auditoria_de_permisos() == 0

    # ...ni el cambio de permisos en sí sobrevivieron al rollback.
    tras_el_fallo = (await cliente.get(f"{ROLES}/{ponente['id']}", headers=cabeceras)).json()
    assert sorted(tras_el_fallo["permissions"]) == sorted(permisos_originales)


async def test_un_rol_de_otra_organizacion_no_es_accesible(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.get(f"{ROLES}/{otra_organizacion.owner_role_id}", headers=cabeceras)
    assert respuesta.status_code == 404
