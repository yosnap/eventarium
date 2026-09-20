"""Borradores de gasto extraídos de un justificante (fase 4 de trabajo).

Fichero propio y no una sección más de `service.py`: el módulo tiene un techo
de mil líneas por fichero y este dominio —subida, extracción asíncrona,
confirmación con bloqueo, descarte y reintento— es una frontera real, con su
propio worker y su propia taxonomía de errores.

Reglas que gobiernan todo lo de aquí:

- **La extracción nunca corre en el camino HTTP.** La subida guarda el objeto,
  crea el borrador en `pending_extraction` y encola; el resto lo hace el
  worker. Una llamada a un modelo de visión tarda segundos y puede fallar: una
  petición HTTP no es sitio para eso.
- **El modelo nunca autoconfirma.** Lo extraído es una propuesta que una
  persona revisa y confirma, y la confirmación revalida importes y pertenencia
  de la partida en el servidor. El peor resultado de un documento con
  instrucciones incrustadas es un campo erróneo que alguien ve antes de
  confirmar.
- **Degradación controlada.** Sin configuración de IA, con el servicio
  apagado o con el límite de gasto agotado, el borrador queda
  `extraction_failed` con su `error_code` y el justificante sigue en el
  almacén: recuperable, nunca un 500 ni un borrador perdido.
- Toda mutación audita como `BackgroundTask` tras el commit, igual que el
  resto del módulo (`service.auditar`).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from botocore.exceptions import ClientError
from fastapi import BackgroundTasks
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import SessionApp, maintenance_session, set_organization_context
from app.core.storage import ALLOWED_DOCUMENT_MIMES, build_object_key, get_storage, validate_upload
from app.modules.accounting import ocr_client, rasterizacion, repository
from app.modules.accounting.models import AccountingExpense, AccountingExpenseDraft
from app.modules.accounting.service import auditar
from app.modules.ai_gateway import errores as ai_errores
from app.shared.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationDomainError,
)

if TYPE_CHECKING:  # pragma: no cover - solo para el comprobador de tipos
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

#: Centinela que lleva `ocr_provider` mientras el borrador está pendiente: el
#: modelo efectivo aún no se conoce, lo resuelve la pasarela en el momento de
#: la llamada. Al liquidar con éxito se sobrescribe con `"{provider}/{model}"`.
MOTOR_PENDIENTE = "ai_gateway"

#: Prefijo de almacenamiento de justificantes y de sus páginas rasterizadas.
PREFIJO_DE_JUSTIFICANTES = "accounting-receipts"

#: Estados desde los que todavía se puede descartar un borrador.
ESTADOS_DESCARTABLES = ("pending_extraction", "pending_review", "extraction_failed")

#: Único `error_code` que el barrido reintenta por tiempo (ver R3 del plan):
#: es el único transitorio de verdad.
ERROR_REINTENTABLE_POR_TIEMPO = ai_errores.PROVEEDOR_ERROR

#: Único `error_code` que admite el reintento manual: se agotó el presupuesto
#: de IA y el organizador ya ha ampliado el límite.
ERROR_REINTENTABLE_A_MANO = ai_errores.LIMITE_SUPERADO

#: Valor de `AccountingExpense.receipt_status` de un gasto nacido de un
#: borrador: el justificante está adjunto y es el que se extrajo.
RECEIPT_STATUS_CONFIRMADO = "adjuntado"

#: Cuántos borradores atascados reencola como mucho una pasada del barrido.
#: Conservador a propósito, del orden de los límites de `ai_gateway`: tras una
#: caída larga del proveedor, soltar el atasco entero de golpe sobre la cola y
#: sobre el presupuesto de IA es peor que repartirlo entre varias pasadas.
MAXIMO_REENCOLADAS_POR_PASADA = 20


# --- Subida y alta del borrador ---------------------------------------------


async def crear_draft_desde_documento(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    contenido: bytes,
) -> AccountingExpenseDraft:
    """Valida los bytes reales, guarda el objeto, crea el borrador y encola.

    La validación va **antes** de tocar el almacén y antes de crear ninguna
    fila: un documento no soportado o que supera `max_document_bytes` se
    rechaza sin borrador y sin consumir la pasarela.

    El encolado se hace como `BackgroundTask` y no con un `.kiq` inline: la
    transacción de la petición todavía no ha hecho `commit` cuando este
    servicio termina, y un worker rápido buscaría un borrador que aún no
    existe.
    """
    settings = get_settings()
    mime, extension = validate_upload(
        contenido,
        max_bytes=settings.max_document_bytes,
        allowed_mimes=ALLOWED_DOCUMENT_MIMES,
    )

    clave = build_object_key(organization_id, PREFIJO_DE_JUSTIFICANTES, extension)
    almacen = get_storage()
    try:
        await almacen.put_object(clave, contenido, mime, content_disposition="attachment")
    except ClientError as exc:
        raise ConflictError("No se ha podido guardar el justificante.") from exc

    borrador = AccountingExpenseDraft(
        event_id=event_id,
        organization_id=organization_id,
        receipt_object_key=clave,
        ocr_provider=MOTOR_PENDIENTE,
        extracted_fields={},
        field_confidence={},
        status="pending_extraction",
        attempts=0,
    )
    session.add(borrador)
    try:
        await session.flush()
    except IntegrityError as exc:
        await _borrar_objeto(clave)
        raise ConflictError("No se ha podido dar de alta el borrador de gasto.") from exc

    background_tasks.add_task(
        auditar,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action="accounting.draft.created",
        entity_type="accounting_expense_draft",
        entity_id=str(borrador.id),
        detail={"event_id": str(event_id), "mime": mime},
    )
    background_tasks.add_task(encolar_extraccion, borrador.id, organization_id)
    return borrador


async def encolar_extraccion(draft_id: uuid.UUID, organization_id: uuid.UUID) -> None:
    """Encola la extracción. Importa la tarea aquí dentro para no arrastrar el
    broker (y con él todo `core/tasks.py`) en cada importación del módulo."""
    from app.core.tasks import extraer_campos_task

    await extraer_campos_task.kiq(str(draft_id), str(organization_id))


async def _borrar_objeto(clave: str | None) -> None:
    """Borra del almacén sin dejar que un fallo del almacén tumbe la operación
    de dominio: el objeto huérfano es un problema menor que un 500."""
    if not clave:
        return
    try:
        await get_storage().delete_object(clave)
    except ClientError:
        logger.warning("No se ha podido borrar el objeto %s del almacén.", clave)


# --- Extracción asíncrona (cuerpo de `extraer_campos_task`) -----------------


@dataclass(frozen=True, slots=True)
class _Documento:
    contenido: bytes
    mime: str


def _codigo_de_error(exc: BaseException) -> str:
    """Excepción → `error_code` de la taxonomía cerrada de la pasarela.

    Nunca inventa un código fuera de `ai_errores.CODIGOS_DE_ERROR`: esa
    columna es lo único que distingue «amplía el límite» de «este documento no
    se puede leer», y el barrido decide con ella si reintentar.
    """
    if isinstance(exc, ai_errores.ServicioDesactivado):
        return ai_errores.SERVICIO_DESACTIVADO
    if isinstance(exc, ai_errores.SinConfiguracion):
        return ai_errores.SIN_CONFIGURACION
    if isinstance(exc, ai_errores.LimiteDeGastoSuperado):
        return ai_errores.LIMITE_SUPERADO
    if isinstance(exc, ai_errores.CredencialIlegible):
        return ai_errores.CREDENCIAL_ILEGIBLE
    if isinstance(exc, ai_errores.ErrorDeProveedor):
        codigo = getattr(exc, "error_code", ai_errores.PROVEEDOR_ERROR)
        return codigo if codigo in ai_errores.CODIGOS_DE_ERROR else ai_errores.PROVEEDOR_ERROR
    if isinstance(exc, ocr_client.RespuestaFueraDeEsquema | rasterizacion.DocumentoIlegible):
        # Ni una respuesta fuera de esquema ni un PDF ilegible mejoran
        # repitiendo la llamada: quedan a la vista, sin reintento en bucle.
        return ai_errores.PAYLOAD_INVALIDO
    return ai_errores.PROVEEDOR_ERROR


async def extraer_campos(draft_id: uuid.UUID, organization_id: uuid.UUID) -> None:
    """Cuerpo de `extraer_campos_task`. Nunca propaga: deja el borrador
    explicado.

    Tres tramos, con las transacciones lo más cortas posible y **ninguna**
    abierta durante la llamada al modelo: `SessionApp` + contexto de
    organización (nunca la sesión de mantenimiento) porque las tablas llevan
    `FORCE ROW LEVEL SECURITY` y un worker sin petición HTTP no debe escribir
    esquivando RLS. Mismo criterio que `ai_gateway.client`.
    """
    documento = await _reservar_intento(draft_id, organization_id)
    if documento is None:
        return

    settings = get_settings()
    try:
        imagenes = await _preparar_imagenes(documento, settings=settings)
        await _guardar_rasterizada(draft_id, organization_id, documento, imagenes)
        extraccion = await ocr_client.extraer(organization_id=organization_id, imagenes=imagenes)
    except Exception as exc:  # noqa: BLE001 - se traduce a `error_code`, no se propaga
        codigo = _codigo_de_error(exc)
        logger.warning(
            "Extracción fallida del borrador %s (%s): %s",
            draft_id,
            type(exc).__name__,
            codigo,
        )
        await _marcar_fallo(draft_id, organization_id, codigo)
        return

    await _liquidar_extraccion(draft_id, organization_id, extraccion=extraccion)


async def _reservar_intento(draft_id: uuid.UUID, organization_id: uuid.UUID) -> _Documento | None:
    """Tramo 1: cuenta el intento y lee el justificante.

    Devuelve `None` si el borrador ya no está pendiente (lo confirmó o
    descartó alguien, o esta tarea llegó duplicada): la tarea es idempotente,
    nunca pisa un borrador que ya salió de `pending_extraction`.
    """
    async with _sesion_de_organizacion(organization_id) as tx:
        borrador = await repository.get_draft_for_update(tx, organization_id, draft_id)
        if borrador is None or borrador.status != "pending_extraction":
            return None
        borrador.attempts += 1
        clave = borrador.receipt_object_key

    try:
        contenido, mime = await get_storage().get_object(clave)
    except ClientError:
        logger.error("El justificante %s del borrador %s no está en el almacén.", clave, draft_id)
        await _marcar_fallo(draft_id, organization_id, ai_errores.PAYLOAD_INVALIDO)
        return None
    return _Documento(contenido=contenido, mime=mime)


async def _preparar_imagenes(
    documento: _Documento, *, settings: Settings
) -> list[rasterizacion.ImagenParaOcr]:
    """Rasteriza en un hilo aparte: PDFium es síncrono y bloquearía el bucle de
    eventos del worker durante toda la conversión."""
    return await asyncio.to_thread(
        rasterizacion.preparar_para_ocr,
        documento.contenido,
        documento.mime,
        max_paginas=settings.accounting_ocr_max_pdf_pages,
        ancho_maximo_px=settings.accounting_ocr_raster_max_width,
    )


async def _guardar_rasterizada(
    draft_id: uuid.UUID,
    organization_id: uuid.UUID,
    documento: _Documento,
    imagenes: list[rasterizacion.ImagenParaOcr],
) -> None:
    """Guarda la primera página rasterizada junto al original y **la deja ya
    referenciada en la fila del borrador**.

    Lo segundo es tan importante como lo primero: si la clave solo se
    escribiera al liquidar una extracción con éxito, un fallo del modelo se
    llevaría la clave con la excepción y el PNG —con los datos fiscales y
    personales del justificante— quedaría en el almacén sin ninguna fila que
    lo nombrara, imposible de borrar ni por el descarte ni por nada. Con la
    clave en base de datos antes de llamar al modelo, el descarte normal la
    borra siempre.

    Solo si hubo rasterización de verdad: si el justificante ya era una
    imagen, el original **es** lo que se envió y no hay nada que duplicar. Un
    fallo del almacén aquí no aborta la extracción: la previsualización es una
    comodidad, no el dato.
    """
    if not imagenes or documento.mime != "application/pdf":
        return
    primera = imagenes[0]
    clave = build_object_key(organization_id, PREFIJO_DE_JUSTIFICANTES, primera.extension)
    try:
        await get_storage().put_object(
            clave, primera.contenido, primera.mime, content_disposition="attachment"
        )
    except ClientError:
        logger.warning("No se ha podido guardar la página rasterizada %s.", clave)
        return
    await _borrar_objeto(await _apuntar_rasterizada(draft_id, organization_id, clave))


async def _apuntar_rasterizada(
    draft_id: uuid.UUID, organization_id: uuid.UUID, clave: str
) -> str | None:
    """Escribe `rasterized_object_key` y devuelve la clave que sobra por
    borrar, si la hay.

    Dos casos de sobra, los dos del mismo estilo: la de un intento anterior
    que este reintento acaba de sustituir, y la recién subida cuando el
    borrador ya no está pendiente —alguien lo descartó o lo confirmó mientras
    se rasterizaba— y por tanto nadie la referenciaría nunca.
    """
    async with _sesion_de_organizacion(organization_id) as tx:
        borrador = await repository.get_draft_for_update(tx, organization_id, draft_id)
        if borrador is None or borrador.status != "pending_extraction":
            return clave
        anterior = borrador.rasterized_object_key
        borrador.rasterized_object_key = clave
        return anterior if anterior != clave else None


async def _liquidar_extraccion(
    draft_id: uuid.UUID,
    organization_id: uuid.UUID,
    *,
    extraccion: ocr_client.Extraccion,
) -> None:
    """Escribe lo extraído. **No toca `rasterized_object_key`**: esa ya quedó
    persistida antes de llamar al modelo, precisamente para que un fallo no la
    pierda."""
    async with _sesion_de_organizacion(organization_id) as tx:
        borrador = await repository.get_draft_for_update(tx, organization_id, draft_id)
        if borrador is None or borrador.status != "pending_extraction":
            return
        borrador.extracted_fields = extraccion.campos
        borrador.field_confidence = extraccion.confianza
        borrador.ocr_provider = extraccion.motor
        borrador.error_code = None
        borrador.status = "pending_review"


async def _marcar_fallo(draft_id: uuid.UUID, organization_id: uuid.UUID, codigo: str) -> None:
    if codigo not in ai_errores.CODIGOS_DE_ERROR:
        codigo = ai_errores.PROVEEDOR_ERROR
    async with _sesion_de_organizacion(organization_id) as tx:
        borrador = await repository.get_draft_for_update(tx, organization_id, draft_id)
        if borrador is None or borrador.status != "pending_extraction":
            return
        borrador.status = "extraction_failed"
        borrador.error_code = codigo


@asynccontextmanager
async def _sesion_de_organizacion(organization_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Sesión propia del worker con el rol `app_user` y el contexto RLS puesto.

    Mismo patrón que `ai_gateway.client._sesion_de_organizacion`, repetido
    aquí porque el de allí es privado de aquel módulo y exportarlo acoplaría
    los dos por una utilidad de transacción. `SessionApp` y nunca
    `maintenance_session()`: las tablas llevan `FORCE ROW LEVEL SECURITY` y un
    worker sin petición HTTP tampoco debe escribir esquivando RLS.
    """
    async with SessionApp() as session:
        async with session.begin():
            await set_organization_context(session, organization_id)
            yield session


