"""Escaneo y check-in de entradas QR.

Fase 4 del PRD, fase 2 de trabajo. Separado de `service.py` (emisión,
revocación y firma del JWT, fase 1 de trabajo): son preocupaciones distintas
— aquí se decodifica y se decide `valid`/`duplicate`/`revoked`/`expired`/
`invalid_signature`/`not_found`/`manual`, allí se crea la fila y se firma.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.events import repository as events_repository
from app.modules.events.models import EventMember
from app.modules.registrations.models import EventRegistration
from app.modules.tickets import repository
from app.modules.tickets.models import EventTicket, EventTicketScan
from app.modules.tickets.schemas import ScanRequest, TicketScanResult


@dataclass(frozen=True, slots=True)
class ResultadoEscaneo:
    """Resultado de un escaneo, con lo necesario para construir la respuesta."""

    client_scan_id: uuid.UUID
    result: TicketScanResult
    ticket: EventTicket | None
    registration: EventRegistration | None


def _decodificar_token_qr(
    token: str,
) -> tuple[TicketScanResult | None, uuid.UUID | None, uuid.UUID | None]:
    """Verifica firma y caducidad. Devuelve `(resultado_de_error, None, None)`
    si falla, o `(None, ticket_id, event_id_del_token)` si decodifica.

    No se distingue más allá de `expired`/`invalid_signature` (mismo
    principio de no filtrar información que `decode_access_token`): un JWT
    ajeno o manipulado no debe revelar por qué falló exactamente.

    `eid` se devuelve para que el llamador lo compare contra el evento de la
    URL **antes** de tocar la base de datos — la comprobación real de
    pertenencia sigue siendo `ticket.event_id` (la fuente de verdad), pero
    exigir `eid` en el JWT sin nunca leerlo sería confuso para quien lea el
    código después.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.ticket_qr_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "tid", "eid"]},
        )
    except jwt.ExpiredSignatureError:
        return "expired", None, None
    except jwt.PyJWTError:
        return "invalid_signature", None, None

    try:
        return None, uuid.UUID(str(payload["tid"])), uuid.UUID(str(payload["eid"]))
    except ValueError:
        return "invalid_signature", None, None


def _resolver_y_marcar_uso(
    ticket: EventTicket | None,
    *,
    scanner_event_member_id: uuid.UUID,
    resultado_valido: TicketScanResult,
) -> TicketScanResult:
    """La regla compartida por el escaneo y el check-in manual: revocada,
    duplicada o válida — y en el último caso, marca el uso."""
    if ticket is None:
        return "not_found"
    if ticket.revoked_at is not None:
        return "revoked"
    if ticket.used_at is not None:
        return "duplicate"
    ticket.used_at = datetime.now(UTC)
    ticket.used_by_event_member_id = scanner_event_member_id
    return resultado_valido


async def resolver_event_member_del_usuario(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID, user_id: uuid.UUID
) -> EventMember:
    """Resuelve (o crea) el `EventMember` del usuario autenticado para este evento.

    `tickets:write` es un permiso de organización, no de roster (decisión #7
    del plan): quien escanea puede no participar en este evento en concreto.
    Se usa cualquiera de sus membresías de organización para darlo de alta en
    el roster del evento la primera vez que escanea — igual que si un
    organizador lo hubiera añadido a mano; solo así puede completarse
    `event_ticket_scans.scanned_by_event_member_id`, que no es nulo.
    """
    organization_member_id = await repository.get_any_organization_member_id(
        session, organization_id, user_id
    )
    if organization_member_id is None:  # pragma: no cover - exige sesión ya autenticada en la org
        raise RuntimeError(f"El usuario {user_id} no tiene membresía en esta organización.")

    existente = await events_repository.get_event_member_by_organization_member(
        session, organization_id, event_id, organization_member_id
    )
    if existente is not None:
        return existente

    miembro = EventMember(
        event_id=event_id,
        organization_id=organization_id,
        organization_member_id=organization_member_id,
    )
    try:
        # `begin_nested`: mismo motivo que `emitir_entrada` — no perder el
        # contexto RLS de la transacción de la petición ante la carrera de
        # dos escaneos casi simultáneos de la misma persona dándola de alta.
        async with session.begin_nested():
            session.add(miembro)
            await session.flush()
    except IntegrityError:
        ganador = await events_repository.get_event_member_by_organization_member(
            session, organization_id, event_id, organization_member_id
        )
        if ganador is None:  # pragma: no cover - el UNIQUE lo hace imposible
            raise
        return ganador
    return miembro


async def _resultado_desde_scan(
    session: AsyncSession, organization_id: uuid.UUID, scan: EventTicketScan
) -> ResultadoEscaneo:
    ticket: EventTicket | None = None
    registration: EventRegistration | None = None
    if scan.ticket_id is not None:
        ticket = await repository.get_ticket(session, organization_id, scan.ticket_id)
        if ticket is not None:
            registration = await session.get(EventRegistration, ticket.registration_id)
    return ResultadoEscaneo(
        client_scan_id=scan.client_scan_id,
        result=scan.result,  # type: ignore[arg-type]
        ticket=ticket,
        registration=registration,
    )


