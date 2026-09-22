"""Papelera (`DELETE`/`restore`) de la biblioteca de medios. El borrado
comprueba referencias en las 3 tablas de dominio antes de aceptar.

El recorte (`PATCH .../crop`) se retiró: el editor de recorte ahora hornea
proporción/rotación/volteo/zoom en el propio navegador. El resultado se sube
como una subida normal (`POST`, «Guardar como nueva») o, desde
`260922-0125-prd-iconos-hover-biblioteca-medios`, reemplaza los píxeles del
medio ya existente (`PUT .../contenido`, «Sobrescribir original») — ver
`sobrescribir_contenido` más abajo."""

from __future__ import annotations

import base64
import io
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from PIL import Image
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


def _png_mas_grande() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=(200, 40, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


async def test_sobrescribir_contenido_mantiene_la_misma_id_y_url(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """«Sobrescribir original»: misma `id` y mismo objeto de almacenamiento
    (la URL sin el `?v=` no cambia) que antes, solo cambian los píxeles —
    cualquier sitio que ya use esta imagen (portada, logo…) ve el recorte
    nuevo sin tener que reasignar el campo. El `?v=` SÍ debe cambiar: es lo
    que evita que `/media/*` (servido con `Cache-Control: immutable`) siga
    entregando los bytes viejos desde caché."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")

    sobrescrito = await cliente.put(
        f"{MEDIA}/{subido['id']}/contenido",
        headers=cabeceras,
        files={"fichero": ("recorte.png", _png_mas_grande(), "image/png")},
    )
    assert sobrescrito.status_code == 200, sobrescrito.text
    cuerpo = sobrescrito.json()
    assert cuerpo["id"] == subido["id"]
    assert cuerpo["url"].split("?")[0] == subido["url"].split("?")[0]
    assert cuerpo["url"] != subido["url"]
    assert cuerpo["width"] == 64
    assert cuerpo["height"] == 64
    assert cuerpo["size"] != subido["size"]


async def test_sobrescribir_contenido_no_borra_el_nombre_ni_la_carpeta(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")
    await cliente.patch(
        f"{MEDIA}/{subido['id']}", headers=cabeceras, json={"filename": "logo-recortado.png"}
    )

    sobrescrito = await cliente.put(
        f"{MEDIA}/{subido['id']}/contenido",
        headers=cabeceras,
        files={"fichero": ("recorte.png", _png_mas_grande(), "image/png")},
    )
    assert sobrescrito.status_code == 200, sobrescrito.text
    assert sobrescrito.json()["filename"] == "logo-recortado.png"


async def test_sobrescribir_contenido_dos_veces_con_los_mismos_bytes_cambia_igualmente_el_v(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Regresión: `onupdate` (TimestampMixin) solo se dispara si SQLAlchemy
    detecta que alguna columna cambió de valor de verdad. Sobrescribir dos
    veces con bytes IDÉNTICOS dejaba `mime_type`/`size`/`width`/`height`
    exactamente iguales a los ya guardados en la segunda vez, así que
    `updated_at` no cambiaba y el `?v=` de la URL tampoco — la caché de
    `/media/*` (`Cache-Control: immutable`) seguía sirviendo los píxeles
    viejos. `fila.updated_at` ahora se fija a mano, así que el `?v=` debe
    cambiar SIEMPRE, con o sin cambio real en las otras columnas."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")

    contenido = _png_mas_grande()
    primera = await cliente.put(
        f"{MEDIA}/{subido['id']}/contenido",
        headers=cabeceras,
        files={"fichero": ("recorte.png", contenido, "image/png")},
    )
    assert primera.status_code == 200, primera.text

    segunda = await cliente.put(
        f"{MEDIA}/{subido['id']}/contenido",
        headers=cabeceras,
        files={"fichero": ("recorte.png", contenido, "image/png")},
    )
    assert segunda.status_code == 200, segunda.text
    assert primera.json()["size"] == segunda.json()["size"]
    assert primera.json()["url"] != segunda.json()["url"]


async def test_sobrescribir_contenido_exige_permiso_o_propiedad(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras_owner = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras_owner, "branding")

    await crear_rol(organizacion, key="solo-eventos", permisos=[Permission.EVENTS_WRITE])
    correo, contrasena = await crear_usuario_con_rol(organizacion, "solo-eventos")
    _, cabeceras_ajenas = await iniciar_sesion_con(cliente, organizacion, correo, contrasena)

    sobrescrito = await cliente.put(
        f"{MEDIA}/{subido['id']}/contenido",
        headers=cabeceras_ajenas,
        files={"fichero": ("recorte.png", _png_mas_grande(), "image/png")},
    )
    assert sobrescrito.status_code == 403, sobrescrito.text


async def test_sobrescribir_contenido_en_uso_exige_permiso_del_kind_no_solo_propiedad(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Regresión: sobrescribir un medio EN USO solo exigía propiedad (haberlo
    subido), no el permiso del `kind` — a alguien al que se le retira
    `BRANDING_WRITE` seguía bastándole haber subido la imagen en su día para
    cambiar los píxeles del logo ya publicado de la organización (hallazgo
    de code-review). Sin uso, la propiedad sigue bastando (no se toca ese
    caso, ver `test_sobrescribir_contenido_mantiene_la_misma_id_y_url`)."""
    await crear_rol(organizacion, key="editor-branding", permisos=[Permission.BRANDING_WRITE])
    correo, contrasena = await crear_usuario_con_rol(organizacion, "editor-branding")
    _, cabeceras = await iniciar_sesion_con(cliente, organizacion, correo, contrasena)

    subido = await _subir(cliente, cabeceras, "branding")
    asignado = await cliente.put(BRANDING_LOGO, headers=cabeceras, json={"media_id": subido["id"]})
    assert asignado.status_code == 200, asignado.text

    # Revocación del permiso (como haría un admin editando el rol): la
    # propiedad del medio se conserva, el permiso no.
    async with SessionMaintenance() as session:
        await session.execute(
            delete(RolePermission).where(
                RolePermission.organization_id == organizacion.id,
                RolePermission.permission == Permission.BRANDING_WRITE.value,
            )
        )
        await session.commit()

    sobrescrito = await cliente.put(
        f"{MEDIA}/{subido['id']}/contenido",
        headers=cabeceras,
        files={"fichero": ("recorte.png", _png_mas_grande(), "image/png")},
    )
    assert sobrescrito.status_code == 403, sobrescrito.text


async def test_consultar_uso_de_un_medio(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras, "branding")

    sin_uso = await cliente.get(f"{MEDIA}/{subido['id']}/uso", headers=cabeceras)
    assert sin_uso.status_code == 200, sin_uso.text
    assert sin_uso.json()["used_by"] == []

    asignado = await cliente.put(BRANDING_LOGO, headers=cabeceras, json={"media_id": subido["id"]})
    assert asignado.status_code == 200, asignado.text

    con_uso = await cliente.get(f"{MEDIA}/{subido['id']}/uso", headers=cabeceras)
    assert con_uso.status_code == 200, con_uso.text
    assert con_uso.json()["used_by"][0]["tipo"] == "branding"


async def test_consultar_uso_exige_permiso_o_propiedad(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras_owner = await iniciar_sesion(cliente, organizacion)
    subido = await _subir(cliente, cabeceras_owner, "branding")

    await crear_rol(organizacion, key="solo-eventos", permisos=[Permission.EVENTS_WRITE])
    correo, contrasena = await crear_usuario_con_rol(organizacion, "solo-eventos")
    _, cabeceras_ajenas = await iniciar_sesion_con(cliente, organizacion, correo, contrasena)

    uso = await cliente.get(f"{MEDIA}/{subido['id']}/uso", headers=cabeceras_ajenas)
    assert uso.status_code == 403, uso.text


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
