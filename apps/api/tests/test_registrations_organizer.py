"""Panel de organizador sobre inscripciones: aprobación, lista de espera y
preguntas personalizadas.

Fase 3 del PRD, fase 3 de trabajo. Mismo patrón que
`test_registrations_public.py`: cliente HTTP real, `Host` para resolver la
organización, y helpers directos contra `SessionMaintenance` para preparar
estados que el formulario público no puede producir por sí solo (p. ej.
`pending_approval` sin pasar por Turnstile).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import SessionMaintenance
from app.core.tasks import send_registration_verification_email
from app.modules.auth.verification import (
    PROPOSITO_PROMOCION_LISTA_ESPERA,
    consume_token,
    generate_token,
)
from app.modules.registrations.models import (
    EventRegistration,
    EventRegistrationAnswer,
    EventRegistrationQuestion,
)
from app.modules.registrations.service import expire_waitlist_promotions
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

EVENTS = "/api/v1/events"
CONFIRM_PROMOTION = "/api/v1/public/registrations/confirm-waitlist-promotion"
AHORA = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture(autouse=True)
def _correo_de_verificacion_encolado_sincrono():
    with patch.object(send_registration_verification_email, "kiq", new_callable=AsyncMock) as tarea:
        yield tarea


def _payload_evento(slug: str, **overrides: object) -> dict:
    payload = {
        "slug": slug,
        "title": f"Evento {slug}",
        "starts_at": AHORA.isoformat(),
        "ends_at": (AHORA + timedelta(days=2)).isoformat(),
        "location_mode": "in_person",
    }
    payload.update(overrides)
    return payload


async def _crear_y_publicar_evento(
    cliente: AsyncClient, cabeceras: dict[str, str], slug: str, **overrides: object
) -> dict:
    creacion = await cliente.post(
        EVENTS, headers=cabeceras, json=_payload_evento(slug, **overrides)
    )
    assert creacion.status_code == 201, creacion.text
    evento = creacion.json()
    publicacion = await cliente.patch(
        f"{EVENTS}/{evento['id']}",
        headers=cabeceras,
        json={"status": "published", "visibility": "public"},
    )
    assert publicacion.status_code == 200, publicacion.text
    return publicacion.json()


async def _crear_inscripcion(
    organizacion: OrganizacionDePrueba,
    evento: dict,
    *,
    email: str,
    status: str = "confirmed",
    full_name: str = "Asistente de Prueba",
) -> str:
    """Inserta una inscripción directamente, saltándose el formulario público:
    el panel de organizador debe funcionar sobre cualquier estado alcanzable,
    y provocar `pending_approval` por el flujo real exigiría Turnstile."""
    ahora = datetime.now(UTC)
    async with SessionMaintenance() as session:
        inscripcion = EventRegistration(
            event_id=uuid.UUID(evento["id"]),
            organization_id=organizacion.id,
            email=email,
            full_name=full_name,
            status=status,
            confirmed_at=ahora if status == "confirmed" else None,
        )
        session.add(inscripcion)
        await session.commit()
        await session.refresh(inscripcion)
        return str(inscripcion.id)


async def _estado(registration_id: str) -> str | None:
    async with SessionMaintenance() as session:
        return await session.scalar(
            text("SELECT status FROM event_registrations WHERE id = :id"), {"id": registration_id}
        )


async def _fila(registration_id: str) -> dict:
    async with SessionMaintenance() as session:
        fila = (
            (
                await session.execute(
                    text(
                        "SELECT status, waitlist_promoted_at, waitlist_promotion_expires_at, "
                        "waitlist_position FROM event_registrations WHERE id = :id"
                    ),
                    {"id": registration_id},
                )
            )
            .mappings()
            .one()
        )
    return dict(fila)


class TestAprobacionYRechazo:
    async def test_aprobar_con_aforo_libre_confirma(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(
            cliente, cabeceras, "aprobacion-aforo-libre", registration_mode="approval", capacity=5
        )
        registration_id = await _crear_inscripcion(
            organizacion, evento, email="pendiente@example.com", status="pending_approval"
        )

        respuesta = await cliente.post(
            f"{EVENTS}/{evento['id']}/registrations/{registration_id}/approve", headers=cabeceras
        )

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["status"] == "confirmed"

    async def test_aprobar_con_aforo_agotado_deja_en_lista_de_espera(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(
            cliente, cabeceras, "aprobacion-aforo-agotado", registration_mode="approval", capacity=1
        )
        await _crear_inscripcion(
            organizacion, evento, email="confirmado@example.com", status="confirmed"
        )
        registration_id = await _crear_inscripcion(
            organizacion, evento, email="pendiente@example.com", status="pending_approval"
        )

        respuesta = await cliente.post(
            f"{EVENTS}/{evento['id']}/registrations/{registration_id}/approve", headers=cabeceras
        )

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["status"] == "waitlisted"

    async def test_aprobar_una_inscripcion_que_no_esta_pendiente_falla_409(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "aprobar-no-pendiente")
        registration_id = await _crear_inscripcion(
            organizacion, evento, email="confirmado@example.com", status="confirmed"
        )

        respuesta = await cliente.post(
            f"{EVENTS}/{evento['id']}/registrations/{registration_id}/approve", headers=cabeceras
        )

        assert respuesta.status_code == 409

    async def test_rechazar_una_pendiente_de_aprobacion(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(
            cliente, cabeceras, "rechazo", registration_mode="approval"
        )
        registration_id = await _crear_inscripcion(
            organizacion, evento, email="pendiente@example.com", status="pending_approval"
        )

        respuesta = await cliente.post(
            f"{EVENTS}/{evento['id']}/registrations/{registration_id}/reject", headers=cabeceras
        )

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["status"] == "rejected"

    async def test_rechazar_una_inscripcion_confirmada_falla_409(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "rechazar-confirmada")
        registration_id = await _crear_inscripcion(
            organizacion, evento, email="confirmado@example.com", status="confirmed"
        )

        respuesta = await cliente.post(
            f"{EVENTS}/{evento['id']}/registrations/{registration_id}/reject", headers=cabeceras
        )

        assert respuesta.status_code == 409


class TestCancelacionYListaDeEspera:
    async def test_cancelar_una_confirmada_promueve_a_la_primera_en_espera(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "cancelar-promueve", capacity=1)
        confirmada_id = await _crear_inscripcion(
            organizacion, evento, email="confirmado@example.com", status="confirmed"
        )
        en_espera_id = await _crear_inscripcion(
            organizacion, evento, email="espera@example.com", status="waitlisted"
        )

        respuesta = await cliente.post(
            f"{EVENTS}/{evento['id']}/registrations/{confirmada_id}/cancel", headers=cabeceras
        )

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["status"] == "cancelled"

        fila = await _fila(en_espera_id)
        assert fila["status"] == "waitlisted"
        assert fila["waitlist_promoted_at"] is not None
        assert fila["waitlist_promotion_expires_at"] is not None

    async def test_cancelar_sin_lista_de_espera_no_promueve_a_nadie(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "cancelar-sin-espera")
        confirmada_id = await _crear_inscripcion(
            organizacion, evento, email="confirmado@example.com", status="confirmed"
        )

        respuesta = await cliente.post(
            f"{EVENTS}/{evento['id']}/registrations/{confirmada_id}/cancel", headers=cabeceras
        )

        assert respuesta.status_code == 200, respuesta.text

    async def test_cancelar_una_ya_cancelada_falla_409(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "cancelar-dos-veces")
        registration_id = await _crear_inscripcion(
            organizacion, evento, email="cancelado@example.com", status="cancelled"
        )

        respuesta = await cliente.post(
            f"{EVENTS}/{evento['id']}/registrations/{registration_id}/cancel", headers=cabeceras
        )

        assert respuesta.status_code == 409

    async def test_confirmar_promocion_con_token_valido(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(
            cliente, cabeceras, "confirmar-promocion", capacity=1
        )
        confirmada_id = await _crear_inscripcion(
            organizacion, evento, email="confirmado@example.com", status="confirmed"
        )
        en_espera_id = await _crear_inscripcion(
            organizacion, evento, email="espera@example.com", status="waitlisted"
        )
        await cliente.post(
            f"{EVENTS}/{evento['id']}/registrations/{confirmada_id}/cancel", headers=cabeceras
        )
        token = await generate_token(PROPOSITO_PROMOCION_LISTA_ESPERA, en_espera_id)

        respuesta = await cliente.post(
            CONFIRM_PROMOTION, headers={"Host": organizacion.host}, json={"token": token}
        )

        assert respuesta.status_code == 200, respuesta.text
        assert await _estado(en_espera_id) == "confirmed"

    async def test_confirmar_promocion_con_token_invalido_falla(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        respuesta = await cliente.post(
            CONFIRM_PROMOTION, headers={"Host": organizacion.host}, json={"token": "inventado"}
        )
        assert respuesta.status_code == 422

    async def test_confirmar_promocion_caducada_falla_y_no_consume_dos_veces(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "promocion-caducada")
        en_espera_id = await _crear_inscripcion(
            organizacion, evento, email="espera@example.com", status="waitlisted"
        )
        ahora = datetime.now(UTC)
        async with SessionMaintenance() as session:
            await session.execute(
                text(
                    "UPDATE event_registrations SET waitlist_promoted_at = :promovida, "
                    "waitlist_promotion_expires_at = :caducada WHERE id = :id"
                ),
                {"promovida": ahora, "caducada": ahora - timedelta(hours=1), "id": en_espera_id},
            )
            await session.commit()
        token = await generate_token(PROPOSITO_PROMOCION_LISTA_ESPERA, en_espera_id)

        respuesta = await cliente.post(
            CONFIRM_PROMOTION, headers={"Host": organizacion.host}, json={"token": token}
        )

        assert respuesta.status_code == 422
        assert await _estado(en_espera_id) == "waitlisted"
        # El token era de un solo uso (`GETDEL`): aunque la promoción haya
        # caducado, reintentarlo no debe encontrar nada que consumir de nuevo.
        assert await consume_token(PROPOSITO_PROMOCION_LISTA_ESPERA, token) is None

    async def test_tarea_cron_reasigna_una_promocion_caducada(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "cron-reasigna", capacity=1)
        caducada_id = await _crear_inscripcion(
            organizacion, evento, email="caducada@example.com", status="waitlisted"
        )
        siguiente_id = await _crear_inscripcion(
            organizacion, evento, email="siguiente@example.com", status="waitlisted"
        )
        ahora = datetime.now(UTC)
        async with SessionMaintenance() as session:
            await session.execute(
                text(
                    "UPDATE event_registrations SET waitlist_promoted_at = :promovida, "
                    "waitlist_promotion_expires_at = :caducada, waitlist_position = 1 "
                    "WHERE id = :id"
                ),
                {"promovida": ahora, "caducada": ahora - timedelta(hours=1), "id": caducada_id},
            )
            await session.commit()

        await expire_waitlist_promotions()

        caducada = await _fila(caducada_id)
        siguiente = await _fila(siguiente_id)
        assert caducada["status"] == "waitlisted"
        assert caducada["waitlist_promoted_at"] is None
        assert caducada["waitlist_position"] is not None and caducada["waitlist_position"] > 1
        assert siguiente["status"] == "waitlisted"
        assert siguiente["waitlist_promoted_at"] is not None
        assert siguiente["waitlist_promotion_expires_at"] is not None


class TestListadoYEstadisticas:
    async def test_listar_inscripciones_filtra_por_estado(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "listado-filtro")
        await _crear_inscripcion(
            organizacion, evento, email="confirmado@example.com", status="confirmed"
        )
        await _crear_inscripcion(
            organizacion, evento, email="espera@example.com", status="waitlisted"
        )

        respuesta = await cliente.get(
            f"{EVENTS}/{evento['id']}/registrations",
            headers=cabeceras,
            params={"status": "waitlisted"},
        )

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["total"] == 1
        assert cuerpo["items"][0]["email"] == "espera@example.com"

    async def test_detalle_incluye_respuestas_y_consentimiento(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "detalle-respuestas")
        async with SessionMaintenance() as session:
            pregunta = EventRegistrationQuestion(
                event_id=uuid.UUID(evento["id"]),
                organization_id=organizacion.id,
                type="short_text",
                label="¿Empresa?",
                required=False,
                sort_order=0,
            )
            session.add(pregunta)
            await session.flush()
            registration_id = await _crear_inscripcion(
                organizacion, evento, email="detalle@example.com", status="confirmed"
            )
            session.add(
                EventRegistrationAnswer(
                    registration_id=uuid.UUID(registration_id),
                    question_id=pregunta.id,
                    organization_id=organizacion.id,
                    value="ACME",
                )
            )
            await session.commit()

        respuesta = await cliente.get(
            f"{EVENTS}/{evento['id']}/registrations/{registration_id}", headers=cabeceras
        )

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["answers"] == [
            {"question_id": str(pregunta.id), "label": "¿Empresa?", "value": "ACME"}
        ]

    async def test_estadisticas_cuadran_con_un_escenario_sembrado(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "estadisticas")
        await _crear_inscripcion(
            organizacion, evento, email="a@example.com", status="pending_verification"
        )
        await _crear_inscripcion(
            organizacion, evento, email="b@example.com", status="pending_approval"
        )
        await _crear_inscripcion(organizacion, evento, email="c@example.com", status="confirmed")
        await _crear_inscripcion(organizacion, evento, email="d@example.com", status="rejected")
        await _crear_inscripcion(organizacion, evento, email="e@example.com", status="cancelled")
        await _crear_inscripcion(organizacion, evento, email="f@example.com", status="waitlisted")
        async with SessionMaintenance() as session:
            await session.execute(
                text(
                    "UPDATE event_registrations SET verified_at = now() "
                    "WHERE event_id = :event_id AND email IN "
                    "('b@example.com', 'c@example.com', 'd@example.com')"
                ),
                {"event_id": evento["id"]},
            )
            await session.commit()

        respuesta = await cliente.get(
            f"{EVENTS}/{evento['id']}/registrations/stats", headers=cabeceras
        )

        assert respuesta.status_code == 200, respuesta.text
        stats = respuesta.json()
        assert stats["initiated"] == 6
        assert stats["verified"] == 3
        assert stats["pending_approval"] == 1
        assert stats["confirmed"] == 1
        assert stats["rejected"] == 1
        assert stats["cancelled"] == 1
        assert stats["waitlisted"] == 1
        assert stats["verified_conversion_rate"] == pytest.approx(3 / 6)
        assert stats["confirmed_conversion_rate"] == pytest.approx(1 / 3)


class TestGestionDePreguntas:
    async def test_crear_editar_y_borrar_una_pregunta_sin_respuestas(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "preguntas-crud")

        creacion = await cliente.post(
            f"{EVENTS}/{evento['id']}/registration-questions",
            headers=cabeceras,
            json={"type": "short_text", "label": "¿Empresa?", "required": False, "sort_order": 0},
        )
        assert creacion.status_code == 201, creacion.text
        pregunta_id = creacion.json()["id"]

        edicion = await cliente.patch(
            f"{EVENTS}/{evento['id']}/registration-questions/{pregunta_id}",
            headers=cabeceras,
            json={"type": "single_choice", "options": ["S", "M", "L"], "label": "¿Camiseta?"},
        )
        assert edicion.status_code == 200, edicion.text
        assert edicion.json()["type"] == "single_choice"
        assert edicion.json()["options"] == ["S", "M", "L"]

        borrado = await cliente.delete(
            f"{EVENTS}/{evento['id']}/registration-questions/{pregunta_id}", headers=cabeceras
        )
        assert borrado.status_code == 204

    async def test_cambiar_tipo_de_una_pregunta_con_respuestas_falla_409(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "preguntas-con-respuestas")
        async with SessionMaintenance() as session:
            pregunta = EventRegistrationQuestion(
                event_id=uuid.UUID(evento["id"]),
                organization_id=organizacion.id,
                type="short_text",
                label="¿Empresa?",
                required=False,
                sort_order=0,
            )
            session.add(pregunta)
            await session.flush()
            registration_id = await _crear_inscripcion(
                organizacion, evento, email="respondio@example.com", status="confirmed"
            )
            session.add(
                EventRegistrationAnswer(
                    registration_id=uuid.UUID(registration_id),
                    question_id=pregunta.id,
                    organization_id=organizacion.id,
                    value="ACME",
                )
            )
            await session.commit()
            pregunta_id = str(pregunta.id)

        edicion = await cliente.patch(
            f"{EVENTS}/{evento['id']}/registration-questions/{pregunta_id}",
            headers=cabeceras,
            json={"type": "single_choice", "options": ["S", "M"]},
        )
        assert edicion.status_code == 409

        borrado = await cliente.delete(
            f"{EVENTS}/{evento['id']}/registration-questions/{pregunta_id}", headers=cabeceras
        )
        assert borrado.status_code == 409

    async def test_editar_label_de_una_pregunta_con_respuestas_funciona(
        self, cliente: AsyncClient, organizacion: OrganizacionDePrueba
    ) -> None:
        """Corrige un typo aunque ya haya una respuesta: la restricción de la
        decisión #6 es sobre `type`/`options`, no sobre cualquier edición."""
        _, cabeceras = await iniciar_sesion(cliente, organizacion)
        evento = await _crear_y_publicar_evento(cliente, cabeceras, "preguntas-typo")
        async with SessionMaintenance() as session:
            pregunta = EventRegistrationQuestion(
                event_id=uuid.UUID(evento["id"]),
                organization_id=organizacion.id,
                type="short_text",
                label="¿Empresaa?",
                required=False,
                sort_order=0,
            )
            session.add(pregunta)
            await session.flush()
            registration_id = await _crear_inscripcion(
                organizacion, evento, email="respondio@example.com", status="confirmed"
            )
            session.add(
                EventRegistrationAnswer(
                    registration_id=uuid.UUID(registration_id),
                    question_id=pregunta.id,
                    organization_id=organizacion.id,
                    value="ACME",
                )
            )
            await session.commit()
            pregunta_id = str(pregunta.id)

        edicion = await cliente.patch(
            f"{EVENTS}/{evento['id']}/registration-questions/{pregunta_id}",
            headers=cabeceras,
            json={"label": "¿Empresa?"},
        )

        assert edicion.status_code == 200, edicion.text
        assert edicion.json()["label"] == "¿Empresa?"
