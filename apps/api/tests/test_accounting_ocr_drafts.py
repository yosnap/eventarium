"""Subida y extracción del OCR de justificantes: cola, worker, rasterización
y códigos de error de la pasarela.

**Ningún test de aquí necesita una clave real ni sale a Internet**: todos
doblan `ai_gateway.completar` directamente. El resto del flujo (barrido y
reintento, confirmación y descarte, seguridad y coste) vive en sus propios
ficheros — se dividió `test_accounting_ocr_drafts.py` (1137 líneas, por
encima de la norma de 1000 del proyecto) por sección. La fijación `sin_cola`
la registra `tests.accounting_ocr_test_helpers` como plugin en `conftest.py`.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.storage import get_storage
from app.modules.accounting import drafts_service, repository
from app.modules.ai_gateway import errores as ai_errores
from tests.accounting_ocr_test_helpers import (
    BASE,
    _crear_evento,
    _doblar_completar,
    _existe_en_el_almacen,
    _forzar_estado,
    _leer_draft,
    _resultado,
    _subir,
    _subir_y_extraer,
)
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.test_accounting_ocr_unidad import CONTENIDO_PNG, pdf_de_prueba

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


async def test_un_fallo_inesperado_antes_de_en_extraccion_no_deja_el_borrador_colgado(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
    sin_cola: AsyncMock,
) -> None:
    """Regresión: un error de programación/infraestructura ANTES de que
    `_reservar_intento` llegue a escribir `en_extraccion` (reproducido: un
    modelo sin importar en `core/tasks.py` reventaba con
    `NoReferencedTableError` en cuanto SQLAlchemy configuraba los
    mapeadores) dejaba el borrador en `pending_extraction` para siempre —
    la tarea se confirmaba en la cola igualmente, así que no había reintento
    ni aviso, solo "Leyendo este justificante…" indefinido en el panel."""
    original = repository.get_draft_for_update
    primera_llamada = True

    async def _reventar_solo_la_primera_vez(*args: Any, **kwargs: Any) -> Any:
        nonlocal primera_llamada
        if primera_llamada:
            primera_llamada = False
            raise RuntimeError("boom")
        return await original(*args, **kwargs)

    monkeypatch.setattr(repository, "get_draft_for_update", _reventar_solo_la_primera_vez)
    event_id = await _crear_evento(organizacion)
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    draft_id = await _subir_y_extraer(cliente, cabeceras, organizacion, event_id)

    borrador = await _leer_draft(organizacion, draft_id)
    assert borrador.status == "extraction_failed"
    assert borrador.error_code is not None
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