# --- Barrido de extracciones atascadas --------------------------------------


async def reencolar_extracciones_atascadas() -> int:
    """Cuerpo de `sweep_stuck_extractions_task`. Devuelve cuántas reencoló.

    Dos pasos, igual que `ai_gateway.client.cerrar_reservas_abandonadas`: el
    descubrimiento es transversal y va con la sesión de mantenimiento en solo
    lectura; la escritura va organización a organización bajo RLS.

    **Nunca** reencola un borrador con `error_code="limite_superado"` (R3):
    con el límite agotado, cada pasada consumiría una reserva y la quemaría.
    Ese estado se recupera solo con el reintento manual del organizador, tras
    ampliar el límite.

    Cada pasada reencola como mucho `MAXIMO_REENCOLADAS_POR_PASADA`: lo que
    no entre espera a la siguiente, empezando siempre por lo más antiguo.
    """
    settings = get_settings()
    async with maintenance_session() as lectura:
        pendientes = await repository.drafts_reencolables(
            lectura,
            minutos=settings.accounting_ocr_stuck_minutes,
            max_intentos=settings.accounting_ocr_max_attempts,
            error_code_reintentable=ERROR_REINTENTABLE_POR_TIEMPO,
            limite=MAXIMO_REENCOLADAS_POR_PASADA,
        )
        agotados = await repository.contar_drafts_agotados(
            lectura, max_intentos=settings.accounting_ocr_max_attempts
        )

    reencoladas = 0
    for draft_id, organization_id in pendientes:
        async with _sesion_de_organizacion(organization_id) as tx:
            borrador = await repository.get_draft_for_update(tx, organization_id, draft_id)
            if borrador is None or borrador.status not in (
                "pending_extraction",
                "extraction_failed",
            ):
                continue
            if (
                borrador.status == "extraction_failed"
                and borrador.error_code != ERROR_REINTENTABLE_POR_TIEMPO
            ):
                continue
            borrador.status = "pending_extraction"
            borrador.error_code = None
        await encolar_extraccion(draft_id, organization_id)
        reencoladas += 1

    if agotados:
        logger.error(
            "Hay %s extracción(es) de justificante agotadas tras %s intentos: "
            "esperan una acción manual en el panel de contabilidad.",
            agotados,
            settings.accounting_ocr_max_attempts,
        )
    return reencoladas


