"""Borrado RGPD (`DELETE /admin/registrations/by-email`) de una inscripción
con un `event_payments` asociado (fase 6 del PRD, fase 1 de trabajo).

Verifica el criterio de éxito más delicado del plan: el borrado real
(`admin.service.borrar_inscrito_por_email`, no un `DELETE` suelto) no falla
por la FK compuesta de `event_payments.registration_id`, gracias a
`ondelete="SET NULL (registration_id)"`, y el pago sobrevive con
`organization_id` intacto — es el registro económico, no un dato personal.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import SessionMaintenance
from app.modules.events.models import Event
from app.modules.payments.models import EventPayment, EventTicketType, OrganizationStripeAccount
from app.modules.registrations.models import EventRegistration
from app.modules.users.models import User
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

ADMIN_BORRADO = "/api/v1/admin/registrations/by-email"
AHORA = datetime.now(UTC).replace(microsecond=0)


async def _hacer_superadmin(email: str) -> None:
    async with SessionMaintenance() as session:
        usuario = await session.scalar(select(User).where(User.email == email))
        assert usuario is not None
        usuario.is_superadmin = True
        await session.commit()


async def test_borrar_un_inscrito_con_pago_no_falla_y_deja_el_pago_huerfano(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug="evento-rgpd-pago",
            title="Evento con pago",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
            registration_mode="paid",
        )
        session.add(evento)
        await session.flush()

        inscripcion = EventRegistration(
            event_id=evento.id,
            organization_id=organizacion.id,
            email="pagador@example.com",
            full_name="Pagador de Prueba",
            status="confirmed",
        )
        session.add(inscripcion)
        await session.flush()

        cuenta = OrganizationStripeAccount(
            organization_id=organizacion.id, stripe_account_id="acct_rgpd"
        )
        session.add(cuenta)
        await session.flush()

        tipo = EventTicketType(
            event_id=evento.id,
            organization_id=organizacion.id,
            name="General",
            price_cents=2000,
            currency="eur",
        )
        session.add(tipo)
        await session.flush()

        pago = EventPayment(
            organization_id=organizacion.id,
            event_id=evento.id,
            registration_id=inscripcion.id,
            stripe_account_id=cuenta.stripe_account_id,
            ticket_type_id=tipo.id,
            amount_cents=2000,
            currency="eur",
            status="paid",
            paid_at=AHORA,
        )
        session.add(pago)
        await session.commit()
        pago_id = pago.id
        evento_id = evento.id
        registration_id = inscripcion.id

    await _hacer_superadmin(organizacion.owner_email)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.request(
        "DELETE",
        ADMIN_BORRADO,
        headers=cabeceras,
        json={
            "event_id": str(evento_id),
            "email": "pagador@example.com",
            "password": organizacion.owner_password,
        },
    )
    assert respuesta.status_code == 204, respuesta.text

    async with SessionMaintenance() as session:
        pago_tras_borrado = await session.get(EventPayment, pago_id)
        assert pago_tras_borrado is not None, "el pago no debe borrarse en cascada"
        assert pago_tras_borrado.registration_id is None
        assert pago_tras_borrado.organization_id == organizacion.id
        assert pago_tras_borrado.status == "paid"

        inscripcion_restante = await session.get(EventRegistration, registration_id)
        assert inscripcion_restante is None, "la inscripción sí debe borrarse (RGPD real)"
