"""Aislamiento entre organizaciones, acceso al justificante y coste
registrado en la pasarela de IA del OCR de justificantes — ver
`test_accounting_ocr_drafts.py` para el porqué de la división en varios
ficheros. La fijación `sin_cola` la registra `tests.accounting_ocr_test_helpers`
como plugin en `conftest.py`.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionApp, set_organization_context
from app.core.storage import get_storage
from app.modules.accounting import drafts_service
from app.modules.ai_gateway import errores as ai_errores
from app.modules.ai_gateway.models import AiUsageRecord
from tests.accounting_ocr_test_helpers import (
    BASE,
    RESPUESTA_DEL_MODELO,
    _borrador_listo,
    _confirmacion,
    _crear_evento,
    _forzar_estado,
    _leer_draft,
    _subir_y_extraer,
)
from tests.ai_gateway_test_helpers import ProveedorSimulado, configurar_plataforma
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.test_accounting_ocr_unidad import CONTENIDO_PNG

# --- Seguridad ------------------------------------------------------------------


async def test_una_organizacion_no_ve_ni_confirma_borradores_de_otra(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    draft_id = await _borrador_listo(cliente, cabeceras, organizacion, event_id, monkeypatch)

    _, ajenas = await iniciar_sesion(cliente, otra_organizacion)
    listado = await cliente.get(f"{BASE}/events/{event_id}/expense-drafts", headers=ajenas)
    assert listado.status_code == 404, listado.text

    confirmacion = await cliente.post(
        f"{BASE}/expense-drafts/{draft_id}/confirm", headers=ajenas, json=_confirmacion()
    )
    assert confirmacion.status_code == 404, confirmacion.text

    descarte = await cliente.post(f"{BASE}/expense-drafts/{draft_id}/discard", headers=ajenas)
    assert descarte.status_code == 404, descarte.text


async def test_el_justificante_se_sirve_como_adjunto_y_nunca_sin_sesion(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    draft_id = await _borrador_listo(cliente, cabeceras, organizacion, event_id, monkeypatch)
    borrador = await _leer_draft(organizacion, draft_id)

    anonima = await cliente.get(f"{BASE}/receipts/{borrador.receipt_object_key}")
    assert anonima.status_code == 401, anonima.text

    propia = await cliente.get(f"{BASE}/receipts/{borrador.receipt_object_key}", headers=cabeceras)
    assert propia.status_code == 200, propia.text
    assert propia.headers["content-disposition"].startswith("attachment")


async def test_peticion_anonima_directa_al_bucket_no_sirve_el_justificante(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    """Cierra la deuda W1 de la fase 1: la comprobación va **contra el
    almacén público**, no contra el endpoint de la API.

    La URL pública del bucket (`S3_PUBLIC_BASE_URL`) es la única entrada
    anónima al almacenamiento —en producción el puerto S3 no se publica— y la
    regla del Caddyfile deniega ahí el prefijo `accounting-receipts/`.
    """
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    draft_id = await _borrador_listo(cliente, cabeceras, organizacion, event_id, monkeypatch)
    borrador = await _leer_draft(organizacion, draft_id)
    url = get_storage().public_url(borrador.receipt_object_key)

    async with AsyncClient(timeout=10.0) as anonimo:
        try:
            respuesta = await anonimo.get(url)
        except httpx.HTTPError as error:  # pragma: no cover - entorno sin Caddy delante
            pytest.skip(f"El almacén público no está accesible en esta máquina: {error}")

    assert respuesta.status_code in (401, 403), (
        f"{url} devolvió {respuesta.status_code}: el prefijo de justificantes sigue "
        "siendo legible sin sesión desde el almacén público."
    )


# --- Coste registrado en la pasarela -------------------------------------------


async def test_el_coste_de_la_extraccion_queda_en_ai_usage_records(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
    sin_cola: AsyncMock,
) -> None:
    """Único test que ejercita la pasarela real (con el transporte HTTP de
    LiteLLM simulado, sin clave real ni red): comprueba el criterio de éxito
    «el coste de cada extracción queda en `ai_usage_records` con
    `use_case="accounting_ocr"`»."""
    proveedor_simulado.cuerpo = {
        "id": "chatcmpl-simulada",
        "object": "chat.completion",
        "created": 1,
        "model": "modelo-sin-precio-conocido",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": RESPUESTA_DEL_MODELO},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 200, "completion_tokens": 40, "total_tokens": 240},
    }
    await configurar_plataforma()
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    draft_id = await _subir_y_extraer(cliente, cabeceras, organizacion, event_id)

    borrador = await _leer_draft(organizacion, draft_id)
    assert borrador.status == "pending_review", borrador.error_code
    assert borrador.ocr_provider.startswith("nan_builders/")

    async with SessionApp() as session, session.begin():
        await set_organization_context(session, organizacion.id)
        filas = list(await session.scalars(select(AiUsageRecord)))
    assert [fila.use_case for fila in filas] == ["accounting_ocr"]
    assert filas[0].status == "liquidado"
    assert filas[0].cost_usd > 0


async def test_un_corte_por_limite_de_gasto_no_deja_facturas_irrecuperables(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    cifrado: str,
    proveedor_simulado: ProveedorSimulado,
    dns_publico: None,
    sin_cola: AsyncMock,
) -> None:
    """Criterio de éxito de la fase, con el límite real de la pasarela — no
    con el error inyectado a mano.

    Se pone un techo de gasto ridículo a propósito, se suben **varias**
    facturas y se comprueba la secuencia entera: las que no caben fallan con
    `limite_superado` y sus justificantes siguen en el almacén; el barrido
    **no** las reencola (con el límite agotado, cada pasada quemaría una
    reserva); y tras ampliar el límite, el reintento manual las completa.
    """
    proveedor_simulado.cuerpo = {
        "id": "chatcmpl-simulada",
        "object": "chat.completion",
        "created": 1,
        "model": "modelo-sin-precio-conocido",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": RESPUESTA_DEL_MODELO},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 200, "completion_tokens": 40, "total_tokens": 240},
    }
    # Techo por debajo de lo que aparta una sola llamada: la primera reserva
    # ya lo agota.
    await configurar_plataforma(techo_usd=Decimal("0.000001"))
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    borradores = [
        await _subir_y_extraer(cliente, cabeceras, organizacion, event_id) for _ in range(3)
    ]

    for draft_id in borradores:
        borrador = await _leer_draft(organizacion, draft_id)
        assert borrador.status == "extraction_failed"
        assert borrador.error_code == ai_errores.LIMITE_SUPERADO
        # El justificante sigue ahí: la factura no es irrecuperable.
        contenido, _ = await get_storage().get_object(borrador.receipt_object_key)
        assert contenido == CONTENIDO_PNG

    # El barrido los ve viejos y aun así no toca ninguno.
    for draft_id in borradores:
        await _forzar_estado(
            organizacion,
            draft_id,
            status="extraction_failed",
            error_code=ai_errores.LIMITE_SUPERADO,
            attempts=1,
            antiguedad_minutos=get_settings().accounting_ocr_stuck_minutes + 5,
        )
    sin_cola.reset_mock()
    assert await drafts_service.reencolar_extracciones_atascadas() == 0
    sin_cola.assert_not_awaited()

    # El organizador amplía el límite y reintenta a mano.
    await configurar_plataforma(techo_usd=Decimal("50"))
    for draft_id in borradores:
        reintento = await cliente.post(f"{BASE}/expense-drafts/{draft_id}/retry", headers=cabeceras)
        assert reintento.status_code == 200, reintento.text
        await drafts_service.extraer_campos(draft_id, organizacion.id)

    for draft_id in borradores:
        borrador = await _leer_draft(organizacion, draft_id)
        assert borrador.status == "pending_review", borrador.error_code
        assert borrador.extracted_fields["total_cents"] == 12_100
        await get_storage().delete_object(borrador.receipt_object_key)