# --- Reintento manual --------------------------------------------------------


async def reintentar_draft(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    draft_id: uuid.UUID,
) -> AccountingExpenseDraft:
    """Vuelve a encolar un borrador que se quedó sin presupuesto de IA.

    Solo `limite_superado`: cualquier otro `error_code` devuelve 422, porque
    repetir la llamada daría exactamente el mismo resultado y el organizador
    merece saberlo en vez de reintentar a ciegas. `attempts` sigue contando
    con el mismo tope: un reintento manual tampoco es infinito.
    """
    borrador = await repository.get_draft_for_update(session, organization_id, draft_id)
    if borrador is None:
        raise NotFoundError("Ese borrador de gasto no existe.")
    if borrador.status != "extraction_failed":
        raise ConflictError("Ese borrador no está en estado fallido.")
    if borrador.error_code != ERROR_REINTENTABLE_A_MANO:
        raise ValidationDomainError(
            "Solo se puede reintentar una extracción que falló por presupuesto de IA "
            "agotado. Este borrador falló por otro motivo y repetirla daría el mismo "
            "resultado."
        )
    if borrador.attempts >= get_settings().accounting_ocr_max_attempts:
        raise ConflictError(
            "Este borrador ha agotado sus intentos de extracción: da de alta el gasto "
            "a mano desde el justificante."
        )

    borrador.status = "pending_extraction"
    borrador.error_code = None
    await session.flush()

    background_tasks.add_task(
        auditar,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action="accounting.draft.retried",
        entity_type="accounting_expense_draft",
        entity_id=str(borrador.id),
        detail={"attempts": borrador.attempts},
    )
    background_tasks.add_task(encolar_extraccion, borrador.id, organization_id)
    return borrador


