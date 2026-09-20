"""Lógica de superadministración: auditoría, exportación y borrado RGPD.

Fase 5 del PRD, fase 4 de trabajo. Todo corre bajo `get_maintenance_db`
(`app_maintainer`, `BYPASSRLS`) porque son operaciones globales de la
instalación, nunca de una sola organización.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
import zipfile
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog, registrar_auditoria
from app.core.security import hash_email_with_salt, verify_password
from app.modules.events.models import Event
from app.modules.registrations import repository as registrations_repository
from app.modules.registrations import service as registrations_service
from app.modules.registrations.models import EventRegistration
from app.modules.tickets import repository as tickets_repository
from app.modules.tickets.models import EventTicket, EventTicketScan
from app.modules.users.models import User
from app.shared.errors import AuthenticationError, NotFoundError

# Prefijo `'` (Excel/LibreOffice lo interpretan como "texto forzado") sobre
# toda celda que empiece por uno de estos caracteres: neutraliza la
# inyección de fórmulas en el texto libre de las respuestas, que cualquiera
# escribe sin autenticar en el formulario público (corrección de red-team).
_CARACTERES_PELIGROSOS_CSV = ("=", "+", "-", "@", "\t", "\r")


def _celda_segura(valor: Any) -> str:
    texto = "" if valor is None else str(valor)
    if texto.startswith(_CARACTERES_PELIGROSOS_CSV):
        return f"'{texto}"
    return texto


def _fecha_iso(valor: datetime | None) -> str:
    return valor.isoformat() if valor is not None else ""


async def verificar_password_de_superadmin(
    session: AsyncSession, *, user_id: uuid.UUID, password: str
) -> None:
    """Reautenticación reciente (Validation Log, sesión 1, pregunta 1 del
    plan): repetir la contraseña actual en el body de la petición."""
    usuario = await session.get(User, user_id)
    if usuario is None or not verify_password(password, usuario.password_hash):
        raise AuthenticationError("La contraseña no es correcta.")


async def list_audit_log(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID | None,
    date_from: datetime | None,
    date_to: datetime | None,
    action: str | None,
    limit: int,
    offset: int,
) -> tuple[list[AuditLog], int]:
    condiciones = []
    if organization_id is not None:
        condiciones.append(AuditLog.organization_id == organization_id)
    if date_from is not None:
        condiciones.append(AuditLog.created_at >= date_from)
    if date_to is not None:
        condiciones.append(AuditLog.created_at <= date_to)
    if action is not None:
        condiciones.append(AuditLog.action == action)

    total = await session.scalar(select(func.count()).select_from(AuditLog).where(*condiciones))
    filas = (
        await session.execute(
            select(AuditLog)
            .where(*condiciones)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars()
    return list(filas), int(total or 0)


def _get_evento_o_404(evento: Event | None) -> Event:
    if evento is None:
        raise NotFoundError("El evento no existe.")
    return evento


async def exportar_rgpd_evento(
    session: AsyncSession, *, event_id: uuid.UUID
) -> tuple[bytes, Event]:
    """ZIP en memoria con las inscripciones (+ respuestas) y las entradas de
    un evento — decisión #5 del plan: exporta inscripciones, no el evento en
    sí, que no es dato personal.

    El CSV de entradas **nunca** lleva el JWT del QR (Validation Log, sesión
    1, pregunta 4): es una credencial de acceso físico válida mientras el
    ticket no esté revocado, no solo un dato personal.
    """
    evento = _get_evento_o_404(await session.get(Event, event_id))

    preguntas = await registrations_repository.get_questions(
        session, evento.organization_id, evento.id
    )
    preguntas_por_id = {pregunta.id: pregunta for pregunta in preguntas}

    inscripciones = (
        await session.execute(
            select(EventRegistration)
            .where(
                EventRegistration.organization_id == evento.organization_id,
                EventRegistration.event_id == evento.id,
            )
            .order_by(EventRegistration.created_at)
        )
    ).scalars()

    buffer_inscripciones = io.StringIO()
    escritor = csv.writer(buffer_inscripciones)
    escritor.writerow(
        [
            "registration_id",
            "email",
            "full_name",
            "status",
            "created_at",
            "verified_at",
            "confirmed_at",
            "question",
            "answer",
        ]
    )
    for inscripcion in inscripciones:
        base = [
            str(inscripcion.id),
            inscripcion.email,
            inscripcion.full_name,
            inscripcion.status,
            _fecha_iso(inscripcion.created_at),
            _fecha_iso(inscripcion.verified_at),
            _fecha_iso(inscripcion.confirmed_at),
        ]
        respuestas = inscripcion.answers
        if not respuestas:
            escritor.writerow([_celda_segura(c) for c in (*base, "", "")])
            continue
        for respuesta in respuestas:
            pregunta = preguntas_por_id.get(respuesta.question_id)
            etiqueta = pregunta.label if pregunta is not None else "(pregunta eliminada)"
            valor = (
                respuesta.value
                if isinstance(respuesta.value, str)
                else json.dumps(respuesta.value, ensure_ascii=False)
            )
            escritor.writerow([_celda_segura(c) for c in (*base, etiqueta, valor)])

    tickets = (
        await session.execute(
            select(EventTicket).where(
                EventTicket.organization_id == evento.organization_id,
                EventTicket.event_id == evento.id,
            )
        )
    ).scalars()

    buffer_tickets = io.StringIO()
    escritor_tickets = csv.writer(buffer_tickets)
    escritor_tickets.writerow(["registration_id", "issued_at", "used_at", "revoked_at", "status"])
    for ticket in tickets:
        if ticket.revoked_at is not None:
            estado = "revoked"
        elif ticket.used_at is not None:
            estado = "used"
        else:
            estado = "issued"
        escritor_tickets.writerow(
            [
                _celda_segura(c)
                for c in (
                    str(ticket.registration_id),
                    _fecha_iso(ticket.issued_at),
                    _fecha_iso(ticket.used_at),
                    _fecha_iso(ticket.revoked_at),
                    estado,
                )
            ]
        )

    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("inscripciones.csv", buffer_inscripciones.getvalue())
        zip_file.writestr("entradas.csv", buffer_tickets.getvalue())
    return memoria.getvalue(), evento


async def borrar_inscrito_por_email(
    session: AsyncSession, *, event_id: uuid.UUID, email: str
) -> tuple[uuid.UUID, uuid.UUID]:
    """Borrado RGPD real (no soft-delete) de un inscrito por email —
    decisión #6 del plan.

    Reutiliza `registrations.service.cancel_registration` en vez de un
    `DELETE` SQL directo: revoca la entrada y promueve a la lista de espera
    igual que una cancelación normal si liberaba una plaza reservada. Antes
    de que la cascada de borrado llegue a `event_ticket_scans`, esos
    escaneos se anonimizan (`ticket_id = NULL`) para conservar el recuento
    de aforo real sin conservar el vínculo con la persona borrada.
    """
    evento = _get_evento_o_404(await session.get(Event, event_id))
    email_normalizado = email.strip().lower()

    inscripcion = await registrations_repository.get_registration_by_event_and_email(
        session, evento.organization_id, evento.id, email_normalizado
    )
    if inscripcion is None:
        raise NotFoundError("No existe ninguna inscripción con ese email en este evento.")

    registration_id = inscripcion.id
    organization_id = evento.organization_id

    if inscripcion.status not in ("cancelled", "rejected"):
        await registrations_service.cancel_registration(
            session,
            organization_id=organization_id,
            event_id=evento.id,
            registration_id=registration_id,
        )

    ticket = await tickets_repository.get_ticket_by_registration(
        session, organization_id, registration_id
    )
    if ticket is not None:
        await session.execute(
            update(EventTicketScan)
            .where(EventTicketScan.ticket_id == ticket.id)
            .values(ticket_id=None)
        )

    inscripcion_actual = await session.get(EventRegistration, registration_id)
    if inscripcion_actual is not None:
        await session.delete(inscripcion_actual)
    await session.flush()

    return registration_id, organization_id


def audit_detail_borrado(*, email: str, registration_id: uuid.UUID) -> dict[str, Any]:
    """`detail` de `audit_log` para un borrado RGPD: hash con sal del email
    (nunca en claro, decisión #6) más el `registration_id` ya borrado."""
    return {"email_hash": hash_email_with_salt(email), "registration_id": str(registration_id)}


__all__ = [
    "audit_detail_borrado",
    "borrar_inscrito_por_email",
    "exportar_rgpd_evento",
    "list_audit_log",
    "registrar_auditoria",
    "verificar_password_de_superadmin",
]
