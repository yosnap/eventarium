"""Barrido de extracciones atascadas y reintento manual del OCR de
justificantes — ver `test_accounting_ocr_drafts.py` para el porqué de la
división en varios ficheros. La fijación `sin_cola` la registra
`tests.accounting_ocr_test_helpers` como plugin en `conftest.py`.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.database import SessionMaintenance
from app.modules.accounting import drafts_service, repository
from app.modules.ai_gateway import errores as ai_errores
from tests.accounting_ocr_test_helpers import (
    BASE,
    _crear_evento,
    _forzar_estado,
    _leer_draft,
    _subir,
)
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

# --- Barrido y reintento ------------------------------------------------------


@pytest.mark.parametrize(
    ("codigo", "reencolado"),
    [
        (ai_errores.PROVEEDOR_ERROR, True),
        (ai_errores.LIMITE_SUPERADO, False),
        (ai_errores.PAYLOAD_INVALIDO, False),
        (ai_errores.CLAVE_RECHAZADA, False),
    ],
)
async def test_el_barrido_solo_reencola_el_error_transitorio(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    sin_cola: AsyncMock,
    codigo: str,
    reencolado: bool,
) -> None:
    """`limite_superado` **nunca** se reencola por tiempo: con el límite aún
    agotado, cada pasada consumiría una reserva y quemaría cuota."""
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await _subir(cliente, cabeceras, event_id)
    draft_id = uuid.UUID(respuesta.json()["id"])
    await _forzar_estado(
        organizacion,
        draft_id,
        status="extraction_failed",
        error_code=codigo,
        attempts=1,
        antiguedad_minutos=get_settings().accounting_ocr_stuck_minutes + 5,
    )
    sin_cola.reset_mock()

    await drafts_service.reencolar_extracciones_atascadas()

    borrador = await _leer_draft(organizacion, draft_id)
    if reencolado:
        assert borrador.status == "pending_extraction"
        assert borrador.error_code is None
        sin_cola.assert_awaited_once()
    else:
        assert borrador.status == "extraction_failed"
        assert borrador.error_code == codigo
        sin_cola.assert_not_awaited()


async def test_el_barrido_reencola_una_extraccion_atascada(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, sin_cola: AsyncMock
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await _subir(cliente, cabeceras, event_id)
    draft_id = uuid.UUID(respuesta.json()["id"])
    await _forzar_estado(
        organizacion,
        draft_id,
        status="pending_extraction",
        attempts=1,
        antiguedad_minutos=get_settings().accounting_ocr_stuck_minutes + 5,
    )
    sin_cola.reset_mock()

    reencoladas = await drafts_service.reencolar_extracciones_atascadas()

    assert reencoladas == 1
    sin_cola.assert_awaited_once()


async def test_agotados_no_cuenta_un_en_extraccion_todavia_en_curso(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, sin_cola: AsyncMock
) -> None:
    """`en_extraccion` con `updated_at` reciente es un intento legítimamente en
    curso (la llamada al modelo puede tardar hasta ~120 s) — no un atasco.
    Sin el filtro de antigüedad, este borrador se contaría como agotado
    mientras procesa con normalidad."""
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await _subir(cliente, cabeceras, event_id)
    draft_id = uuid.UUID(respuesta.json()["id"])
    await _forzar_estado(
        organizacion,
        draft_id,
        status="en_extraccion",
        attempts=get_settings().accounting_ocr_max_attempts,
    )

    async with SessionMaintenance() as session:
        agotados = await repository.contar_drafts_agotados(
            session,
            max_intentos=get_settings().accounting_ocr_max_attempts,
            minutos=get_settings().accounting_ocr_stuck_minutes,
        )

    assert agotados == 0


async def test_agotados_cuenta_un_en_extraccion_parado(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, sin_cola: AsyncMock
) -> None:
    """El mismo estado, pero con `updated_at` viejo: el worker murió a mitad
    y sí es un atasco real que necesita acción humana."""
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await _subir(cliente, cabeceras, event_id)
    draft_id = uuid.UUID(respuesta.json()["id"])
    await _forzar_estado(
        organizacion,
        draft_id,
        status="en_extraccion",
        attempts=get_settings().accounting_ocr_max_attempts,
        antiguedad_minutos=get_settings().accounting_ocr_stuck_minutes + 5,
    )

    async with SessionMaintenance() as session:
        agotados = await repository.contar_drafts_agotados(
            session,
            max_intentos=get_settings().accounting_ocr_max_attempts,
            minutos=get_settings().accounting_ocr_stuck_minutes,
        )

    assert agotados == 1


async def test_el_barrido_acota_el_lote_de_cada_pasada(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    """Tras una caída larga del proveedor puede haber cientos de borradores
    atascados: una pasada reencola un lote y el resto espera a la siguiente,
    en vez de soltar el atasco entero sobre la cola de golpe."""
    monkeypatch.setattr(drafts_service, "MAXIMO_REENCOLADAS_POR_PASADA", 2)
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    for _ in range(3):
        respuesta = await _subir(cliente, cabeceras, event_id)
        await _forzar_estado(
            organizacion,
            uuid.UUID(respuesta.json()["id"]),
            status="pending_extraction",
            attempts=1,
            antiguedad_minutos=get_settings().accounting_ocr_stuck_minutes + 5,
        )
    sin_cola.reset_mock()

    reencoladas = await drafts_service.reencolar_extracciones_atascadas()

    assert reencoladas == 2
    assert sin_cola.await_count == 2


async def test_reintento_manual_solo_sobre_limite_superado(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, sin_cola: AsyncMock
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await _subir(cliente, cabeceras, event_id)
    draft_id = uuid.UUID(respuesta.json()["id"])

    await _forzar_estado(
        organizacion,
        draft_id,
        status="extraction_failed",
        error_code=ai_errores.PAYLOAD_INVALIDO,
        attempts=1,
    )
    rechazo = await cliente.post(f"{BASE}/expense-drafts/{draft_id}/retry", headers=cabeceras)
    assert rechazo.status_code == 422, rechazo.text

    await _forzar_estado(
        organizacion,
        draft_id,
        status="extraction_failed",
        error_code=ai_errores.LIMITE_SUPERADO,
        attempts=1,
    )
    sin_cola.reset_mock()
    aceptado = await cliente.post(f"{BASE}/expense-drafts/{draft_id}/retry", headers=cabeceras)

    assert aceptado.status_code == 200, aceptado.text
    assert aceptado.json()["status"] == "pending_extraction"
    assert aceptado.json()["error_code"] is None
    sin_cola.assert_awaited_once()


async def test_reintento_manual_respeta_el_tope_de_intentos(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, sin_cola: AsyncMock
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await _subir(cliente, cabeceras, event_id)
    draft_id = uuid.UUID(respuesta.json()["id"])
    await _forzar_estado(
        organizacion,
        draft_id,
        status="extraction_failed",
        error_code=ai_errores.LIMITE_SUPERADO,
        attempts=get_settings().accounting_ocr_max_attempts,
    )

    agotado = await cliente.post(f"{BASE}/expense-drafts/{draft_id}/retry", headers=cabeceras)

    assert agotado.status_code == 409, agotado.text