# --- Confirmación y descarte -------------------------------------------------


def validar_importes(
    *,
    base_cents: int,
    vat_cents: int | None,
    total_cents: int,
    confirmar_importe_alto: bool,
) -> None:
    """Revalida los importes en el servidor, sobre lo que envía la persona.

    Lo extraído por el modelo no decide nada de esto: un `total` inyectado
    desde el propio documento no cuadra con `base + iva` y se rechaza aquí.
    `vat_cents=None` es «exento», el único caso en que `total == base`.
    """
    if base_cents < 0 or total_cents < 0 or (vat_cents is not None and vat_cents < 0):
        raise ValidationDomainError("Ningún importe del gasto puede ser negativo.")
    if total_cents != base_cents + (vat_cents or 0):
        raise ValidationDomainError(
            "`total_cents` debe ser `base_cents + vat_cents` (o `base_cents` si exento)."
        )
    techo = get_settings().accounting_expense_confirmation_ceiling_cents
    if total_cents > techo and not confirmar_importe_alto:
        # `code` estable en el `problem+json`: el cliente pide la segunda
        # confirmación por este identificador, no por el texto del mensaje,
        # que puede reescribirse sin romper a nadie.
        raise ValidationDomainError(
            "El importe supera el techo de confirmación automática: vuelve a enviarlo "
            "con «confirmar_importe_alto» si es correcto.",
            extra={"code": "importe_sobre_techo"},
        )


