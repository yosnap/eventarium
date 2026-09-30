"""El slug de evento es único por organización y la resolución pública lo respeta."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import SessionMaintenance
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.test_events_public import EVENTS, _crear_evento, _publicar

SLUG = "reunion-anual"


def _anidada(organizacion: OrganizacionDePrueba, slug: str = SLUG) -> str:
    return f"/api/v1/public/organizations/{organizacion.slug}/events/{slug}"


async def _evento_publicado(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, **overrides: object
) -> dict:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    evento = await _crear_evento(cliente, cabeceras, slug=SLUG, **overrides)
    await _publicar(cliente, cabeceras, evento["id"])
    return evento


async def test_el_mismo_slug_convive_en_dos_organizaciones_y_cada_url_resuelve_el_suyo(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    propio = await _evento_publicado(cliente, organizacion, title="De la primera")
    ajeno = await _evento_publicado(cliente, otra_organizacion, title="De la segunda")
    assert propio["id"] != ajeno["id"]

    primera = await cliente.get(_anidada(organizacion))
    segunda = await cliente.get(_anidada(otra_organizacion))
    assert primera.status_code == 200, primera.text
    assert segunda.status_code == 200, segunda.text
    assert primera.json()["title"] == propio["title"]
    assert segunda.json()["title"] == ajeno["title"]
    assert primera.json()["organization"]["slug"] == organizacion.slug
    assert segunda.json()["organization"]["slug"] == otra_organizacion.slug


async def test_un_slug_repetido_dentro_de_la_misma_organizacion_da_409_con_sugerencia(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    await _crear_evento(cliente, cabeceras, slug=SLUG)

    repetido = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json={
            "slug": SLUG,
            "title": "Otro",
            "starts_at": "2030-01-01T10:00:00+00:00",
            "ends_at": "2030-01-02T10:00:00+00:00",
            "location_mode": "in_person",
        },
    )
    assert repetido.status_code == 409
    assert repetido.json()["suggested_slug"] == f"{SLUG}-2"


async def test_lo_no_publicable_da_404_en_la_url_anidada(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    borrador = await _crear_evento(cliente, cabeceras, slug="borrador")
    oculto = await _crear_evento(cliente, cabeceras, slug="oculto")
    await _publicar(cliente, cabeceras, oculto["id"], visibility="hidden")
    privado = await _crear_evento(cliente, cabeceras, slug="privado")
    await _publicar(cliente, cabeceras, privado["id"], visibility="private")

    for slug in (borrador["slug"], oculto["slug"], privado["slug"]):
        assert (await cliente.get(_anidada(organizacion, slug))).status_code == 404
    # Un evento de una organización no se ve bajo el slug de otra.
    assert (await cliente.get(_anidada(otra_organizacion, "borrador"))).status_code == 404


async def test_una_organizacion_inactiva_no_sirve_sus_eventos(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    await _evento_publicado(cliente, organizacion)
    assert (await cliente.get(_anidada(organizacion))).status_code == 200

    async with SessionMaintenance() as session:
        await session.execute(
            text("UPDATE organizations SET is_active = false WHERE id = :id"),
            {"id": organizacion.id},
        )
        await session.commit()

    assert (await cliente.get(_anidada(organizacion))).status_code == 404


async def test_las_rutas_planas_anteriores_ya_no_existen(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Sin la organización en la ruta el slug no identifica un evento."""
    await _evento_publicado(cliente, organizacion)
    for ruta in (
        f"/api/v1/public/events/{SLUG}",
        f"/api/v1/public/events/{SLUG}/canonical",
        f"/api/v1/public/events/{SLUG}/policies",
    ):
        assert (await cliente.get(ruta)).status_code == 404, ruta


def _migracion():  # noqa: ANN202 - módulo cargado por ruta, su nombre no es importable
    ruta = (
        Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0058_slug_evento_por_org.py"
    )
    especificacion = importlib.util.spec_from_file_location("migracion_0058", ruta)
    assert especificacion is not None and especificacion.loader is not None
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


async def test_la_comprobacion_de_la_bajada_aborta_y_lista_los_slugs_repetidos(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    await _evento_publicado(cliente, organizacion)
    await _evento_publicado(cliente, otra_organizacion)

    async with SessionMaintenance() as session:
        with pytest.raises(DBAPIError, match=SLUG):
            await session.execute(text(_migracion()._COMPROBACION_DUPLICADOS))
