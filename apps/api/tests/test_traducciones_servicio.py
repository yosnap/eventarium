"""Traducciones del contenido: el traductor, la escritura manual, el aislamiento
entre organizaciones y el borrado junto con la entidad."""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.modules.organizations.models import Organization
from app.modules.translations import service
from app.modules.translations.campos import (
    CAMPOS,
    TABLAS,
    TIPOS,
    TIPOS_DE_ORGANIZACION,
    TRANSICIONES,
    campo_valido,
    huella,
    puede_pasar,
)
from app.modules.translations.models import ContentTranslation
from app.shared.errors import ValidationDomainError
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.test_events_public import EVENTS, _crear_evento

ID = uuid.uuid4()


def _traductor(**filas: tuple[str, str]) -> service.Traductor:
    traductor = service.Traductor(idioma="en-US", origen="es-ES", activos=("es-ES", "en-US"))
    traductor._filas = {
        ("event", ID, campo, "en-US"): (valor, huella(original))
        for campo, (original, valor) in filas.items()
    }
    return traductor


def test_sirve_la_traduccion_al_dia_y_cae_al_original_si_falta() -> None:
    traductor = _traductor(title=("Hola", "Hello"))

    assert traductor.campo("event", ID, "title", "Hola") == "Hello"
    assert traductor.campo("event", ID, "summary", "Resumen") == "Resumen"
    assert traductor.campo("event", ID, "description", None) is None
    assert traductor.idiomas_al_dia == ["es-ES"]
    assert traductor.idioma_servido == "es-ES"
    assert traductor.campos_pendientes == 1


def test_no_sirve_una_traduccion_hecha_sobre_otro_original() -> None:
    traductor = _traductor(title=("Hola", "Hello"))

    assert traductor.campo("event", ID, "title", "Hola de nuevo") == "Hola de nuevo"
    assert traductor.campos_pendientes == 1


def test_la_pagina_entera_traducida_esta_al_dia_en_los_dos_idiomas() -> None:
    traductor = _traductor(title=("Hola", "Hello"), summary=("Resumen", "Summary"))
    traductor.campo("event", ID, "title", "Hola")
    traductor.campo("event", ID, "summary", "Resumen")

    assert traductor.idiomas_al_dia == ["es-ES", "en-US"]
    assert traductor.idioma_servido == "en-US"
    assert traductor.metadatos()["pending_fields"] == 0


def test_en_el_idioma_de_origen_no_hay_pendientes() -> None:
    traductor = service.Traductor(idioma="es-ES", origen="es-ES", activos=("es-ES", "en-US"))

    assert traductor.campo("event", ID, "title", "Hola") == "Hola"
    assert traductor.idioma_servido == "es-ES"
    assert traductor.campos_pendientes == 0
    assert traductor.idiomas_al_dia == ["es-ES"]


def test_opciones_como_pares_valor_etiqueta() -> None:
    originales = ["Sí", "No"]
    traductor = service.Traductor(idioma="en-US", origen="es-ES", activos=("es-ES", "en-US"))
    traductor._filas = {
        ("question", ID, "options", "en-US"): (
            json.dumps({"Sí": "Yes"}),
            huella(json.dumps(originales)),
        )
    }

    assert traductor.opciones(ID, originales) == [("Sí", "Yes"), ("No", "No")]
    assert traductor.opciones(ID, None) is None


def test_los_campos_y_las_transiciones_son_coherentes() -> None:
    assert set(CAMPOS) == set(TIPOS)
    assert set(TABLAS) | {"event", "organization", "tag"} == set(TIPOS)
    assert TIPOS_DE_ORGANIZACION <= set(TIPOS)
    assert campo_valido("event", "title")
    assert not campo_valido("event", "slug")
    assert campo_valido("member_profile", "bio")
    assert not campo_valido("member_profile", "web")
    assert not campo_valido("tag", "Con Mayúsculas")
    assert puede_pasar("pendiente", "en_curso")
    assert not puede_pasar("pendiente", "al_dia")
    assert all(
        puede_pasar(estado, "desactualizada")
        for estado in TRANSICIONES
        if estado != "desactualizada"
    )


async def _activar_ingles(organizacion: OrganizacionDePrueba) -> None:
    async with SessionMaintenance() as session, session.begin():
        await session.execute(
            update(Organization)
            .where(Organization.id == organizacion.id)
            .values(content_locales=["es-ES", "en-US"])
        )