async def confirmar_draft(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    draft_id: uuid.UUID,
    datos: dict[str, Any],
) -> AccountingExpense:
    """Da de alta el gasto a partir del borrador, con dos barreras contra la
    doble confirmación: el bloqueo de la fila del borrador y el índice único
    parcial `uq_accounting_expenses_draft_id`.

    Nunca la llama nada que no sea el endpoint de confirmación: es el único
    punto donde una persona declara que los importes son correctos.
    """
    member_id = await repository.get_member_id(session, organization_id, actor_user_id)
    if member_id is None:
        # No debería ocurrir con una sesión válida de la organización; si
        # ocurre, la constancia de quién confirmó se perdería y eso no se
        # acepta en silencio en un alta de gasto.
        raise PermissionDeniedError("No perteneces a esta organización.")

    borrador = await repository.get_draft_for_update(session, organization_id, draft_id)
    if borrador is None:
        raise NotFoundError("Ese borrador de gasto no existe.")
    if borrador.status != "pending_review":
        raise ConflictError("Ese borrador ya no está pendiente de revisión.")

    budget_line_id = datos.get("budget_line_id")
    if budget_line_id is not None:
        linea = await repository.get_budget_line(session, organization_id, budget_line_id)
        if linea is None or linea.event_id != borrador.event_id:
            raise ValidationDomainError(
                "Esa partida de presupuesto no existe en el evento de este borrador."
            )

    validar_importes(
        base_cents=datos["base_cents"],
        vat_cents=datos.get("vat_cents"),
        total_cents=datos["total_cents"],
        confirmar_importe_alto=bool(datos.get("confirmar_importe_alto", False)),
    )

    gasto = AccountingExpense(
        event_id=borrador.event_id,
        organization_id=organization_id,
        budget_line_id=budget_line_id,
        sponsor_id=None,
        provider_name=datos["provider_name"],
        expense_date=datos["expense_date"],
        base_cents=datos["base_cents"],
        vat_cents=datos.get("vat_cents"),
        total_cents=datos["total_cents"],
        receipt_object_key=borrador.receipt_object_key,
        receipt_status=RECEIPT_STATUS_CONFIRMADO,
        draft_id=borrador.id,
    )
    session.add(gasto)

    borrador.status = "confirmed"
    borrador.confirmed_by_member_id = member_id
    borrador.confirmed_at = datetime.now(UTC)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("Ese borrador ya se había confirmado.") from exc
    borrador.confirmed_expense_id = gasto.id
    await session.flush()

    background_tasks.add_task(
        auditar,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action="accounting.draft.confirmed",
        entity_type="accounting_expense_draft",
        entity_id=str(borrador.id),
        detail={
            "expense_id": str(gasto.id),
            "total_cents": gasto.total_cents,
            "ocr_provider": borrador.ocr_provider,
        },
    )
    return gasto