async def procesar_escaneo(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    token: str,
    client_scan_id: uuid.UUID,
    client_scanned_at: datetime,
    device_label: str | None,
    scanner_event_member_id: uuid.UUID,
) -> ResultadoEscaneo:
    """Procesa un escaneo de QR. Idempotente por `client_scan_id`: un
    reintento de red del mismo escaneo devuelve el resultado ya guardado sin
    volver a evaluar nada."""
    existente = await repository.get_scan_by_client_scan_id(
        session, organization_id, client_scan_id
    )
    if existente is not None:
        return await _resultado_desde_scan(session, organization_id, existente)

    resultado_error, ticket_id, eid = _decodificar_token_qr(token)
    ticket: EventTicket | None = None
    resultado: TicketScanResult
    if resultado_error is not None or ticket_id is None or eid != event_id:
        # `eid != event_id` incluye el caso legítimo de decodificar bien un
        # QR de otro evento: se trata igual que una firma inválida, sin
        # tocar la base de datos — `ticket.event_id` (comprobado justo
        # debajo para el caso `eid` correcto) sigue siendo la fuente de
        # verdad real, esto es solo la comprobación temprana.
        resultado = resultado_error or "invalid_signature"
    else:
        # `FOR UPDATE`: serializa dos escaneos casi simultáneos del mismo QR
        # en dos dispositivos — el caso real que hay que resolver.
        candidato = await repository.get_ticket_for_update(session, organization_id, ticket_id)
        if candidato is not None and candidato.event_id != event_id:
            # Entrada de otro evento de la misma organización: no es de este
            # dispositivo de check-in, se trata igual que si no existiera.
            candidato = None
        ticket = candidato
        resultado = _resolver_y_marcar_uso(
            ticket, scanner_event_member_id=scanner_event_member_id, resultado_valido="valid"
        )
        if resultado == "not_found":
            ticket = None

    scan = EventTicketScan(
        ticket_id=ticket.id if ticket is not None else None,
        organization_id=organization_id,
        event_id=event_id,
        scanned_by_event_member_id=scanner_event_member_id,
        client_scan_id=client_scan_id,
        client_scanned_at=client_scanned_at,
        result=resultado,
        device_label=device_label,
    )
    try:
        # `begin_nested`: dos reintentos de red del mismo `client_scan_id`
        # casi simultáneos no deben poder colarse los dos como filas nuevas.
        async with session.begin_nested():
            session.add(scan)
            await session.flush()
    except IntegrityError:
        ganador = await repository.get_scan_by_client_scan_id(
            session, organization_id, client_scan_id
        )
        if ganador is None:  # pragma: no cover - el UNIQUE lo hace imposible
            raise
        return await _resultado_desde_scan(session, organization_id, ganador)

    registration = (
        await session.get(EventRegistration, ticket.registration_id) if ticket is not None else None
    )
    return ResultadoEscaneo(
        client_scan_id=client_scan_id, result=resultado, ticket=ticket, registration=registration
    )


async def procesar_escaneos_en_lote(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    escaneos: list[ScanRequest],
    scanner_event_member_id: uuid.UUID,
) -> list[ResultadoEscaneo]:
    """Procesa varios escaneos en el orden de `client_scanned_at` — el orden
    en que de verdad ocurrieron en el dispositivo, no el orden de llegada de
    la sincronización."""
    ordenados = sorted(escaneos, key=lambda item: item.client_scanned_at)
    resultados = []
    for escaneo in ordenados:
        resultados.append(
            await procesar_escaneo(
                session,
                organization_id=organization_id,
                event_id=event_id,
                token=escaneo.token,
                client_scan_id=escaneo.client_scan_id,
                client_scanned_at=escaneo.client_scanned_at,
                device_label=escaneo.device_label,
                scanner_event_member_id=scanner_event_member_id,
            )
        )
    return resultados


async def procesar_check_in_manual(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    ticket_id: uuid.UUID,
    scanner_event_member_id: uuid.UUID,
) -> ResultadoEscaneo:
    """Mismo efecto que un escaneo válido, pero originado desde la búsqueda
    manual: mismas reglas de duplicado/revocado, `result = manual` en vez de
    `valid` para diferenciarlo en la auditoría.

    No hay QR que decodificar (la entrada ya viene resuelta por `ticket_id`
    desde la búsqueda), así que `client_scan_id`/`client_scanned_at` se
    generan aquí: es una acción síncrona del staff, no un evento encolado
    desde un dispositivo sin conexión."""
    candidato = await repository.get_ticket_for_update(session, organization_id, ticket_id)
    if candidato is not None and candidato.event_id != event_id:
        candidato = None
    resultado = _resolver_y_marcar_uso(
        candidato, scanner_event_member_id=scanner_event_member_id, resultado_valido="manual"
    )
    ticket = candidato if resultado != "not_found" else None

    scan = EventTicketScan(
        ticket_id=ticket.id if ticket is not None else None,
        organization_id=organization_id,
        event_id=event_id,
        scanned_by_event_member_id=scanner_event_member_id,
        client_scan_id=uuid.uuid4(),
        client_scanned_at=datetime.now(UTC),
        result=resultado,
        device_label=None,
    )
    session.add(scan)
    await session.flush()

    registration = (
        await session.get(EventRegistration, ticket.registration_id) if ticket is not None else None
    )
    return ResultadoEscaneo(
        client_scan_id=scan.client_scan_id,
        result=resultado,
        ticket=ticket,
        registration=registration,
    )