async def _guardar(
    organizacion: OrganizacionDePrueba,
    event_id: uuid.UUID,
    *,
    contexto: uuid.UUID | None = None,
    **extra: object,
) -> None:
    async with SessionApp() as session, session.begin():
        await set_organization_context(session, contexto or organizacion.id)
        await service.guardar_manual(
            session,
            organization_id=extra.pop("organization_id", organizacion.id),  # type: ignore[arg-type]
            event_id=event_id,
            tipo="event",
            entity_id=event_id,
            campo=extra.pop("campo", "title"),  # type: ignore[arg-type]
            locale=extra.pop("locale", "en-US"),  # type: ignore[arg-type]
            valor="My event",
            original="Mi evento",
            origen_del_contenido="es-ES",
            idiomas_activos=("es-ES", "en-US"),
            user_id=organizacion.owner_id,
        )


async def _contar(organizacion_id: uuid.UUID) -> int:
    async with SessionMaintenance() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(ContentTranslation)
                .where(ContentTranslation.organization_id == organizacion_id)
            )
            or 0
        )


async def test_guardar_manual_y_volver_a_guardar_actualiza_la_misma_fila(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, slug="traducible")
    await _activar_ingles(organizacion)

    await _guardar(organizacion, uuid.UUID(evento["id"]))
    await _guardar(organizacion, uuid.UUID(evento["id"]))

    assert await _contar(organizacion.id) == 1


@pytest.mark.parametrize(
    ("extra", "motivo"),
    [
        ({"campo": "slug"}, "campo"),
        ({"locale": "es-ES"}, "origen"),
    ],
    ids=["campo-no-traducible", "idioma-original"],
)
async def test_guardar_manual_rechaza_lo_que_no_se_traduce(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, extra: dict, motivo: str
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, slug=f"rechazo-{motivo}")

    with pytest.raises(ValidationDomainError):
        await _guardar(organizacion, uuid.UUID(evento["id"]), **extra)


async def test_una_organizacion_no_escribe_ni_lee_traducciones_de_otra(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, slug="ajeno")
    event_id = uuid.UUID(evento["id"])
    await _guardar(organizacion, event_id)

    # Con el contexto de la otra, escribir a nombre de la primera lo para RLS…
    with pytest.raises(DBAPIError):
        await _guardar(organizacion, event_id, contexto=otra_organizacion.id)
    # …y a nombre propio sobre el evento ajeno lo para la FK compuesta.
    with pytest.raises(IntegrityError):
        await _guardar(
            organizacion,
            event_id,
            contexto=otra_organizacion.id,
            organization_id=otra_organizacion.id,
        )

    async with SessionApp() as session, session.begin():
        await set_organization_context(session, otra_organizacion.id)
        visibles = await session.scalar(select(func.count()).select_from(ContentTranslation))
    assert visibles == 0
    assert await _contar(otra_organizacion.id) == 0


async def test_borrar_la_entidad_borra_sus_traducciones(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, slug="con-sitio")
    sitio = await cliente.post(
        f"{EVENTS}/{evento['id']}/nearby-places",
        headers=cabeceras,
        json={"kind": "hotel", "name": "Hotel Mar"},
    )
    assert sitio.status_code == 201, sitio.text
    await _activar_ingles(organizacion)
    async with SessionApp() as session, session.begin():
        await set_organization_context(session, organizacion.id)
        await service.guardar_manual(
            session,
            organization_id=organizacion.id,
            event_id=uuid.UUID(evento["id"]),
            tipo="nearby_place",
            entity_id=uuid.UUID(sitio.json()["id"]),
            campo="name",
            locale="en-US",
            valor="Sea Hotel",
            original="Hotel Mar",
            origen_del_contenido="es-ES",
            idiomas_activos=("es-ES", "en-US"),
            user_id=organizacion.owner_id,
        )
    assert await _contar(organizacion.id) == 1

    borrado = await cliente.delete(
        f"{EVENTS}/{evento['id']}/nearby-places/{sitio.json()['id']}", headers=cabeceras
    )
    assert borrado.status_code == 204
    assert await _contar(organizacion.id) == 0


async def test_las_etiquetas_sin_uso_se_barren(organizacion: OrganizacionDePrueba) -> None:
    async with SessionMaintenance() as session, session.begin():
        session.add(
            ContentTranslation(
                organization_id=organizacion.id,
                event_id=None,
                entity_type="tag",
                entity_id=organizacion.id,
                field="sin uso",
                locale="en-US",
                value="unused",
                origin="manual",
                status="al_dia",
                source_hash=huella("sin uso"),
            )
        )
    async with SessionMaintenance() as session, session.begin():
        assert await service.borrar_etiquetas_sin_uso(session) == 1
