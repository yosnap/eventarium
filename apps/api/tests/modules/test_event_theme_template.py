"""Plantilla de tema por evento, con herencia.

Un organizador puede llevar una semana técnica y una gala benéfica y querer que
cada una tenga su identidad visual. La plantilla vive en el evento, y si el
evento no elige **hereda** la de su organización — que a su vez hereda la
marcada por defecto en el catálogo.

Lo que se fija aquí: que `NULL` signifique heredar (y no «sin tema»), que se
pueda volver a heredar mandando cadena vacía, y que un identificador que no
existe o no es un identificador se rechace con un mensaje, no con un error de
base de datos.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.modules.theme_templates.models import ThemeTemplate
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"


async def _plantillas() -> list[ThemeTemplate]:
    async with SessionMaintenance() as session:
        filas = await session.scalars(select(ThemeTemplate).order_by(ThemeTemplate.key))
        return list(filas)


async def _crear_evento(cliente: AsyncClient, cabeceras: dict[str, str], slug: str) -> dict:
    respuesta = await cliente.post(
        EVENTS,
        headers=cabeceras,
        json={
            "slug": slug,
            "title": f"Evento {slug}",
            "starts_at": "2026-10-01T09:00:00Z",
            "ends_at": "2026-10-02T18:00:00Z",
            "location_mode": "in_person",
            "location_name": "Sala",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


class TestPlantillaPorEvento:
    async def test_un_evento_nuevo_no_elige_plantilla_y_hereda(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """`None` es «hereda», no «sin tema»: el evento se ve como su organización."""
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "plantilla-hereda")
        assert evento["theme_template_id"] is None

    async def test_se_puede_elegir_una_plantilla_del_catalogo(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        plantillas = await _plantillas()
        assert plantillas, "el catálogo tiene que tener al menos una plantilla"

        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "plantilla-elegida")
        elegida = str(plantillas[0].id)

        actualizado = await cliente.patch(
            f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"theme_template_id": elegida}
        )
        assert actualizado.status_code == 200, actualizado.text
        assert actualizado.json()["theme_template_id"] == elegida

    async def test_la_cadena_vacia_vuelve_a_heredar(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """Es la forma de deshacer la elección: si no, no habría vuelta atrás."""
        plantillas = await _plantillas()
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "plantilla-vuelve")
        await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras,
            json={"theme_template_id": str(plantillas[0].id)},
        )

        vuelto = await cliente.patch(
            f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"theme_template_id": ""}
        )
        assert vuelto.status_code == 200, vuelto.text
        assert vuelto.json()["theme_template_id"] is None

    async def test_un_identificador_que_no_existe_se_rechaza_con_mensaje(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """Sin esto, el fallo sería un error de integridad de la base, que no dice
        nada a quien está usando la pantalla."""
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "plantilla-inexistente")

        respuesta = await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras,
            json={"theme_template_id": str(uuid.uuid4())},
        )
        assert respuesta.status_code in (400, 422), respuesta.text

    async def test_algo_que_no_es_un_identificador_se_rechaza(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "plantilla-no-uuid")

        respuesta = await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras,
            json={"theme_template_id": "no-soy-un-uuid"},
        )
        assert respuesta.status_code in (400, 422), respuesta.text


class TestTemaEnLaFichaPublica:
    """La plantilla del evento llega a su ficha pública, con la herencia resuelta.

    Se resuelve en el servidor —evento → organización → por defecto— y no en el
    cliente: encadenar tres consultas desde el navegador para pintar una página
    pública sería absurdo, y el catálogo es una tabla de instalación que el
    visitante no tiene por qué conocer.
    """

    async def test_sin_eleccion_la_ficha_hereda_una_plantilla(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "tema-hereda")
        await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras,
            json={"status": "published", "visibility": "public"},
        )

        ficha = await cliente.get(f"/api/v1/public/events/{evento['slug']}")
        assert ficha.status_code == 200, ficha.text
        tema = ficha.json()["theme"]
        # El catálogo tiene al menos la de por defecto: sin elección, se sirve esa.
        assert tema is not None
        assert tema["tokens"]

    async def test_la_ficha_sirve_la_plantilla_que_eligio_el_evento(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """Y no la de la organización, que es lo que distingue un evento de otro."""
        plantillas = await _plantillas()
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "tema-propio")

        # Se busca una plantilla distinta de la que heredaría, para que el test
        # distinga de verdad «la eligió» de «heredó la misma».
        heredada = await cliente.get(f"/api/v1/public/events/{evento['slug']}")
        await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras,
            json={"status": "published", "visibility": "public"},
        )
        heredada = await cliente.get(f"/api/v1/public/events/{evento['slug']}")
        id_heredado = heredada.json()["theme"]["id"]

        otra = next((p for p in plantillas if str(p.id) != id_heredado), None)
        if otra is None:
            pytest.skip("el catálogo solo tiene una plantilla: no hay nada que distinguir")

        await cliente.patch(
            f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"theme_template_id": str(otra.id)}
        )
        ficha = await cliente.get(f"/api/v1/public/events/{evento['slug']}")

        assert ficha.json()["theme"]["id"] == str(otra.id)
        assert ficha.json()["theme"]["id"] != id_heredado
