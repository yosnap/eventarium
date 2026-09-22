"""Papelera (`DELETE`/`restore`) de la biblioteca de medios. El borrado
comprueba referencias en las 3 tablas de dominio antes de aceptar.

El recorte (`PATCH .../crop`) se retiró: el editor de recorte ahora hornea
proporción/rotación/volteo/zoom en el propio navegador y sube el resultado
como una subida normal — ver `plans/260921-1720-prd-editor-recorte-imagen`."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.core.permissions import Permission
from tests.conftest import (
    OrganizacionDePrueba,
    crear_rol,
    crear_usuario_con_rol,
    iniciar_sesion,
    iniciar_sesion_con,
)

MEDIA = "/api/v1/organizations/me/media"
BRANDING_LOGO = "/api/v1/organizations/me/branding/logo"
EVENTS = "/api/v1/events"

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

AHORA = datetime.now(UTC).replace(microsecond=0)


async def _subir(cliente: AsyncClient, cabeceras: dict[str, str], kind: str) -> dict:
    respuesta = await cliente.post(
        MEDIA,
        headers=cabeceras,
        data={"kind": kind},
        files={"fichero": ("i.png", PNG, "image/png")},
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _crear_evento(cliente: AsyncClient, cabeceras: dict[str, str], slug: str) -> dict:
    respuesta = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json={
            "slug": slug,
            "title": f"Evento {slug}",
            "starts_at": AHORA.isoformat(),
            "ends_at": (AHORA + timedelta(days=2)).isoformat(),
            "location_mode": "in_person",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def test_borrar_una_imagen_no_usada_la_envia_a_la_papelera(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")

    borrado = await cliente.delete(f"{MEDIA}/{subido['id']}", headers=cabeceras)
    assert borrado.status_code == 204, borrado.text

    listado = await cliente.get(f"{MEDIA}?kind=branding", headers=cabeceras)
    assert listado.json()["total"] == 0


async def test_borrar_una_imagen_en_uso_da_409_con_el_recurso_que_la_usa(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")
    asignado = await cliente.put(BRANDING_LOGO, headers=cabeceras, json={"media_id": subido["id"]})
    assert asignado.status_code == 200, asignado.text

    borrado = await cliente.delete(f"{MEDIA}/{subido['id']}", headers=cabeceras)
    assert borrado.status_code == 409, borrado.text
    cuerpo = borrado.json()
    assert cuerpo["used_by"][0]["tipo"] == "branding"


async def test_restaurar_una_imagen_de_la_papelera(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")
    await cliente.delete(f"{MEDIA}/{subido['id']}", headers=cabeceras)

    restaurado = await cliente.post(f"{MEDIA}/{subido['id']}/restore", headers=cabeceras)
    assert restaurado.status_code == 200, restaurado.text

    listado = await cliente.get(f"{MEDIA}?kind=branding", headers=cabeceras)
    assert listado.json()["total"] == 1


async def test_editar_metadatos_de_una_imagen(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")

    editado = await cliente.patch(
        f"{MEDIA}/{subido['id']}", headers=cabeceras, json={"alt": "Logotipo de la organización"}
    )
    assert editado.status_code == 200, editado.text
    assert editado.json()["alt"] == "Logotipo de la organización"


async def test_editar_solo_la_carpeta_no_borra_el_alt_ya_guardado(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Regresión: es un PATCH, no un PUT — enviar solo `folder_id` no debe
    poner `alt` a `null` (antes se asignaban los dos incondicionalmente)."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")
    await cliente.patch(f"{MEDIA}/{subido['id']}", headers=cabeceras, json={"alt": "Logo"})

    carpeta = await cliente.post(
        "/api/v1/organizations/me/media-folders",
        headers=cabeceras,
        json={"name": "Redes", "slug": "redes", "kind": "branding"},
    )
    assert carpeta.status_code == 200, carpeta.text

    editado = await cliente.patch(
        f"{MEDIA}/{subido['id']}", headers=cabeceras, json={"folder_id": carpeta.json()["id"]}
    )
    assert editado.status_code == 200, editado.text
    assert editado.json()["alt"] == "Logo"
    assert editado.json()["folder_id"] == carpeta.json()["id"]


async def test_editar_el_nombre_de_una_imagen(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")

    editado = await cliente.patch(
        f"{MEDIA}/{subido['id']}", headers=cabeceras, json={"filename": "logo-nuevo.png"}
    )
    assert editado.status_code == 200, editado.text
    assert editado.json()["filename"] == "logo-nuevo.png"


async def test_editar_el_nombre_no_borra_el_alt_ya_guardado(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Mismo criterio que `test_editar_solo_la_carpeta_no_borra_el_alt_ya_guardado`,
    aplicado al campo `filename` añadido para el modal «Editar imagen»."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")
    await cliente.patch(f"{MEDIA}/{subido['id']}", headers=cabeceras, json={"alt": "Logo"})

    editado = await cliente.patch(
        f"{MEDIA}/{subido['id']}", headers=cabeceras, json={"filename": "logo-nuevo.png"}
    )
    assert editado.status_code == 200, editado.text
    assert editado.json()["alt"] == "Logo"
    assert editado.json()["filename"] == "logo-nuevo.png"


async def test_editar_el_nombre_a_vacio_falla(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")

    editado = await cliente.patch(
        f"{MEDIA}/{subido['id']}", headers=cabeceras, json={"filename": "   "}
    )
    assert editado.status_code == 422, editado.text


async def test_editar_el_nombre_demasiado_largo_da_422(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")

    editado = await cliente.patch(
        f"{MEDIA}/{subido['id']}", headers=cabeceras, json={"filename": "a" * 256}
    )
    assert editado.status_code == 422, editado.text


async def test_borrar_una_imagen_reutilizada_en_dos_eventos_da_409_no_500(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Regresión: dos filas de dominio apuntando al mismo `media_id`
    (justo el caso de uso de una biblioteca reutilizable) hacían que
    `_referencias_activas` lanzara `MultipleResultsFound` (500) en vez de
    devolver las dos referencias con un 409."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "events")

    primero = await _crear_evento(cliente, cabeceras, "evento-reutiliza-1")
    segundo = await _crear_evento(cliente, cabeceras, "evento-reutiliza-2")
    for evento in (primero, segundo):
        asignado = await cliente.put(
            f"{EVENTS}/{evento['id']}/cover", headers=cabeceras, json={"media_id": subido["id"]}
        )
        assert asignado.status_code == 200, asignado.text

    borrado = await cliente.delete(f"{MEDIA}/{subido['id']}", headers=cabeceras)
    assert borrado.status_code == 409, borrado.text
    tipos_y_ids = {(u["tipo"], u["id"]) for u in borrado.json()["used_by"]}
    assert ("evento", primero["id"]) in tipos_y_ids
    assert ("evento", segundo["id"]) in tipos_y_ids


async def test_restaurar_y_editar_exigen_permiso_o_propiedad(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Regresión: `restore`/`PATCH` no comprobaban ni permiso ni propiedad —
    cualquier miembro autenticado podía gestionar cualquier medio ajeno de
    la organización, sin importar su `kind`."""
    _, cabeceras_owner = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras_owner, "branding")
    borrado = await cliente.delete(f"{MEDIA}/{subido['id']}", headers=cabeceras_owner)
    assert borrado.status_code == 204, borrado.text

    await crear_rol(organizacion, key="solo-eventos", permisos=[Permission.EVENTS_WRITE])
    correo, contrasena = await crear_usuario_con_rol(organizacion, "solo-eventos")
    _, cabeceras_ajenas = await iniciar_sesion_con(cliente, organizacion, correo, contrasena)

    restaurado = await cliente.post(f"{MEDIA}/{subido['id']}/restore", headers=cabeceras_ajenas)
    assert restaurado.status_code == 403, restaurado.text

    # Editar exige el medio fuera de la papelera para llegar a comprobar el
    # permiso (si no, `actualizar` ya lo rechaza antes por estar borrado) —
    # lo restaura quien sí puede.
    restaurado_por_dueno = await cliente.post(
        f"{MEDIA}/{subido['id']}/restore", headers=cabeceras_owner
    )
    assert restaurado_por_dueno.status_code == 200, restaurado_por_dueno.text

    editado = await cliente.patch(
        f"{MEDIA}/{subido['id']}", headers=cabeceras_ajenas, json={"alt": "intento ajeno"}
    )
    assert editado.status_code == 403, editado.text
