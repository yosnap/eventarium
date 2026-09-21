"""Helpers compartidos por los tests del OCR de justificantes de gasto.

Extraído de lo que era un único `test_accounting_ocr_drafts.py` (1137
líneas, por encima de la norma de 1000 del proyecto) al partirlo en varios
ficheros por sección — subida/extracción, barrido/reintento,
confirmación/descarte, seguridad/coste —, cada uno con la misma necesidad de
crear un evento, doblar la pasarela de IA, subir un justificante o forzar el
estado de un borrador.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.audit import AuditLog
from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.core.storage import get_storage
from app.modules.accounting import drafts_service
from app.modules.accounting.models import AccountingExpenseDraft
from app.modules.ai_gateway import client as ai_client
from app.modules.events.models import Event
from tests.conftest import OrganizacionDePrueba
from tests.test_accounting_ocr_unidad import CONTENIDO_PNG

BASE = "/api/v1/accounting"
AHORA = datetime.now(UTC).replace(microsecond=0)

RESPUESTA_DEL_MODELO = (
    '{"campos": {"provider_name": "Catering Paco", "expense_date": "2026-09-01", '
    '"base": "100.00", "vat": "21.00", "total": "121.00", "currency": "EUR"}, '
    '"confianza": {"provider_name": "alta", "expense_date": "alta", "base": "alta", '
    '"vat": "alta", "total": "alta", "currency": "media"}}'
)


async def _crear_evento(organizacion: OrganizacionDePrueba) -> uuid.UUID:
    async with SessionMaintenance() as session:
        evento = Event(
            organization_id=organizacion.id,
            slug=f"evento-ocr-{uuid.uuid4().hex[:8]}",
            title="Evento con justificantes",
            status="published",
            visibility="public",
            starts_at=AHORA,
            ends_at=AHORA + timedelta(days=1),
            location_mode="online",
        )
        session.add(evento)
        await session.commit()
        return evento.id


def _resultado(contenido: str = RESPUESTA_DEL_MODELO) -> ai_client.Resultado:
    return ai_client.Resultado(
        contenido=contenido,
        provider="proveedor_simulado",
        model="modelo-de-vision",
        input_tokens=100,
        output_tokens=20,
        cost_usd=Decimal("0.001000"),
        cost_auditable=True,
        latency_ms=12,
        usage_record_id=uuid.uuid4(),
    )


@pytest.fixture
def sin_cola(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """No hay worker en la suite: se comprueba que se encola, y la extracción
    se ejecuta después llamando al cuerpo de la tarea."""
    encolar = AsyncMock()
    monkeypatch.setattr("app.core.tasks.extraer_campos_task.kiq", encolar)
    return encolar


def _doblar_completar(
    monkeypatch: pytest.MonkeyPatch, resultado: Any = None, error: Exception | None = None
) -> AsyncMock:
    """Sustituye `ai_gateway.completar`. Ningún test necesita una clave."""
    doble = AsyncMock(side_effect=error) if error else AsyncMock(return_value=resultado)
    monkeypatch.setattr(ai_client, "completar", doble)
    return doble


async def _subir(
    cliente: AsyncClient,
    cabeceras: dict[str, str],
    event_id: uuid.UUID,
    *,
    contenido: bytes = CONTENIDO_PNG,
    nombre: str = "ticket.png",
    tipo: str = "image/png",
) -> httpx.Response:
    return await cliente.post(
        f"{BASE}/events/{event_id}/expense-drafts",
        headers=cabeceras,
        files={"fichero": (nombre, contenido, tipo)},
    )


async def _subir_y_extraer(
    cliente: AsyncClient,
    cabeceras: dict[str, str],
    organizacion: OrganizacionDePrueba,
    event_id: uuid.UUID,
    **kwargs: Any,
) -> uuid.UUID:
    respuesta = await _subir(cliente, cabeceras, event_id, **kwargs)
    assert respuesta.status_code == 200, respuesta.text
    draft_id = uuid.UUID(respuesta.json()["id"])
    await drafts_service.extraer_campos(draft_id, organizacion.id)
    return draft_id


async def _borrador_listo(
    cliente: AsyncClient,
    cabeceras: dict[str, str],
    organizacion: OrganizacionDePrueba,
    event_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> uuid.UUID:
    _doblar_completar(monkeypatch, _resultado())
    return await _subir_y_extraer(cliente, cabeceras, organizacion, event_id)


def _confirmacion(**extra: Any) -> dict[str, Any]:
    datos = {
        "provider_name": "Catering Paco",
        "expense_date": AHORA.isoformat(),
        "base_cents": 10_000,
        "vat_cents": 2_100,
        "total_cents": 12_100,
    }
    datos.update(extra)
    return datos


async def _leer_draft(
    organizacion: OrganizacionDePrueba, draft_id: uuid.UUID
) -> AccountingExpenseDraft:
    async with SessionApp() as session, session.begin():
        await set_organization_context(session, organizacion.id)
        borrador = await session.get(AccountingExpenseDraft, draft_id)
        assert borrador is not None
        await session.refresh(borrador)
        return borrador


async def _forzar_estado(
    organizacion: OrganizacionDePrueba,
    draft_id: uuid.UUID,
    *,
    status: str,
    error_code: str | None = None,
    attempts: int | None = None,
    antiguedad_minutos: int | None = None,
) -> None:
    """Deja el borrador en el estado que el test necesita examinar."""
    async with SessionMaintenance() as session:
        borrador = await session.get(AccountingExpenseDraft, draft_id)
        assert borrador is not None
        borrador.status = status
        borrador.error_code = error_code
        if attempts is not None:
            borrador.attempts = attempts
        if antiguedad_minutos is not None:
            borrador.updated_at = datetime.now(UTC) - timedelta(minutes=antiguedad_minutos)
        await session.commit()


async def _existe_en_el_almacen(clave: str) -> bool:
    from botocore.exceptions import ClientError

    try:
        await get_storage().get_object(clave)
    except ClientError:
        return False
    return True


async def _contar_auditoria(action: str, entity_id: str) -> int:
    async with SessionMaintenance() as session:
        total = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == action, AuditLog.entity_id == entity_id)
        )
    return total or 0
