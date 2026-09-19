"""`GET /organizations/me/media` — filtro de visibilidad por `kind` y por
persona: uploader / compañero con el permiso de ESE `kind` / compañero con
permiso de OTRO `kind` / miembro de otra organización.

Regresión: `listar()` llamaba a `_requerir_permiso_del_kind`, que lanza
`PermissionDeniedError` si la sesión no tiene el permiso amplio del `kind` —
bloqueaba con 403 a quien solo debía ver sus propias subidas, en vez de
filtrar. El bug se detectó y corrigió durante esta misma fase; esta suite es
la regresión que lo mantiene arreglado.
"""

from __future__ import annotations

import base64

from httpx import AsyncClient
from sqlalchemy import delete

from app.core.database import SessionMaintenance
from app.core.permissions import Permission
from app.modules.roles.models import RolePermission
from tests.conftest import (
    OrganizacionDePrueba,
    crear_rol,
    crear_usuario_con_rol,
    iniciar_sesion,
    iniciar_sesion_con,
)

MEDIA = "/api/v1/organizations/me/media"

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def _subir(cliente: AsyncClient, cabeceras: dict[str, str], kind: str) -> dict:
    respuesta = await cliente.post(
        MEDIA,
        headers=cabeceras,
        data={"kind": kind},
        files={"fichero": ("i.png", PNG, "image/png")},
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def test_quien_tiene_el_permiso_del_kind_ve_toda_la_biblioteca_de_ese_kind(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras_owner = await iniciar_sesion(cliente, organizacion)
    await _subir(cliente, cabeceras_owner, "branding")

    await crear_rol(organizacion, key="solo-branding", permisos=[Permission.BRANDING_WRITE])
    correo, contrasena = await crear_usuario_con_rol(organizacion, "solo-branding")
    _, cabeceras_companero = await iniciar_sesion_con(cliente, organizacion, correo, contrasena)

    listado = await cliente.get(f"{MEDIA}?kind=branding", headers=cabeceras_companero)
    assert listado.status_code == 200, listado.text
    assert listado.json()["total"] == 1


async def test_quien_pierde_el_permiso_del_kind_sigue_viendo_lo_que_subio(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Subir un `branding` exige `branding:write`, así que "ver solo lo
    propio sin el permiso amplio" solo es alcanzable si el permiso se
    revoca DESPUÉS de subir (rol editado) — no hay otra vía en la API para
    tener una fila propia sin haber tenido el permiso alguna vez."""
    _, cabeceras_owner = await iniciar_sesion(cliente, organizacion)
    await _subir(cliente, cabeceras_owner, "branding")

    rol_id = await crear_rol(
        organizacion, key="branding-temporal", permisos=[Permission.BRANDING_WRITE]
    )
    correo, contrasena = await crear_usuario_con_rol(organizacion, "branding-temporal")
    _, cabeceras_companero = await iniciar_sesion_con(cliente, organizacion, correo, contrasena)
    subida_propia = await _subir(cliente, cabeceras_companero, "branding")

    async with SessionMaintenance() as session:
        await session.execute(delete(RolePermission).where(RolePermission.role_id == rol_id))
        await session.commit()

    listado = await cliente.get(f"{MEDIA}?kind=branding", headers=cabeceras_companero)
    assert listado.status_code == 200, listado.text
    ids = [f["id"] for f in listado.json()["items"]]
    assert ids == [subida_propia["id"]]


async def test_quien_solo_tiene_permiso_de_otro_kind_no_ve_ni_lo_ajeno_ni_bloquea(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Sin `branding:write` y sin haber subido nada de `branding`: la lista
    debe volver vacía, nunca un 403 (ver docstring del módulo)."""
    _, cabeceras_owner = await iniciar_sesion(cliente, organizacion)
    await _subir(cliente, cabeceras_owner, "branding")

    await crear_rol(organizacion, key="solo-sponsors", permisos=[Permission.SPONSORS_WRITE])
    correo, contrasena = await crear_usuario_con_rol(organizacion, "solo-sponsors")
    _, cabeceras_companero = await iniciar_sesion_con(cliente, organizacion, correo, contrasena)

    listado = await cliente.get(f"{MEDIA}?kind=branding", headers=cabeceras_companero)
    assert listado.status_code == 200, listado.text
    assert listado.json()["total"] == 0


async def test_un_kind_no_admitido_da_422(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.get(f"{MEDIA}?kind=lo-que-sea", headers=cabeceras)
    assert respuesta.status_code == 422, respuesta.text


async def test_aislamiento_entre_kind_dentro_de_la_misma_organizacion(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _subir(cliente, cabeceras, "branding")
    await _subir(cliente, cabeceras, "events")

    solo_branding = await cliente.get(f"{MEDIA}?kind=branding", headers=cabeceras)
    assert solo_branding.json()["total"] == 1
    solo_eventos = await cliente.get(f"{MEDIA}?kind=events", headers=cabeceras)
    assert solo_eventos.json()["total"] == 1


async def test_una_organizacion_no_ve_la_biblioteca_de_otra(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras_propias = await iniciar_sesion(cliente, organizacion)
    await _subir(cliente, cabeceras_propias, "branding")

    _, cabeceras_ajenas = await iniciar_sesion(cliente, otra_organizacion)
    listado = await cliente.get(f"{MEDIA}?kind=branding", headers=cabeceras_ajenas)
    assert listado.status_code == 200, listado.text
    assert listado.json()["total"] == 0
