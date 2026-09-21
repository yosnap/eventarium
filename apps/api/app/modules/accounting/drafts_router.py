"""Endpoints de los borradores de gasto extraídos de un justificante.

Router propio con el mismo prefijo que `router.py` (se registran los dos en
`main.py`): el módulo tiene un techo de mil líneas por fichero y este dominio
ya trae seis endpoints y su propio mapeo de respuesta.

La descarga del justificante —y de la imagen rasterizada, que vive en el mismo
prefijo y con el mismo formato de clave— sigue siendo la de `router.py`:
`GET /accounting/receipts/{object_key}`, autenticada, con
`Content-Disposition: attachment` y comprobando que el `organization_id`
embebido en la clave es el de la sesión.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile

from app.core.deps import CurrentUserDep, DbDep, require_permission
from app.core.permissions import Permission
from app.modules.accounting import drafts_service, ocr_client, repository
from app.modules.accounting.models import AccountingExpenseDraft
from app.modules.accounting.router import EventoDep, expense_response, uuid_o_422
from app.modules.accounting.schemas import (
    ExpenseDraftConfirm,
    ExpenseDraftFieldsOut,
    ExpenseDraftOut,
    ExpenseOut,
)
from app.shared.errors import ValidationDomainError

router = APIRouter(prefix="/accounting", tags=["contabilidad"])

#: Espejo del `CHECK` de `accounting_expense_drafts.status`.
_ESTADOS_VALIDOS = (
    "pending_extraction",
    "en_extraccion",
    "pending_review",
    "extraction_failed",
    "confirmed",
    "discarded",
)


def _draft_response(borrador: AccountingExpenseDraft) -> ExpenseDraftOut:
    """Mapea el borrador a su contrato público.

    La confianza se vuelve a normalizar aquí aunque el adaptador ya la
    normalizó al escribirla: `field_confidence` es `JSONB` y una fila escrita
    por una versión anterior (o a mano) no puede hacer que la respuesta falle
    al serializarse.
    """
    campos = borrador.extracted_fields or {}
    confianza = borrador.field_confidence or {}
    return ExpenseDraftOut(
        id=str(borrador.id),
        event_id=str(borrador.event_id),
        status=borrador.status,  # type: ignore[arg-type]
        error_code=borrador.error_code,
        ocr_provider=borrador.ocr_provider,
        receipt_object_key=borrador.receipt_object_key,
        rasterized_object_key=borrador.rasterized_object_key,
        extracted_fields=ExpenseDraftFieldsOut(
            **{campo: campos.get(campo) for campo in ExpenseDraftFieldsOut.model_fields}
        ),
        field_confidence={
            campo: ocr_client.normalizar_confianza(confianza.get(campo))  # type: ignore[misc]
            for campo in ocr_client.CAMPOS_DEL_BORRADOR
        },
        attempts=borrador.attempts,
        confirmed_expense_id=(
            str(borrador.confirmed_expense_id) if borrador.confirmed_expense_id else None
        ),
        created_at=borrador.created_at,
    )


@router.post(
    "/events/{event_id}/expense-drafts",
    summary="Subir un justificante y encolar su extracción",
    description=(
        "Acepta imagen o PDF, validado por sus bytes reales y por "
        "`max_document_bytes`. La extracción **nunca** es síncrona: el "
        "borrador nace en `pending_extraction` y un worker lo completa. Un "
        "documento no soportado o demasiado grande se rechaza con 422 sin "
        "crear borrador ni consumir la pasarela de IA."
    ),
    response_model=ExpenseDraftOut,
    dependencies=[require_permission(Permission.ACCOUNTING_WRITE)],
)
async def upload_expense_draft(
    evento: EventoDep,
    session: DbDep,
    usuario: CurrentUserDep,
    background_tasks: BackgroundTasks,
    fichero: Annotated[UploadFile, File()],
) -> ExpenseDraftOut:
    contenido = await fichero.read()
    borrador = await drafts_service.crear_draft_desde_documento(
        session,
        background_tasks,
        actor_user_id=usuario.id,
        organization_id=evento.organization_id,
        event_id=evento.id,
        contenido=contenido,
    )
    return _draft_response(borrador)


@router.get(
    "/events/{event_id}/expense-drafts",
    summary="Listar los borradores de gasto de un evento",
    description=(
        "`estado` filtra por uno de los estados del borrador. Sin filtro "
        "devuelve todos, que es lo que necesita la pantalla de revisión para "
        "distinguir «presupuesto de IA agotado» de «extracción fallida»."
    ),
    response_model=list[ExpenseDraftOut],
    dependencies=[require_permission(Permission.ACCOUNTING_READ)],
)
async def list_expense_drafts(
    evento: EventoDep, session: DbDep, estado: str | None = None
) -> list[ExpenseDraftOut]:
    estados: tuple[str, ...] | None = None
    if estado is not None:
        if estado not in _ESTADOS_VALIDOS:
            raise ValidationDomainError("Ese estado de borrador no existe.")
        estados = (estado,)
    borradores = await repository.list_drafts(
        session, evento.organization_id, evento.id, estados=estados
    )
    return [_draft_response(borrador) for borrador in borradores]


def _draft_id(draft_id: str) -> uuid.UUID:
    return uuid_o_422(draft_id, "draft_id")


DraftIdDep = Annotated[uuid.UUID, Depends(_draft_id)]


@router.post(
    "/expense-drafts/{draft_id}/confirm",
    summary="Confirmar un borrador y dar de alta el gasto",
    description=(
        "Único camino de alta de un gasto por OCR, y siempre con una persona "
        "detrás: el modelo nunca autoconfirma. Bloquea la fila del borrador y "
        "revalida importes y pertenencia de la partida. 409 si el borrador ya "
        "no está pendiente de revisión o ya se confirmó."
    ),
    response_model=ExpenseOut,
    dependencies=[require_permission(Permission.ACCOUNTING_WRITE)],
)
async def confirm_expense_draft(
    datos: ExpenseDraftConfirm,
    draft_id: DraftIdDep,
    session: DbDep,
    usuario: CurrentUserDep,
    background_tasks: BackgroundTasks,
) -> ExpenseOut:
    valores = datos.model_dump()
    budget_line_id = valores.pop("budget_line_id")
    gasto = await drafts_service.confirmar_draft(
        session,
        background_tasks,
        actor_user_id=usuario.id,
        organization_id=usuario.organization_id,
        draft_id=draft_id,
        datos={
            **valores,
            "budget_line_id": (
                uuid_o_422(budget_line_id, "budget_line_id") if budget_line_id is not None else None
            ),
        },
    )
    return expense_response(gasto)


@router.post(
    "/expense-drafts/{draft_id}/discard",
    summary="Descartar un borrador",
    description=(
        "Borra el justificante (y su página rasterizada) del almacén de "
        "inmediato, sin papelera: es un documento con datos fiscales que ya "
        "nadie va a usar."
    ),
    response_model=ExpenseDraftOut,
    dependencies=[require_permission(Permission.ACCOUNTING_WRITE)],
)
async def discard_expense_draft(
    draft_id: DraftIdDep,
    session: DbDep,
    usuario: CurrentUserDep,
    background_tasks: BackgroundTasks,
) -> ExpenseDraftOut:
    borrador = await drafts_service.descartar_draft(
        session,
        background_tasks,
        actor_user_id=usuario.id,
        organization_id=usuario.organization_id,
        draft_id=draft_id,
    )
    return _draft_response(borrador)


@router.post(
    "/expense-drafts/{draft_id}/retry",
    summary="Reintentar la extracción de un borrador",
    description=(
        "Solo para `error_code=limite_superado`, tras ampliar el límite de "
        "gasto de IA: 422 con cualquier otro código, porque repetir la "
        "llamada daría el mismo resultado. El barrido automático nunca "
        "reencola este estado —consumiría una reserva por pasada con el "
        "límite todavía agotado—, así que este endpoint es el único camino."
    ),
    response_model=ExpenseDraftOut,
    dependencies=[require_permission(Permission.ACCOUNTING_WRITE)],
)
async def retry_expense_draft(
    draft_id: DraftIdDep,
    session: DbDep,
    usuario: CurrentUserDep,
    background_tasks: BackgroundTasks,
) -> ExpenseDraftOut:
    borrador = await drafts_service.reintentar_draft(
        session,
        background_tasks,
        actor_user_id=usuario.id,
        organization_id=usuario.organization_id,
        draft_id=draft_id,
    )
    return _draft_response(borrador)
