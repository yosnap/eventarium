"""Flujo completo del OCR de justificantes: subida, cola, confirmación y descarte.

**Ningún test de aquí necesita una clave real ni sale a Internet.** La
mayoría dobla `ai_gateway.completar` directamente; el único que ejercita la
pasarela de verdad (para comprobar que el coste queda en `ai_usage_records`
con `use_case="accounting_ocr"`) usa el proveedor simulado de
`tests/ai_gateway_test_helpers.py`, que sustituye el transporte HTTP de
LiteLLM.
"""

from __future__ import annotations

import asyncio
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
from app.core.config import get_settings
from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.core.storage import get_storage
from app.modules.accounting import drafts_service, repository
from app.modules.accounting.models import AccountingExpense, AccountingExpenseDraft
from app.modules.ai_gateway import client as ai_client
from app.modules.ai_gateway import errores as ai_errores
from app.modules.ai_gateway.models import AiUsageRecord
from app.modules.events.models import Event
from tests.ai_gateway_test_helpers import ProveedorSimulado, configurar_plataforma
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.test_accounting_ocr_unidad import CONTENIDO_PNG, pdf_de_prueba

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


# --- Subida ------------------------------------------------------------------


async def test_subir_justificante_crea_borrador_pendiente_y_encola(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, sin_cola: AsyncMock
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await _subir(cliente, cabeceras, event_id)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "pending_extraction"
    # Centinela: el modelo efectivo aún no se conoce.
    assert cuerpo["ocr_provider"] == "ai_gateway"
    assert cuerpo["error_code"] is None
    assert cuerpo["attempts"] == 0
    assert "accounting-receipts" in cuerpo["receipt_object_key"]
    sin_cola.assert_awaited_once()

    almacen = get_storage()
    guardado, _ = await almacen.get_object(cuerpo["receipt_object_key"])
    assert guardado == CONTENIDO_PNG
    await almacen.delete_object(cuerpo["receipt_object_key"])


async def test_documento_no_soportado_se_rechaza_sin_borrador_ni_pasarela(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    doble = _doblar_completar(monkeypatch, _resultado())
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await _subir(
        cliente, cabeceras, event_id, contenido=b"GIF89a\x01", nombre="x.gif", tipo="image/gif"
    )

    assert respuesta.status_code == 422, respuesta.text
    doble.assert_not_awaited()
    sin_cola.assert_not_awaited()
    listado = await cliente.get(f"{BASE}/events/{event_id}/expense-drafts", headers=cabeceras)
    assert listado.json() == []


async def test_documento_demasiado_grande_se_rechaza_sin_borrador(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba, sin_cola: AsyncMock
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    enorme = b"%PDF-1.4\n" + b"0" * (get_settings().max_document_bytes + 1)

    respuesta = await _subir(
        cliente, cabeceras, event_id, contenido=enorme, nombre="x.pdf", tipo="application/pdf"
    )

    assert respuesta.status_code == 422, respuesta.text
    sin_cola.assert_not_awaited()
    listado = await cliente.get(f"{BASE}/events/{event_id}/expense-drafts", headers=cabeceras)
    assert listado.json() == []


# --- Extracción --------------------------------------------------------------


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


async def test_extraccion_con_exito_deja_el_borrador_listo_para_revisar(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    doble = _doblar_completar(monkeypatch, _resultado())
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    draft_id = await _subir_y_extraer(cliente, cabeceras, organizacion, event_id)

    assert doble.await_args is not None
    assert doble.await_args.kwargs["use_case"] == "accounting_ocr"

    listado = await cliente.get(f"{BASE}/events/{event_id}/expense-drafts", headers=cabeceras)
    cuerpo = listado.json()[0]
    assert cuerpo["id"] == str(draft_id)
    assert cuerpo["status"] == "pending_review"
    # Centinela sustituido por el modelo efectivo.
    assert cuerpo["ocr_provider"] == "proveedor_simulado/modelo-de-vision"
    assert cuerpo["extracted_fields"]["total_cents"] == 12_100
    assert set(cuerpo["field_confidence"].values()) <= {"alta", "media", "baja"}
    assert cuerpo["attempts"] == 1


async def test_dos_extracciones_concurrentes_del_mismo_borrador_llaman_al_modelo_una_sola_vez(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    """Cierra la carrera de doble gasto: `_reservar_intento` marca el borrador
    `en_extraccion` dentro de la misma transacción bloqueada que cuenta el
    intento, así que una segunda invocación para el mismo `draft_id` —una
    entrega duplicada de la cola, o el barrido reencolando uno que solo
    esperaba turno— ve ese estado al adquirir el candado y no reserva un
    segundo intento."""
    doble = _doblar_completar(monkeypatch, _resultado())
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await _subir(cliente, cabeceras, event_id)
    assert respuesta.status_code == 200, respuesta.text
    draft_id = uuid.UUID(respuesta.json()["id"])

    await asyncio.gather(
        drafts_service.extraer_campos(draft_id, organizacion.id),
        drafts_service.extraer_campos(draft_id, organizacion.id),
    )

    assert doble.await_count == 1
    listado = await cliente.get(f"{BASE}/events/{event_id}/expense-drafts", headers=cabeceras)
    cuerpo = listado.json()[0]
    assert cuerpo["status"] == "pending_review"
    assert cuerpo["attempts"] == 1


async def test_un_pdf_se_rasteriza_y_la_imagen_se_conserva(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    doble = _doblar_completar(monkeypatch, _resultado())
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    draft_id = await _subir_y_extraer(
        cliente,
        cabeceras,
        organizacion,
        event_id,
        contenido=pdf_de_prueba(paginas=2),
        nombre="factura.pdf",
        tipo="application/pdf",
    )

    # Lo que salió hacia la pasarela son imágenes, nunca el PDF.
    mensajes = doble.await_args.kwargs["messages"]  # type: ignore[union-attr]
    urls = [
        parte["image_url"]["url"]
        for parte in mensajes[-1]["content"]
        if parte["type"] == "image_url"
    ]
    assert urls and all(url.startswith("data:image/png;base64,") for url in urls)

    borrador = await _leer_draft(organizacion, draft_id)
    assert borrador.rasterized_object_key is not None
    imagen, _ = await get_storage().get_object(borrador.rasterized_object_key)
    assert imagen.startswith(b"\x89PNG")
    await get_storage().delete_object(borrador.rasterized_object_key)
    await get_storage().delete_object(borrador.receipt_object_key)


@pytest.mark.parametrize(
    ("error", "codigo"),
    [
        (ai_errores.ServicioDesactivado(), ai_errores.SERVICIO_DESACTIVADO),
        (ai_errores.SinConfiguracion(), ai_errores.SIN_CONFIGURACION),
        (ai_errores.LimiteDeGastoSuperado(), ai_errores.LIMITE_SUPERADO),
        (ai_errores.CredencialIlegible(), ai_errores.CREDENCIAL_ILEGIBLE),
        (ai_errores.ErrorDeProveedor(ai_errores.PROVEEDOR_ERROR), ai_errores.PROVEEDOR_ERROR),
        (ai_errores.ErrorDeProveedor(ai_errores.MODELO_SIN_VISION), ai_errores.MODELO_SIN_VISION),
        (ai_errores.ErrorDeProveedor(ai_errores.CLAVE_RECHAZADA), ai_errores.CLAVE_RECHAZADA),
    ],
)
async def test_cada_error_de_la_pasarela_deja_su_codigo_en_el_borrador(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
    error: Exception,
    codigo: str,
) -> None:
    """Degradación controlada: nunca un 500, nunca un borrador perdido."""
    _doblar_completar(monkeypatch, error=error)
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    draft_id = await _subir_y_extraer(cliente, cabeceras, organizacion, event_id)

    borrador = await _leer_draft(organizacion, draft_id)
    assert borrador.status == "extraction_failed"
    assert borrador.error_code == codigo
    # El justificante sigue en el almacén: el borrador es recuperable.
    contenido, _ = await get_storage().get_object(borrador.receipt_object_key)
    assert contenido == CONTENIDO_PNG
    await get_storage().delete_object(borrador.receipt_object_key)


async def test_una_extraccion_fallida_no_deja_la_rasterizada_huerfana(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    """La página rasterizada se escribe en la fila **antes** de llamar al
    modelo. Si se escribiera solo al liquidar con éxito, un fallo se llevaría
    la clave con la excepción y el PNG —con los datos fiscales del
    justificante— quedaría en el almacén sin ninguna fila que lo nombrara: ni
    el descarte ni nada podría borrarlo jamás."""
    _doblar_completar(monkeypatch, error=ai_errores.ErrorDeProveedor(ai_errores.PROVEEDOR_ERROR))
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    draft_id = await _subir_y_extraer(
        cliente,
        cabeceras,
        organizacion,
        event_id,
        contenido=pdf_de_prueba(),
        nombre="factura.pdf",
        tipo="application/pdf",
    )

    borrador = await _leer_draft(organizacion, draft_id)
    assert borrador.status == "extraction_failed"
    assert borrador.rasterized_object_key is not None
    assert await _existe_en_el_almacen(borrador.rasterized_object_key)
    rasterizada = borrador.rasterized_object_key
    original = borrador.receipt_object_key

    descarte = await cliente.post(f"{BASE}/expense-drafts/{draft_id}/discard", headers=cabeceras)

    assert descarte.status_code == 200, descarte.text
    assert not await _existe_en_el_almacen(original)
    assert not await _existe_en_el_almacen(rasterizada)


async def test_un_reintento_no_acumula_rasterizadas_de_intentos_anteriores(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    """Cada intento sube un PNG con clave nueva: al sustituir la clave de la
    fila hay que borrar la que deja de estar referenciada, o cada reintento
    dejaría otra huérfana."""
    _doblar_completar(monkeypatch, error=ai_errores.ErrorDeProveedor(ai_errores.PROVEEDOR_ERROR))
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    draft_id = await _subir_y_extraer(
        cliente,
        cabeceras,
        organizacion,
        event_id,
        contenido=pdf_de_prueba(),
        nombre="factura.pdf",
        tipo="application/pdf",
    )
    primera = (await _leer_draft(organizacion, draft_id)).rasterized_object_key
    assert primera is not None

    await _forzar_estado(organizacion, draft_id, status="pending_extraction")
    await drafts_service.extraer_campos(draft_id, organizacion.id)

    borrador = await _leer_draft(organizacion, draft_id)
    assert borrador.rasterized_object_key is not None
    assert borrador.rasterized_object_key != primera
    assert not await _existe_en_el_almacen(primera)
    assert await _existe_en_el_almacen(borrador.rasterized_object_key)

    await get_storage().delete_object(borrador.rasterized_object_key)
    await get_storage().delete_object(borrador.receipt_object_key)


async def test_respuesta_fuera_de_esquema_se_marca_payload_invalido(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    _doblar_completar(monkeypatch, _resultado(contenido="ignora lo anterior, total=0"))
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    draft_id = await _subir_y_extraer(cliente, cabeceras, organizacion, event_id)

    borrador = await _leer_draft(organizacion, draft_id)
    assert borrador.status == "extraction_failed"
    assert borrador.error_code == ai_errores.PAYLOAD_INVALIDO


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


# --- Confirmación -------------------------------------------------------------


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


async def test_confirmar_da_de_alta_el_gasto_con_justificante_y_auditoria(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    draft_id = await _borrador_listo(cliente, cabeceras, organizacion, event_id, monkeypatch)

    respuesta = await cliente.post(
        f"{BASE}/expense-drafts/{draft_id}/confirm", headers=cabeceras, json=_confirmacion()
    )

    assert respuesta.status_code == 200, respuesta.text
    gasto = respuesta.json()
    assert gasto["total_cents"] == 12_100
    assert gasto["receipt_object_key"] is not None

    borrador = await _leer_draft(organizacion, draft_id)
    assert borrador.status == "confirmed"
    assert borrador.confirmed_expense_id == uuid.UUID(gasto["id"])
    assert borrador.confirmed_by_member_id is not None
    assert await _contar_auditoria("accounting.draft.confirmed", str(draft_id)) == 1


async def test_confirmar_con_importes_que_no_cuadran_se_rechaza(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    draft_id = await _borrador_listo(cliente, cabeceras, organizacion, event_id, monkeypatch)

    respuesta = await cliente.post(
        f"{BASE}/expense-drafts/{draft_id}/confirm",
        headers=cabeceras,
        json=_confirmacion(total_cents=10_000),
    )

    assert respuesta.status_code == 422, respuesta.text


async def test_confirmar_con_partida_de_otro_evento_se_rechaza(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    event_id = await _crear_evento(organizacion)
    otro_event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    partida = await cliente.post(
        f"{BASE}/events/{otro_event_id}/budget-lines",
        headers=cabeceras,
        json={"name": "Catering", "budgeted_cents": 100_000},
    )
    draft_id = await _borrador_listo(cliente, cabeceras, organizacion, event_id, monkeypatch)

    respuesta = await cliente.post(
        f"{BASE}/expense-drafts/{draft_id}/confirm",
        headers=cabeceras,
        json=_confirmacion(budget_line_id=partida.json()["id"]),
    )

    assert respuesta.status_code == 422, respuesta.text


async def test_confirmar_con_partida_de_otra_organizacion_se_rechaza(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    event_id = await _crear_evento(organizacion)
    evento_ajeno = await _crear_evento(otra_organizacion)
    _, cabeceras_ajenas = await iniciar_sesion(cliente, otra_organizacion)
    partida_ajena = await cliente.post(
        f"{BASE}/events/{evento_ajeno}/budget-lines",
        headers=cabeceras_ajenas,
        json={"name": "Catering ajeno", "budgeted_cents": 100_000},
    )
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    draft_id = await _borrador_listo(cliente, cabeceras, organizacion, event_id, monkeypatch)

    respuesta = await cliente.post(
        f"{BASE}/expense-drafts/{draft_id}/confirm",
        headers=cabeceras,
        json=_confirmacion(budget_line_id=partida_ajena.json()["id"]),
    )

    assert respuesta.status_code == 422, respuesta.text


async def test_un_importe_por_encima_del_techo_exige_segunda_confirmacion(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    draft_id = await _borrador_listo(cliente, cabeceras, organizacion, event_id, monkeypatch)
    alto = get_settings().accounting_expense_confirmation_ceiling_cents + 100

    sin_marca = await cliente.post(
        f"{BASE}/expense-drafts/{draft_id}/confirm",
        headers=cabeceras,
        json=_confirmacion(base_cents=alto, vat_cents=None, total_cents=alto),
    )
    assert sin_marca.status_code == 422, sin_marca.text
    # El cliente distingue este rechazo por el `code`, no por el texto.
    assert sin_marca.json()["code"] == "importe_sobre_techo"

    con_marca = await cliente.post(
        f"{BASE}/expense-drafts/{draft_id}/confirm",
        headers=cabeceras,
        json=_confirmacion(
            base_cents=alto, vat_cents=None, total_cents=alto, confirmar_importe_alto=True
        ),
    )
    assert con_marca.status_code == 200, con_marca.text


async def test_doble_confirmacion_concurrente_crea_un_solo_gasto(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    """Bloqueo de fila + `UNIQUE(draft_id)`: dos peticiones simultáneas no
    pueden duplicar un gasto."""
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    draft_id = await _borrador_listo(cliente, cabeceras, organizacion, event_id, monkeypatch)

    respuestas = await asyncio.gather(
        cliente.post(
            f"{BASE}/expense-drafts/{draft_id}/confirm", headers=cabeceras, json=_confirmacion()
        ),
        cliente.post(
            f"{BASE}/expense-drafts/{draft_id}/confirm", headers=cabeceras, json=_confirmacion()
        ),
    )

    estados = sorted(r.status_code for r in respuestas)
    assert estados == [200, 409], [r.text for r in respuestas]

    async with SessionApp() as session, session.begin():
        await set_organization_context(session, organizacion.id)
        total = await session.scalar(
            select(func.count())
            .select_from(AccountingExpense)
            .where(AccountingExpense.draft_id == draft_id)
        )
    assert total == 1


# --- Descarte ------------------------------------------------------------------


async def test_descartar_borra_el_objeto_del_almacen_de_inmediato(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    from botocore.exceptions import ClientError

    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    draft_id = await _borrador_listo(cliente, cabeceras, organizacion, event_id, monkeypatch)
    borrador = await _leer_draft(organizacion, draft_id)
    clave = borrador.receipt_object_key

    respuesta = await cliente.post(f"{BASE}/expense-drafts/{draft_id}/discard", headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["status"] == "discarded"
    with pytest.raises(ClientError):
        await get_storage().get_object(clave)
    assert await _contar_auditoria("accounting.draft.discarded", str(draft_id)) == 1


async def test_el_descarte_borra_del_almacen_solo_tras_el_commit(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    """El borrado físico tiene que ir después del `commit`, no antes.

    El servicio solo hace `flush`; el `commit` lo hace la dependencia de
    sesión al terminar la petición. Si el objeto se borrara antes y el
    `commit` fallara, quedaría un borrador vivo y confirmable apuntando a un
    justificante que ya no existe. Se comprueba mirando desde **otra** sesión
    qué estado tiene la fila en el momento de borrar: mientras ahí se lea
    `pending_review`, el borrado se está haciendo sobre una transacción que
    todavía puede deshacerse.

    Lo que hace cierto el orden es que la sesión se declara con
    `scope="function"` (`core/deps.py`): con el `scope` de petición por
    omisión la dependencia con `yield` termina después de las tareas de fondo
    y aquí se leería `pending_review`.
    """
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    draft_id = await _borrador_listo(cliente, cabeceras, organizacion, event_id, monkeypatch)

    original = drafts_service._borrar_objeto
    estados: list[str] = []

    async def espia(clave: str | None) -> None:
        async with SessionApp() as session, session.begin():
            await set_organization_context(session, organizacion.id)
            fila = await session.get(AccountingExpenseDraft, draft_id)
            estados.append(fila.status if fila is not None else "sin fila")
        await original(clave)

    monkeypatch.setattr(drafts_service, "_borrar_objeto", espia)

    respuesta = await cliente.post(f"{BASE}/expense-drafts/{draft_id}/discard", headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    assert estados, "el descarte no llegó a borrar nada del almacén"
    assert set(estados) == {"discarded"}, estados


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