async def descartar_draft(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    draft_id: uuid.UUID,
) -> AccountingExpenseDraft:
    """Descarta el borrador y **borra sus objetos del almacén en cuanto la
    respuesta sale**.

    Sin papelera: un justificante descartado es un documento con datos
    personales y fiscales que nadie va a usar, y conservarlo «por si acaso» es
    exactamente lo que el PRD no quiere.

    El borrado va como `BackgroundTask` y no inline, igual que en
    `sponsors/router.py` y `events/router.py`: aquí solo hay `flush`, y el
    `commit` real lo hace la dependencia de sesión al terminar la petición.
    Borrando inline, un `commit` fallido dejaría el borrador vivo y
    confirmable apuntando a un objeto que ya no existe.

    Verificado: la tarea corre **tras** el `commit`. Diferir el borrado a una
    tarea de fondo es condición necesaria pero no suficiente — una dependencia
    con `yield` declarada sin `scope` termina después de enviar la respuesta, y
    por tanto después de las tareas de fondo. Lo que cierra la garantía es que
    `core/deps.py` declara la sesión con `scope="function"`; el test
    `test_el_descarte_borra_del_almacen_solo_tras_el_commit` vigila el orden y
    falla si alguien revierte ese `scope`.
    """
    borrador = await repository.get_draft_for_update(session, organization_id, draft_id)
    if borrador is None:
        raise NotFoundError("Ese borrador de gasto no existe.")
    if borrador.status not in ESTADOS_DESCARTABLES:
        raise ConflictError("Ese borrador ya está confirmado o descartado.")

    claves = [borrador.receipt_object_key, borrador.rasterized_object_key]
    borrador.status = "discarded"
    await session.flush()

    background_tasks.add_task(
        auditar,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action="accounting.draft.discarded",
        entity_type="accounting_expense_draft",
        entity_id=str(borrador.id),
        detail={"event_id": str(borrador.event_id)},
    )
    for clave in claves:
        background_tasks.add_task(_borrar_objeto, clave)
    return borrador
