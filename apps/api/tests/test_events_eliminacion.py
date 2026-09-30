"""Eliminar un evento: solo cuando ya está cancelado, sin borrar ninguna fila."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import SessionMaintenance
from app.modules.events.cancelacion import barrer_cancelacion
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.test_events_cancelacion import (
    EVENTS,
    _cancelar,
    _evento_publicado,
    _inscripcion,
    _resumen,
    tareas,  # noqa: F401 - fixture autouse: las tareas en cola no se ejecutan de verdad
)

PUBLICO = "/api/v1/public/organizations"


async def _fila_del_evento(evento: dict) -> tuple[bool, str]:
    """`(existe, estado)` de la fila, con independencia de `deleted_at`."""
    async with SessionMaintenance() as session:
        fila = (
            await session.execute(
                text("SELECT deleted_at IS NOT NULL, status FROM events WHERE id = :id"),
                {"id": evento["id"]},
            )
        ).first()
    assert fila is not None, "la fila del evento no debe borrarse"
    return bool(fila[0]), fila[1]


async def test_un_evento_que_no_esta_cancelado_no_se_elimina(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    publicado = await _evento_publicado(cliente, cabeceras, "activo")
    borrador = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json={
            "slug": "borrador",
            "title": "Borrador",
            "starts_at": publicado["starts_at"],
            "ends_at": publicado["ends_at"],
            "location_mode": "in_person",
        },
    )

    for evento_id in (publicado["id"], borrador.json()["id"]):
        respuesta = await cliente.delete(f"{EVENTS}/{evento_id}", headers=cabeceras)
        assert respuesta.status_code == 409, respuesta.text
        assert "Cancélalo primero" in respuesta.json()["detail"]
    assert await _fila_del_evento(publicado) == (False, "published")


async def test_eliminar_un_evento_cancelado_lo_saca_de_todas_partes_sin_borrar_la_fila(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await cliente.patch(
        "/api/v1/organizations/me", headers=cabeceras, json={"public_page_enabled": True}
    )
    evento = await _evento_publicado(cliente, cabeceras, "a-eliminar")
    otro = await _evento_publicado(cliente, cabeceras, "se-queda")
    await _cancelar(cliente, cabeceras, evento, await _resumen(cliente, cabeceras, evento))
    # Antes de eliminar sigue visible, como cancelado.
    visible = await cliente.get(f"{PUBLICO}/{organizacion.slug}/events/a-eliminar")
    assert visible.status_code == 200
    assert visible.json()["cancelled"] is True

    respuesta = await cliente.delete(f"{EVENTS}/{evento['id']}", headers=cabeceras)
    assert respuesta.status_code == 204, respuesta.text

    # La fila sigue en la base de datos, marcada como eliminada.
    assert await _fila_del_evento(evento) == (True, "cancelled")
    # Desaparece del panel...
    assert (await cliente.get(f"{EVENTS}/{evento['id']}", headers=cabeceras)).status_code == 404
    listado = (await cliente.get(EVENTS, headers=cabeceras)).json()
    assert [e["slug"] for e in listado["items"]] == ["se-queda"]
    # ...y del público: ficha, página de la organización y directorio.
    ficha = await cliente.get(f"{PUBLICO}/{organizacion.slug}/events/a-eliminar")
    assert ficha.status_code == 404
    proximos = (await cliente.get(f"{PUBLICO}/{organizacion.slug}/events")).json()
    assert [e["slug"] for e in proximos["items"]] == ["se-queda"]
    assert [e["slug"] for e in (await cliente.get("/api/v1/public/events")).json()] == ["se-queda"]
    assert otro["slug"] == "se-queda"
    # El identificador sigue reservado dentro de la organización.
    repetido = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json={
            "slug": "a-eliminar",
            "title": "Otra vez",
            "starts_at": evento["starts_at"],
            "ends_at": evento["ends_at"],
            "location_mode": "in_person",
        },
    )
    assert repetido.status_code == 409
    # Eliminarlo dos veces es un 404, no un error.
    assert (await cliente.delete(f"{EVENTS}/{evento['id']}", headers=cabeceras)).status_code == 404


async def test_no_se_elimina_mientras_el_barrido_de_la_cancelacion_sigue_en_marcha(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _evento_publicado(cliente, cabeceras, "con-inscritos")
    await _inscripcion(organizacion, evento, "asistente@example.com", "confirmed")
    await _cancelar(cliente, cabeceras, evento, await _resumen(cliente, cabeceras, evento))

    en_marcha = await cliente.delete(f"{EVENTS}/{evento['id']}", headers=cabeceras)
    assert en_marcha.status_code == 409
    assert "todavía está en marcha" in en_marcha.json()["detail"]
    assert await _fila_del_evento(evento) == (False, "cancelled")

    await barrer_cancelacion(organizacion.id, uuid.UUID(evento["id"]))
    terminado = await cliente.delete(f"{EVENTS}/{evento['id']}", headers=cabeceras)
    assert terminado.status_code == 204, terminado.text
    # Las inscripciones se conservan aunque el evento ya no se vea.
    async with SessionMaintenance() as session:
        inscritos = (
            await session.execute(
                text("SELECT count(*) FROM event_registrations WHERE event_id = :id"),
                {"id": evento["id"]},
            )
        ).scalar()
    assert inscritos == 1


async def test_no_se_puede_eliminar_un_evento_de_otra_organizacion(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _evento_publicado(cliente, cabeceras, "ajeno")
    await _cancelar(cliente, cabeceras, evento, await _resumen(cliente, cabeceras, evento))
    _, cabeceras_otra = await iniciar_sesion(cliente, otra_organizacion)

    respuesta = await cliente.delete(f"{EVENTS}/{evento['id']}", headers=cabeceras_otra)

    assert respuesta.status_code == 404
    assert await _fila_del_evento(evento) == (False, "cancelled")
