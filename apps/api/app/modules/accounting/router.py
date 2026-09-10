"""Endpoints del módulo de contabilidad.

Fase 1 de trabajo: la descarga autenticada de justificantes. Fase 2: vista
compuesta de ingresos y CRUD de `accounting_incomes`/`sponsor_payment_details`.
Las fases 3-5 añaden presupuesto, gastos, OCR y panel a este mismo router.

`GET /accounting/receipts/{object_key}` es la única puerta de entrada a un
justificante (plan.md Decisión #7): nunca se sirve por `public_url` ni por
`presigned_put_url`. El `object_key` sigue el patrón
`orgs/{organization_id}/accounting-receipts/{uuid}.{ext}`
(`build_object_key`); aquí se comprueba que el `organization_id` embebido en
la propia clave coincide con el de la sesión **antes** de tocar el
almacenamiento — sin esto, conocer la clave de un justificante ajeno (p. ej.
filtrada en un log) bastaría para descargarlo con cualquier sesión que tenga
`accounting:read`.

Los endpoints de ingresos cuelgan de `/accounting/events/{event_id}/...`: se
resuelve el evento por `(id, organization_id)` antes de tocar nada (mismo
patrón que `sponsors/router.py:_obtener_evento_o_404`) — RLS ya lo garantiza
a nivel de fila, pero sin esta comprobación previa un evento ajeno inexistente
respondería con un error de base de datos sin traducir en vez de un 404 claro.
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated

from botocore.exceptions import ClientError
from fastapi import APIRouter, BackgroundTasks, Depends, Response
from sqlalchemy import select

from app.core.deps import CurrentUserDep, DbDep, require_permission
from app.core.permissions import Permission
from app.core.storage import get_storage
from app.modules.accounting import repository, service
from app.modules.accounting.models import (
    AccountingBudgetLine,
    AccountingExpense,
    AccountingIncome,
    SponsorPaymentDetail,
)
from app.modules.accounting.schemas import (
    AccountingIncomeCreate,
    AccountingIncomeOut,
    AccountingIncomeUpdate,
    BudgetApprovalOut,
    BudgetLineCreate,
    BudgetLineOut,
    BudgetLineUpdate,
    BudgetReopenIn,
    BudgetSummaryOut,
    ContingencyLineOut,
    ExpenseCreate,
    ExpenseOut,
    ExpenseUpdate,
    IncomeLineOut,
    IncomesViewOut,
    InKindValuationIn,
    InKindValuationOut,
    SponsorPaymentDetailOut,
    SponsorPaymentDetailUpsert,
)
from app.modules.events import repository as events_repository
from app.modules.events.models import Event
from app.modules.sponsors.models import Sponsor
from app.shared.errors import NotFoundError, PermissionDeniedError, ValidationDomainError

router = APIRouter(prefix="/accounting", tags=["contabilidad"])

# Forma exacta de `build_object_key(organization_id, "accounting-receipts", ext)`.
# Un `split("/")` que solo mira los tres primeros segmentos acepta claves con
# `..` intercalados (p. ej. `orgs/{mi_org}/accounting-receipts/../../orgs/
# {otra_org}/accounting-receipts/x.pdf`), que el proveedor S3 real resuelve
# contra el filer y sirve el objeto ajeno — `fullmatch` contra la forma
# completa es lo único que lo cierra.
_CLAVE_JUSTIFICANTE = re.compile(
    r"^orgs/([0-9a-f-]{36})/accounting-receipts/[0-9a-f]{32}\.[a-z0-9]{1,5}$"
)


def _verificar_organizacion_del_object_key(object_key: str, organization_id_esperado: str) -> None:
    coincidencia = _CLAVE_JUSTIFICANTE.fullmatch(object_key)
    if coincidencia is None:
        raise NotFoundError("Ese justificante no existe.")
    if coincidencia.group(1) != organization_id_esperado:
        # No se distingue de un 404 en el mensaje: confirmar que la clave
        # pertenece a otra organización sería información filtrada de más.
        raise PermissionDeniedError("Ese justificante no existe.")


@router.get(
    "/receipts/{object_key:path}",
    summary="Descargar un justificante de gasto",
    description=(
        "Exige `accounting:read`. Sirve el objeto con `Content-Disposition: "
        "attachment`, nunca `inline` — un PDF admite JavaScript y navegación "
        "activa, y no debe ejecutarse en el origen de la plataforma."
    ),
    dependencies=[require_permission(Permission.ACCOUNTING_READ)],
)
async def download_receipt(usuario: CurrentUserDep, object_key: str) -> Response:
    _verificar_organizacion_del_object_key(object_key, str(usuario.organization_id))

    almacen = get_storage()
    try:
        contenido, content_type = await almacen.get_object(object_key)
    except ClientError as exc:
        raise NotFoundError("Ese justificante no existe.") from exc

    nombre_fichero = object_key.rsplit("/", 1)[-1]
    return Response(
        content=contenido,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre_fichero}"'},
    )


async def _obtener_evento_o_404(session: DbDep, usuario: CurrentUserDep, event_id: str) -> Event:
    evento = await events_repository.get_event(
        session, usuario.organization_id, _uuid_o_422(event_id, "event_id")
    )
    if evento is None:
        raise NotFoundError("El evento no existe.")
    return evento


EventoDep = Annotated[Event, Depends(_obtener_evento_o_404)]


def _income_response(ingreso: AccountingIncome) -> AccountingIncomeOut:
    return AccountingIncomeOut(
        id=str(ingreso.id),
        event_id=str(ingreso.event_id),
        origin=ingreso.origin,  # type: ignore[arg-type]
        concept=ingreso.concept,
        amount_cents=ingreso.amount_cents,
        status=ingreso.status,  # type: ignore[arg-type]
        expected_at=ingreso.expected_at,
        collected_at=ingreso.collected_at,
    )


def _payment_detail_response(detalle: SponsorPaymentDetail) -> SponsorPaymentDetailOut:
    return SponsorPaymentDetailOut(
        id=str(detalle.id),
        sponsor_id=str(detalle.sponsor_id),
        collected_at=detalle.collected_at,
        contact_name=detalle.contact_name,
    )


@router.get(
    "/events/{event_id}/incomes",
    summary="Ingresos y comprometido de un evento",
    description=(
        "Vista compuesta: patrocinios cobrados + entradas netas de reembolso + "
        "subvenciones cobradas van a «ingresos»; lo pendiente de cobrar va a "
        "«comprometido». Un ingreso en moneda distinta de la del evento se "
        "excluye del total con aviso, nunca se suma."
    ),
    response_model=IncomesViewOut,
    dependencies=[require_permission(Permission.ACCOUNTING_READ)],
)
async def list_incomes(evento: EventoDep, session: DbDep) -> IncomesViewOut:
    vista = await repository.listar_ingresos(
        session,
        organization_id=evento.organization_id,
        event_id=evento.id,
        moneda_evento=evento.accounting_currency,
    )
    return IncomesViewOut(
        ingresos=[
            IncomeLineOut(
                origen=linea.origen,  # type: ignore[arg-type]
                concepto=linea.concepto,
                importe_cents=linea.importe_cents,
                fecha=linea.fecha,
                peso_sobre_el_total=linea.peso_sobre_el_total,
                referencia_id=linea.referencia_id,
            )
            for linea in vista.ingresos
        ],
        comprometido=[
            IncomeLineOut(
                origen=linea.origen,  # type: ignore[arg-type]
                concepto=linea.concepto,
                importe_cents=linea.importe_cents,
                fecha=linea.fecha,
                peso_sobre_el_total=linea.peso_sobre_el_total,
                referencia_id=linea.referencia_id,
            )
            for linea in vista.comprometido
        ],
        total_ingresos_cents=vista.total_ingresos_cents,
        moneda=vista.moneda,
        ingresos_excluidos_por_moneda=vista.ingresos_excluidos_por_moneda,
    )


@router.post(
    "/events/{event_id}/incomes",
    summary="Dar de alta un ingreso manual (subvención)",
    description="El único `origin` admitido es `subvencion`; cualquier otro valor devuelve 422.",
    response_model=AccountingIncomeOut,
    dependencies=[require_permission(Permission.ACCOUNTING_WRITE)],
)
async def create_income(
    datos: AccountingIncomeCreate,
    evento: EventoDep,
    session: DbDep,
    usuario: CurrentUserDep,
    background_tasks: BackgroundTasks,
) -> AccountingIncomeOut:
    ingreso = await service.crear_ingreso_manual(
        session,
        background_tasks,
        actor_user_id=usuario.id,
        organization_id=evento.organization_id,
        event_id=evento.id,
        datos=datos.model_dump(),
    )
    return _income_response(ingreso)


@router.patch(
    "/incomes/{income_id}",
    summary="Editar un ingreso manual",
    response_model=AccountingIncomeOut,
    dependencies=[require_permission(Permission.ACCOUNTING_WRITE)],
)
async def update_income(
    datos: AccountingIncomeUpdate,
    usuario: CurrentUserDep,
    session: DbDep,
    income_id: str,
    background_tasks: BackgroundTasks,
) -> AccountingIncomeOut:
    ingreso = await service.editar_ingreso_manual(
        session,
        background_tasks,
        actor_user_id=usuario.id,
        organization_id=usuario.organization_id,
        income_id=_uuid_o_422(income_id, "income_id"),
        datos=datos.model_dump(exclude_unset=True),
    )
    return _income_response(ingreso)


@router.put(
    "/sponsors/{sponsor_id}/payment-details",
    summary="Fijar los datos de cobro de un patrocinador",
    description=(
        "Upsert: 1:1 por patrocinador (`UNIQUE(sponsor_id)`). Marcar `collected_at` "
        "mueve al patrocinador de «comprometido» a «ingresos» en la siguiente "
        "consulta de `GET .../incomes`, sin crear ninguna fila nueva."
    ),
    response_model=SponsorPaymentDetailOut,
    dependencies=[require_permission(Permission.ACCOUNTING_WRITE)],
)
async def upsert_sponsor_payment_details(
    datos: SponsorPaymentDetailUpsert,
    usuario: CurrentUserDep,
    session: DbDep,
    sponsor_id: str,
    background_tasks: BackgroundTasks,
) -> SponsorPaymentDetailOut:
    sponsor_uuid = _uuid_o_422(sponsor_id, "sponsor_id")
    # El patrocinador tiene que existir en esta organización antes de fijarle
    # datos de cobro: sin esta comprobación, un `sponsor_id` inventado
    # produciría un `IntegrityError` de la FK compuesta sin traducir en vez
    # de un 404 claro. Se resuelve por `(id, organization_id)` directamente
    # (no por `sponsors.repository.get_sponsor`, que exige un `event_id` — este
    # endpoint no cuelga de un evento en la URL, un patrocinador vale para
    # toda su edición).
    patrocinador = await session.scalar(
        select(Sponsor).where(
            Sponsor.id == sponsor_uuid, Sponsor.organization_id == usuario.organization_id
        )
    )
    if patrocinador is None:
        raise NotFoundError("Ese patrocinador no existe.")

    detalle = await service.fijar_datos_de_cobro_de_patrocinador(
        session,
        background_tasks,
        actor_user_id=usuario.id,
        organization_id=usuario.organization_id,
        sponsor_id=sponsor_uuid,
        datos=datos.model_dump(exclude_unset=True),
    )
    return _payment_detail_response(detalle)


# --- Presupuesto: partidas, aprobación y contingencia (fase 3 de trabajo) ----


def _budget_line_response(linea: AccountingBudgetLine) -> BudgetLineOut:
    return BudgetLineOut(
        id=str(linea.id),
        event_id=str(linea.event_id),
        name=linea.name,
        budgeted_cents=linea.budgeted_cents,
        sort_order=linea.sort_order,
    )


def _expense_response(gasto: AccountingExpense) -> ExpenseOut:
    return ExpenseOut(
        id=str(gasto.id),
        event_id=str(gasto.event_id),
        budget_line_id=str(gasto.budget_line_id) if gasto.budget_line_id else None,
        sponsor_id=str(gasto.sponsor_id) if gasto.sponsor_id else None,
        provider_name=gasto.provider_name,
        expense_date=gasto.expense_date,
        base_cents=gasto.base_cents,
        vat_cents=gasto.vat_cents,
        total_cents=gasto.total_cents,
        receipt_object_key=gasto.receipt_object_key,
        receipt_status=gasto.receipt_status,
    )


def _uuid_o_422(valor: str, etiqueta: str) -> uuid.UUID:
    try:
        return uuid.UUID(valor)
    except ValueError as exc:
        raise ValidationDomainError(f"«{etiqueta}» no es un identificador válido.") from exc


@router.get(
    "/events/{event_id}/budget-lines",
    summary="Listar las partidas de presupuesto de un evento",
    response_model=list[BudgetLineOut],
    dependencies=[require_permission(Permission.ACCOUNTING_READ)],
)
async def list_budget_lines(evento: EventoDep, session: DbDep) -> list[BudgetLineOut]:
    lineas = await repository.list_budget_lines(session, evento.organization_id, evento.id)
    return [_budget_line_response(linea) for linea in lineas]


@router.post(
    "/events/{event_id}/budget-lines",
    summary="Dar de alta una partida de presupuesto",
    description="409 si el presupuesto del evento ya está aprobado.",
    response_model=BudgetLineOut,
    dependencies=[require_permission(Permission.ACCOUNTING_WRITE)],
)
async def create_budget_line(
    datos: BudgetLineCreate,
    evento: EventoDep,
    session: DbDep,
    usuario: CurrentUserDep,
    background_tasks: BackgroundTasks,
) -> BudgetLineOut:
    linea = await service.crear_partida_presupuesto(
        session,
        background_tasks,
        actor_user_id=usuario.id,
        organization_id=evento.organization_id,
        event_id=evento.id,
        datos=datos.model_dump(),
    )
    return _budget_line_response(linea)


@router.patch(
    "/budget-lines/{budget_line_id}",
    summary="Editar una partida de presupuesto",
    description="409 si el presupuesto del evento ya está aprobado.",
    response_model=BudgetLineOut,
    dependencies=[require_permission(Permission.ACCOUNTING_WRITE)],
)
async def update_budget_line(
    datos: BudgetLineUpdate,
    usuario: CurrentUserDep,
    session: DbDep,
    budget_line_id: str,
    background_tasks: BackgroundTasks,
) -> BudgetLineOut:
    linea = await service.editar_partida_presupuesto(
        session,
        background_tasks,
        actor_user_id=usuario.id,
        organization_id=usuario.organization_id,
        budget_line_id=_uuid_o_422(budget_line_id, "budget_line_id"),
        datos=datos.model_dump(exclude_unset=True),
    )
    return _budget_line_response(linea)


@router.delete(
    "/budget-lines/{budget_line_id}",
    summary="Borrar una partida de presupuesto",
    description=(
        "409 si el presupuesto del evento ya está aprobado o si la partida tiene gastos enlazados."
    ),
    status_code=204,
    dependencies=[require_permission(Permission.ACCOUNTING_WRITE)],
)
async def delete_budget_line(
    usuario: CurrentUserDep,
    session: DbDep,
    budget_line_id: str,
    background_tasks: BackgroundTasks,
) -> None:
    await service.borrar_partida_presupuesto(
        session,
        background_tasks,
        actor_user_id=usuario.id,
        organization_id=usuario.organization_id,
        budget_line_id=_uuid_o_422(budget_line_id, "budget_line_id"),
    )


@router.post(
    "/events/{event_id}/budget/approve",
    summary="Aprobar el presupuesto de un evento",
    description=(
        "Dota `contingency_fund_cents` sobre la suma de partidas y el "
        "`contingency_fund_percent` del evento. 409 si ya estaba aprobado."
    ),
    response_model=BudgetApprovalOut,
    dependencies=[require_permission(Permission.ACCOUNTING_WRITE)],
)
async def approve_budget(
    evento: EventoDep,
    session: DbDep,
    usuario: CurrentUserDep,
    background_tasks: BackgroundTasks,
) -> BudgetApprovalOut:
    actualizado = await service.aprobar_presupuesto(
        session,
        background_tasks,
        actor_user_id=usuario.id,
        organization_id=evento.organization_id,
        event_id=evento.id,
    )
    total_budgeted_cents = await repository.sum_budgeted_cents(
        session, evento.organization_id, evento.id
    )
    return BudgetApprovalOut(
        event_id=str(actualizado.id),
        budget_approved_at=actualizado.budget_approved_at,
        contingency_fund_cents=actualizado.contingency_fund_cents,
        total_budgeted_cents=total_budgeted_cents,
    )


@router.post(
    "/events/{event_id}/budget/reopen",
    summary="Reabrir el presupuesto de un evento",
    description=(
        "Exige `motivo`. Vuelve a hacer editables las partidas; no borra `contingency_fund_cents`."
    ),
    response_model=BudgetApprovalOut,
    dependencies=[require_permission(Permission.ACCOUNTING_WRITE)],
)
async def reopen_budget(
    datos: BudgetReopenIn,
    evento: EventoDep,
    session: DbDep,
    usuario: CurrentUserDep,
    background_tasks: BackgroundTasks,
) -> BudgetApprovalOut:
    actualizado = await service.reabrir_presupuesto(
        session,
        background_tasks,
        actor_user_id=usuario.id,
        organization_id=evento.organization_id,
        event_id=evento.id,
        motivo=datos.motivo,
    )
    total_budgeted_cents = await repository.sum_budgeted_cents(
        session, evento.organization_id, evento.id
    )
    return BudgetApprovalOut(
        event_id=str(actualizado.id),
        budget_approved_at=actualizado.budget_approved_at,
        contingency_fund_cents=actualizado.contingency_fund_cents,
        total_budgeted_cents=total_budgeted_cents,
    )


@router.get(
    "/events/{event_id}/budget/summary",
    summary="Resumen de presupuesto y contingencia de un evento",
    description=(
        "Presupuesto total, contingencia consumida/disponible y «gasto sin "
        "partida» — insumo del panel de la fase 5, ya expuesto en esta fase."
    ),
    response_model=BudgetSummaryOut,
    dependencies=[require_permission(Permission.ACCOUNTING_READ)],
)
async def get_budget_summary(evento: EventoDep, session: DbDep) -> BudgetSummaryOut:
    resumen = await service.resumen_presupuesto(
        session, organization_id=evento.organization_id, event_id=evento.id
    )
    return BudgetSummaryOut(
        event_id=str(resumen.event_id),
        budget_approved_at=resumen.budget_approved_at,
        total_budgeted_cents=resumen.total_budgeted_cents,
        contingency_fund_percent=resumen.contingency_fund_percent,
        contingency_fund_cents=resumen.contingency_fund_cents,
        consumido_contingencia_cents=resumen.consumido_contingencia_cents,
        disponible_contingencia_cents=resumen.disponible_contingencia_cents,
        gasto_sin_partida_cents=resumen.gasto_sin_partida_cents,
        ejecutado_en_especie_cents=resumen.ejecutado_en_especie_cents,
        por_partida=[
            ContingencyLineOut(
                budget_line_id=str(linea.budget_line_id) if linea.budget_line_id else None,
                ejecutado_cents=linea.ejecutado_cents,
                budgeted_cents=linea.budgeted_cents,
                exceso_cents=linea.exceso_cents,
            )
            for linea in resumen.por_partida
        ],
    )


# --- Gastos manuales (fase 3 de trabajo) -------------------------------------


@router.get(
    "/events/{event_id}/expenses",
    summary="Listar los gastos de un evento",
    response_model=list[ExpenseOut],
    dependencies=[require_permission(Permission.ACCOUNTING_READ)],
)
async def list_expenses(evento: EventoDep, session: DbDep) -> list[ExpenseOut]:
    gastos = await repository.list_expenses(session, evento.organization_id, evento.id)
    return [_expense_response(gasto) for gasto in gastos]


@router.post(
    "/events/{event_id}/expenses",
    summary="Dar de alta un gasto manual",
    description="Sin `sponsor_id`: el gasto en especie se da de alta desde `in-kind-valuation`.",
    response_model=ExpenseOut,
    dependencies=[require_permission(Permission.ACCOUNTING_WRITE)],
)
async def create_expense(
    datos: ExpenseCreate,
    evento: EventoDep,
    session: DbDep,
    usuario: CurrentUserDep,
    background_tasks: BackgroundTasks,
) -> ExpenseOut:
    valores = datos.model_dump()
    budget_line_id = valores.pop("budget_line_id")
    gasto = await service.crear_gasto(
        session,
        background_tasks,
        actor_user_id=usuario.id,
        organization_id=evento.organization_id,
        event_id=evento.id,
        datos={
            **valores,
            "budget_line_id": (
                _uuid_o_422(budget_line_id, "budget_line_id")
                if budget_line_id is not None
                else None
            ),
        },
    )
    return _expense_response(gasto)


@router.patch(
    "/expenses/{expense_id}",
    summary="Editar un gasto manual",
    description="409 si el gasto es en especie (se edita fijando la valoración del patrocinador).",
    response_model=ExpenseOut,
    dependencies=[require_permission(Permission.ACCOUNTING_WRITE)],
)
async def update_expense(
    datos: ExpenseUpdate,
    usuario: CurrentUserDep,
    session: DbDep,
    expense_id: str,
    background_tasks: BackgroundTasks,
) -> ExpenseOut:
    valores = datos.model_dump(exclude_unset=True)
    if "budget_line_id" in valores and valores["budget_line_id"] is not None:
        valores["budget_line_id"] = _uuid_o_422(valores["budget_line_id"], "budget_line_id")
    gasto = await service.editar_gasto(
        session,
        background_tasks,
        actor_user_id=usuario.id,
        organization_id=usuario.organization_id,
        expense_id=_uuid_o_422(expense_id, "expense_id"),
        datos=valores,
    )
    return _expense_response(gasto)


@router.delete(
    "/expenses/{expense_id}",
    summary="Borrar un gasto manual",
    description="409 si el gasto es en especie.",
    status_code=204,
    dependencies=[require_permission(Permission.ACCOUNTING_WRITE)],
)
async def delete_expense(
    usuario: CurrentUserDep,
    session: DbDep,
    expense_id: str,
    background_tasks: BackgroundTasks,
) -> None:
    await service.borrar_gasto(
        session,
        background_tasks,
        actor_user_id=usuario.id,
        organization_id=usuario.organization_id,
        expense_id=_uuid_o_422(expense_id, "expense_id"),
    )


@router.put(
    "/sponsors/{sponsor_id}/in-kind-valuation",
    summary="Fijar (o borrar) la valoración en especie de un patrocinador",
    description=(
        "Crea/actualiza en la misma transacción el gasto enlazado "
        "(`UNIQUE(sponsor_id)`). `valoracion_cents=null` borra el gasto "
        "enlazado. Solo para patrocinadores `en_especie` (422 en cualquier otro caso)."
    ),
    response_model=InKindValuationOut,
    dependencies=[require_permission(Permission.ACCOUNTING_WRITE)],
)
async def set_in_kind_valuation(
    datos: InKindValuationIn,
    usuario: CurrentUserDep,
    session: DbDep,
    sponsor_id: str,
    background_tasks: BackgroundTasks,
) -> InKindValuationOut:
    resultado = await service.fijar_valoracion_en_especie(
        session,
        background_tasks,
        actor_user_id=usuario.id,
        organization_id=usuario.organization_id,
        sponsor_id=_uuid_o_422(sponsor_id, "sponsor_id"),
        valoracion_cents=datos.valoracion_cents,
        budget_line_id=(
            _uuid_o_422(datos.budget_line_id, "budget_line_id")
            if datos.budget_line_id is not None
            else None
        ),
    )
    return InKindValuationOut(
        sponsor_id=str(resultado.sponsor.id),
        in_kind_valuation_cents=resultado.sponsor.in_kind_valuation_cents,
        expense_id=str(resultado.gasto.id) if resultado.gasto is not None else None,
    )
