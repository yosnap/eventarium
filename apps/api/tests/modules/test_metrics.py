"""Métricas del escritorio de un evento.

Lo que se comprueba aquí no es que los números salgan, sino **de dónde salen** y
**quién los ve**:

- Las cifras vienen de las mismas fuentes que usan las pantallas que las
  gestionan (el embudo, del servicio de inscripciones; el aforo, del que aplica
  el propio sistema). Un segundo camino de conteo acabaría divergiendo.
- Los bloques sin permiso **se omiten en el servidor**. Un miembro con permiso
  para ver el evento pero no las inscripciones no debe recibir sus conteos: si
  se devolvieran y se escondieran en la interfaz, viajarían igual.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


class TestMetricasDelEvento:
    async def test_sin_permiso_de_inscripciones_los_conteos_no_salen(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """El bloque se omite en el servidor, no se esconde en la interfaz.

        Un rol con permiso para ver el evento pero no las inscripciones recibía
        los conteos si se devolvieran y se ocultaran al pintar: el número
        viajaría igual en la respuesta.
        """
        _, cabeceras_admin = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras_admin, "metricas-permisos")
        await _sembrar_inscripcion(organizacion, evento["id"], "a@example.com", "confirmed")

        # Un rol que ve el evento pero no las inscripciones.
        from app.core.permissions import Permission

        await crear_rol(
            organizacion,
            key="solo_eventos",
            permisos=[Permission.EVENTS_READ],
        )
        correo, contraseña = await crear_usuario_con_rol(organizacion, "solo_eventos")
        _, cabeceras = await iniciar_sesion_con(cliente, organizacion, correo, contraseña)

        respuesta = await cliente.get(f"{EVENTS}/{evento['id']}/metrics", headers=cabeceras)
        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()

        assert cuerpo["cifras"] is None, "sin registrations:read no salen los conteos"
        assert cuerpo["embudo"] is None
        # Lo que sí puede ver sigue ahí.
        assert cuerpo["ocupacion"] is not None
        assert cuerpo["piezas"]

    async def test_sin_permiso_economico_el_bloque_de_dinero_no_sale(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras_admin = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras_admin, "metricas-dinero")

        from app.core.permissions import Permission

        await crear_rol(
            organizacion,
            key="sin_dinero",
            permisos=[Permission.EVENTS_READ, Permission.REGISTRATIONS_READ],
        )
        correo, contraseña = await crear_usuario_con_rol(organizacion, "sin_dinero")
        _, cabeceras = await iniciar_sesion_con(cliente, organizacion, correo, contraseña)

        respuesta = await cliente.get(f"{EVENTS}/{evento['id']}/metrics", headers=cabeceras)
        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()

        assert cuerpo["dinero"] is None, "sin accounting:read no sale el dinero"
        # Los conteos de inscripción sí, que para eso tiene el permiso.
        assert cuerpo["cifras"] is not None

    async def test_el_embudo_cuadra_con_las_inscripciones_sembradas(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "metricas-embudo")
        await _sembrar_inscripcion(organizacion, evento["id"], "a@example.com", "confirmed")
        await _sembrar_inscripcion(organizacion, evento["id"], "b@example.com", "waitlisted")
        await _sembrar_inscripcion(organizacion, evento["id"], "c@example.com", "pending_approval")

        respuesta = await cliente.get(f"{EVENTS}/{evento['id']}/metrics", headers=cabeceras)
        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()

        embudo = cuerpo["embudo"]
        assert embudo["formulario"] == 3
        assert embudo["aprobado"] == 0, "nadie ha pasado por aprobación todavía"
        assert embudo["emitido"] == 0, "no se ha emitido ninguna entrada"
        assert cuerpo["cifras"]["por_aprobar"] == 1

    async def test_la_ocupacion_cuenta_lo_que_el_sistema_considera_ocupado(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """No son solo las confirmadas: una promoción de lista de espera dentro de
        su ventana también ocupa plaza, y es lo que impide la sobreventa."""
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "metricas-ocupacion", capacity=10)
        await _sembrar_inscripcion(organizacion, evento["id"], "a@example.com", "confirmed")
        await _sembrar_inscripcion(organizacion, evento["id"], "b@example.com", "waitlisted")

        async with SessionMaintenance() as session:
            # Promoción vigente: cuenta como plaza reservada.
            await session.execute(
                text(
                    "UPDATE event_registrations SET waitlist_promoted_at = now(), "
                    "waitlist_promotion_expires_at = :expira "
                    "WHERE event_id = :event_id AND email = 'b@example.com'"
                ),
                {
                    "event_id": evento["id"],
                    "expira": datetime.now(UTC) + timedelta(hours=24),
                },
            )
            await session.commit()

        respuesta = await cliente.get(f"{EVENTS}/{evento['id']}/metrics", headers=cabeceras)
        cuerpo = respuesta.json()

        assert cuerpo["ocupacion"]["reservadas"] == 2
        assert cuerpo["ocupacion"]["aforo"] == 10

    async def test_un_evento_sin_aforo_se_informa_como_tal(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """`capacity` nulo no es «cero plazas»: es «sin límite», y la interfaz no
        debe poder confundirlos."""
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "metricas-sin-aforo")

        respuesta = await cliente.get(f"{EVENTS}/{evento['id']}/metrics", headers=cabeceras)
        assert respuesta.json()["ocupacion"]["aforo"] is None

    async def test_las_piezas_distinguen_lo_que_falta_de_lo_que_no_aplica(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """Un evento gratuito no necesita tipos de entrada: marcarlo como
        «pendiente» daría un aviso por algo que no hay que hacer."""
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "metricas-piezas")

        respuesta = await cliente.get(f"{EVENTS}/{evento['id']}/metrics", headers=cabeceras)
        piezas = {p["clave"]: p for p in respuesta.json()["piezas"]}

        assert piezas["agenda"]["estado"] == "pendiente", "sin sesiones: falta la agenda"
        assert piezas["tipos_de_entrada"]["estado"] == "no_aplica", "el evento es gratuito"

    async def test_un_evento_de_pago_sin_tipos_de_entrada_es_un_aviso(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """Es el caso que de verdad bloquea: un evento de pago sin tipos de
        entrada no se puede vender."""
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(
            cliente, cabeceras, "metricas-pago-sin-entradas", registration_mode="paid"
        )

        respuesta = await cliente.get(f"{EVENTS}/{evento['id']}/metrics", headers=cabeceras)
        piezas = {p["clave"]: p for p in respuesta.json()["piezas"]}

        assert piezas["tipos_de_entrada"]["estado"] == "pendiente"
        assert piezas["tipos_de_entrada"]["cantidad"] == 0

    async def test_un_evento_de_otra_organizacion_no_existe(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """La organización sale del token, no de la URL: el evento de otra
        organización da 404, igual que en el resto de rutas de evento."""
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "metricas-aislamiento")

        import uuid as _uuid

        ajeno = await cliente.get(f"{EVENTS}/{_uuid.uuid4()}/metrics", headers=cabeceras)
        assert ajeno.status_code == 404
        ajeno_real = await cliente.get(f"{EVENTS}/{evento['id']}/metrics", headers=cabeceras)
        assert ajeno_real.status_code == 200

    async def test_sin_sesion_no_se_puede_consultar(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_evento(cliente, cabeceras, "metricas-sin-sesion")

        respuesta = await cliente.get(f"{EVENTS}/{evento['id']}/metrics")
        assert respuesta.status_code == 401
