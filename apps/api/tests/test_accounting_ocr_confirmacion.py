"""Confirmación (con doble comprobación de importe y bloqueo de
concurrencia) y descarte del OCR de justificantes — ver
`test_accounting_ocr_drafts.py` para el porqué de la división en varios
ficheros. La fijación `sin_cola` la registra `tests.accounting_ocr_test_helpers`
como plugin en `conftest.py`.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import SessionApp, set_organization_context
from app.core.storage import get_storage
from app.modules.accounting import drafts_service
from app.modules.accounting.models import AccountingExpense, AccountingExpenseDraft
from tests.accounting_ocr_test_helpers import (
    BASE,
    _borrador_listo,
    _confirmacion,
    _contar_auditoria,
    _crear_evento,
    _leer_draft,
)
from tests.conftest import OrganizacionDePrueba, iniciar_sesion

# --- Confirmación -------------------------------------------------------------


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
