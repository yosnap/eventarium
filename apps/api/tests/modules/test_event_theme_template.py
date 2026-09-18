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
from sqlalchemy import select, update

from app.core.database import SessionMaintenance
from app.modules.events.models import Event
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


class TestPersonalizacionPorEvento:
    """`theme_overrides`: ajustes de color/fuente sobre la plantilla resuelta.

    Semántica DISTINTA de `theme_template_id` a propósito: aquí `null`
    explícito SÍ borra (no hace falta una cadena vacía), porque es un objeto,
    no un identificador que se confundiría con "sin cambios" al llegar vacío.
    """

    async def test_clave_desconocida_se_rechaza(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "overrides-clave-desconocida")

        respuesta = await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras,
            json={"theme_overrides": {"bg": "#000000"}},
        )
        assert respuesta.status_code == 422, respuesta.text

    async def test_fuente_con_tipo_no_textual_se_rechaza_con_422(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """Sin el `isinstance` explícito, esto revienta con 500 en vez de 422
        (hallazgo del red-team de este plan)."""
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "overrides-fuente-no-string")

        respuesta = await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras,
            json={"theme_overrides": {"font-display": 123}},
        )
        assert respuesta.status_code == 422, respuesta.text

    async def test_fuente_fuera_de_lista_blanca_se_rechaza(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "overrides-fuente-no-permitida")

        respuesta = await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras,
            json={"theme_overrides": {"font-body": "Comic Sans"}},
        )
        assert respuesta.status_code == 422, respuesta.text

    async def test_color_acromatico_se_rechaza(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """El color elegido se perdería sin aviso (croma 0, matiz indefinido)."""
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "overrides-color-gris")

        respuesta = await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras,
            json={"theme_overrides": {"accent": "#808080"}},
        )
        assert respuesta.status_code == 422, respuesta.text

    async def test_guardar_y_leer_overrides_round_trip(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """Cubre el hallazgo del red-team: `EventResponse` se construye a mano
        en `_event_response` — sin ese campo ahí, esto se quedaría en `null`."""
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "overrides-round-trip")

        overrides = {"accent": "#22c55e", "font-display": "Oswald", "font-body": "Inter"}
        actualizado = await cliente.patch(
            f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"theme_overrides": overrides}
        )
        assert actualizado.status_code == 200, actualizado.text
        assert actualizado.json()["theme_overrides"] == overrides

        leido = await cliente.get(f"{EVENTS}/{evento['id']}", headers=cabeceras)
        assert leido.status_code == 200, leido.text
        assert leido.json()["theme_overrides"] == overrides

    async def test_ausente_no_cambia_nada(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "overrides-ausente")
        overrides = {"accent": "#3b82f6"}
        await cliente.patch(
            f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"theme_overrides": overrides}
        )

        sin_tocar_overrides = await cliente.patch(
            f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"title": "Otro título"}
        )
        assert sin_tocar_overrides.status_code == 200, sin_tocar_overrides.text
        assert sin_tocar_overrides.json()["theme_overrides"] == overrides

    async def test_null_explicito_borra_los_overrides(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """Semántica DISTINTA de `theme_template_id`: aquí `null` sí borra
        (no hace falta cadena vacía) — hallazgo del red-team, documentado en
        el docstring de `EventUpdate.theme_overrides`."""
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "overrides-null-borra")
        await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras,
            json={"theme_overrides": {"accent": "#3b82f6"}},
        )

        borrado = await cliente.patch(
            f"{EVENTS}/{evento['id']}", headers=cabeceras, json={"theme_overrides": None}
        )
        assert borrado.status_code == 200, borrado.text
        assert borrado.json()["theme_overrides"] is None

    async def test_volver_a_plantilla_pura_con_los_dos_campos_a_la_vez(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """Perfil (e) del predict: plantilla propia + cadena vacía, overrides +
        null, en el mismo PATCH."""
        plantillas = await _plantillas()
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "overrides-vuelve-a-pura")
        await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras,
            json={
                "theme_template_id": str(plantillas[0].id),
                "theme_overrides": {"accent": "#3b82f6"},
            },
        )

        vuelto = await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras,
            json={"theme_template_id": "", "theme_overrides": None},
        )
        assert vuelto.status_code == 200, vuelto.text
        assert vuelto.json()["theme_template_id"] is None
        assert vuelto.json()["theme_overrides"] is None

    async def test_accent_corrupto_en_bd_degrada_sin_500(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """Un dato corrupto que se saltó el validador (migración de datos,
        restauración de backup) no debe tumbar la ficha pública."""
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "overrides-corrupto")
        await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras,
            json={"status": "published", "visibility": "public"},
        )

        async with SessionMaintenance() as session:
            await session.execute(
                update(Event)
                .where(Event.id == uuid.UUID(evento["id"]))
                .values(theme_overrides={"accent": "no-es-un-color-valido"})
            )
            await session.commit()

        ficha = await cliente.get(f"/api/v1/public/events/{evento['slug']}")
        assert ficha.status_code == 200, ficha.text
        assert ficha.json()["theme"] is not None

    async def test_patch_de_theme_desde_otra_organizacion_se_rechaza(
        self,
        cliente: AsyncClient,
        organizacion: OrganizacionDePrueba,
        otra_organizacion: OrganizacionDePrueba,
    ) -> None:
        """`theme_template_id`/`theme_overrides` son campos de `EventUpdate`
        como cualquier otro: el aislamiento por organización ya lo garantiza
        `service.update_event` (busca el evento por `organization_id` del
        usuario autenticado, no del payload) — este test lo deja explícito
        para estos dos campos en concreto."""
        _, cabeceras_propietaria = await iniciar_sesion(cliente, organizacion)
        _, cabeceras_intrusa = await iniciar_sesion(cliente, otra_organizacion)
        evento = await _crear_evento(cliente, cabeceras_propietaria, "theme-ajeno")

        plantillas = await _plantillas()
        intento_plantilla = await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras_intrusa,
            json={"theme_template_id": str(plantillas[0].id)},
        )
        assert intento_plantilla.status_code == 404

        intento_overrides = await cliente.patch(
            f"{EVENTS}/{evento['id']}",
            headers=cabeceras_intrusa,
            json={"theme_overrides": {"accent": "#3b82f6"}},
        )
        assert intento_overrides.status_code == 404

        sin_tocar = await cliente.get(f"{EVENTS}/{evento['id']}", headers=cabeceras_propietaria)
        assert sin_tocar.json()["theme_template_id"] is None
        assert sin_tocar.json()["theme_overrides"] is None
