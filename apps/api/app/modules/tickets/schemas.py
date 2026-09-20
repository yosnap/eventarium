"""Esquemas del escaneo y check-in de entradas (fase 4 del PRD, fase 2 de trabajo)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TicketScanResult = Literal[
    "valid", "duplicate", "expired", "invalid_signature", "revoked", "not_found", "manual"
]

# Tope de un lote de sincronización: cada elemento abre su propia sección
# crítica (`FOR UPDATE` + `SAVEPOINT`) dentro de una única transacción — sin
# límite, una cola offline de horas podría convertirse en una transacción
# larguísima que retiene bloqueos sobre `event_tickets` todo ese tiempo.
_LIMITE_LOTE_DE_ESCANEO = 200


class ScanRequest(BaseModel):
    """Un intento de escaneo, tal como lo encola la app de escaneo (fase 3)."""

    token: str
    client_scan_id: uuid.UUID
    client_scanned_at: datetime
    device_label: str | None = None


class ScanBatchRequest(BaseModel):
    """Varios escaneos encolados sin conexión, sincronizados en una petición."""

    scans: list[ScanRequest] = Field(max_length=_LIMITE_LOTE_DE_ESCANEO)


class TicketScanResultOut(BaseModel):
    """Resultado de un escaneo — nunca lleva el JWT de vuelta (no-funcional del plan)."""

    client_scan_id: uuid.UUID
    result: TicketScanResult
    ticket_id: str | None = None
    registration_id: str | None = None
    full_name: str | None = None
    email: str | None = None
    used_at: datetime | None = None
    used_by_event_member_id: str | None = None


class TicketSearchItem(BaseModel):
    """Fila del respaldo de búsqueda manual."""

    ticket_id: str
    registration_id: str
    full_name: str
    email: str
    used_at: datetime | None


class TicketDetail(BaseModel):
    """Detalle de la entrada de una inscripción, para el panel de organizador."""

    id: str
    registration_id: str
    event_id: str
    issued_at: datetime
    used_at: datetime | None
    used_by_event_member_id: str | None
    revoked_at: datetime | None
    full_name: str
    email: str
    status: str


class MyTicketResponse(BaseModel):
    """`/mi-entrada` (fase 4, fase 4 de trabajo): qué mostrar y si hay QR que pedir."""

    status: str
    full_name: str
    has_qr: bool
