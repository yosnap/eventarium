"""Métricas del escritorio de la organización.

Se comprueba lo mismo que en las métricas de un evento, aplicado al ámbito de la
organización entera:

- Las cifras por evento salen **agregadas en la misma consulta** que la lista, no
  de un recorrido del cliente.
- Los bloques sin permiso **se omiten en el servidor**.
- Un evento de otra organización no aparece: RLS filtra por organización, y esta
  prueba lo fija.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import SessionMaintenance
from tests.conftest import (
    OrganizacionDePrueba,
    crear_rol,
    crear_usuario_con_rol,
    iniciar_sesion,
    iniciar_sesion_con,
)

METRICS = "/api/v1/organizations/me/metrics"
EVENTS = "/api/v1/events"


async def _crear_evento(
    cliente: AsyncClient, cabeceras: dict[str, str], slug: str, **overrides: object
) -> dict:
    cuerpo = {
        "slug": slug,
        "title": f"Evento {slug}",
        "starts_at": "2026-10-01T09:00:00Z",
        "ends_at": "2026-10-02T18:00:00Z",
        "location_mode": "in_person",
        "location_name": "Sala principal",
        **overrides,
    }
    creado = await cliente.post(EVENTS, headers=cabeceras, json=cuerpo)
    assert creado.status_code == 201, creado.text
    return creado.json()


async def _sembrar_inscripcion(
    organizacion: OrganizacionDePrueba, evento_id: str, email: str, status: str
) -> None:
    async with SessionMaintenance() as session:
        await session.execute(
            text(
                """
                INSERT INTO event_registrations
                    (id, event_id, organization_id, email, full_name, status, created_at)
                VALUES
                    (gen_random_uuid(), :event_id, :org_id, :email, :nombre, :status, now())
                """
            ),
            {
                "event_id": evento_id,
                "org_id": str(organizacion.id),
                "email": email,
                "nombre": email.split("@")[0].title(),
                "status": status,
            },
        )
        await session.commit()


class TestMetricasDeLaOrganizacion:
    async def test_la_tabla_de_eventos_lleva_sus_cifras(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "org-tabla", capacity=10)
        await _sembrar_inscripcion(organizacion, evento["id"], "a@example.com", "confirmed")
        await _sembrar_inscripcion(organizacion, evento["id"], "b@example.com", "confirmed")
        await _sembrar_inscripcion(organizacion, evento["id"], "c@example.com", "pending_approval")

        respuesta = await cliente.get(METRICS, headers=cabeceras)
        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()

        fila = next(e for e in cuerpo["eventos"] if e["slug"] == "org-tabla")
        assert fila["confirmadas"] == 2
        assert fila["por_aprobar"] == 1
        assert fila["aforo"] == 10
        assert cuerpo["eventos_en_borrador"] == 1, "el evento recién creado está en borrador"

    async def test_sin_permiso_economico_no_salen_los_importes_de_la_tabla(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """Ni el bloque de dinero ni la columna de ingresos de cada evento."""
        _, cabeceras_admin = await iniciar_sesion(cliente, organizacion)
        await _crear_evento(cliente, cabeceras_admin, "org-dinero")

        from app.core.permissions import Permission

        await crear_rol(
            organizacion,
            key="sin_economia",
            permisos=[Permission.EVENTS_READ, Permission.REGISTRATIONS_READ],
        )
        correo, contraseña = await crear_usuario_con_rol(organizacion, "sin_economia")
        _, cabeceras = await iniciar_sesion_con(cliente, organizacion, correo, contraseña)

        respuesta = await cliente.get(METRICS, headers=cabeceras)
        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()

        assert cuerpo["dinero"] is None
        assert all(evento["ingresos_cents"] is None for evento in cuerpo["eventos"])

    async def test_sin_permiso_de_inscripciones_las_cifras_no_salen_pero_los_eventos_si(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras_admin = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras_admin, "org-sin-inscripciones")
        await _sembrar_inscripcion(organizacion, evento["id"], "a@example.com", "confirmed")

        from app.core.permissions import Permission

        await crear_rol(organizacion, key="solo_mirar", permisos=[Permission.EVENTS_READ])
        correo, contraseña = await crear_usuario_con_rol(organizacion, "solo_mirar")
        _, cabeceras = await iniciar_sesion_con(cliente, organizacion, correo, contraseña)

        respuesta = await cliente.get(METRICS, headers=cabeceras)
        cuerpo = respuesta.json()

        assert cuerpo["cifras"] is None
        # La lista de eventos sigue: es lo que puede ver.
        assert any(e["slug"] == "org-sin-inscripciones" for e in cuerpo["eventos"])
        # Y las columnas de inscripción **tampoco** llegan: el dato viajaba
        # dentro de cada fila, no en su propio bloque, así que omitir el bloque
        # de cifras no bastaba.
        assert all(e["confirmadas"] is None for e in cuerpo["eventos"])
        assert all(e["por_aprobar"] is None for e in cuerpo["eventos"])

    async def test_los_eventos_de_otra_organizacion_no_aparecen(
        self,
        cliente: AsyncClient,
        organizacion: OrganizacionDePrueba,
        otra_organizacion: OrganizacionDePrueba,
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        await _crear_evento(cliente, cabeceras, "org-aislamiento")

        _, cabeceras_ajenas = await iniciar_sesion(cliente, otra_organizacion)
        respuesta = await cliente.get(METRICS, headers=cabeceras_ajenas)

        assert respuesta.status_code == 200
        slugs = [evento["slug"] for evento in respuesta.json()["eventos"]]
        assert "org-aislamiento" not in slugs

    async def test_la_estructura_cuenta_miembros_roles_y_patrocinadores(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        respuesta = await cliente.get(METRICS, headers=cabeceras)

        estructura = respuesta.json()["estructura"]
        # El propietario es al menos un miembro, y hay roles de sistema.
        assert estructura["miembros"] >= 1
        assert estructura["roles"] >= 1

    async def test_sin_stripe_conectado_se_informa_como_no_conectada(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        respuesta = await cliente.get(METRICS, headers=cabeceras)

        stripe = respuesta.json()["stripe"]
        assert stripe["conectada"] is False
        assert stripe["charges_enabled"] is False

    async def test_una_organizacion_sin_eventos_no_revienta(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """Sin eventos no hay aforo que sumar: `aforo_total` es `None`, no cero."""
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        respuesta = await cliente.get(METRICS, headers=cabeceras)

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["eventos"] == []
        assert cuerpo["cifras"]["aforo_total"] is None
        assert cuerpo["cifras"]["reservadas"] == 0

    async def test_sin_sesion_no_se_puede_consultar(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        respuesta = await cliente.get(METRICS)
        assert respuesta.status_code == 401
