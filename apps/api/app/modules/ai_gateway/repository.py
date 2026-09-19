"""Acceso a datos de la configuración de IA y de los interruptores.

Como el resto de repositorios del proyecto, filtra siempre por
`organization_id` de forma explícita: RLS es la red de seguridad, no el
filtro principal.

Las dos tablas de plataforma se **leen** con la sesión que traiga quien
llama —incluida la `SessionApp` de una organización, que tiene `SELECT`
concedido (V-3/V-4)— y solo se **escriben** desde el módulo `admin` con la
sesión de mantenimiento, porque `app_user` tiene revocado el DML sobre ellas
(V-2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_gateway.errores import LIMITE_SUPERADO, LimiteDeGastoSuperado
from app.modules.ai_gateway.models import (
    ESTADO_FALLIDO,
    ESTADO_LIQUIDADO,
    ESTADO_RESERVADO,
    ESTADOS_QUE_GASTAN,
    ID_FILA_DE_PLATAFORMA,
    AiUsagePeriod,
    AiUsageRecord,
    OrganizationAiSettings,
    OrganizationService,
    PlatformAiSettings,
    PlatformService,
)


async def get_platform_settings(session: AsyncSession) -> PlatformAiSettings | None:
    """La fila única de configuración de plataforma, o `None` si no existe."""
    fila: PlatformAiSettings | None = await session.scalar(
        select(PlatformAiSettings).where(PlatformAiSettings.id == ID_FILA_DE_PLATAFORMA)
    )
    return fila


async def get_or_create_platform_settings(session: AsyncSession) -> PlatformAiSettings:
    """La fila única, creándola vacía si todavía no existe.

    Solo la llama el módulo `admin` (sesión de mantenimiento): `app_user`
    no puede insertar en esta tabla.
    """
    fila = await get_platform_settings(session)
    if fila is None:
        fila = PlatformAiSettings(id=ID_FILA_DE_PLATAFORMA)
        session.add(fila)
        await session.flush()
    return fila


async def get_organization_settings(
    session: AsyncSession, organization_id: uuid.UUID
) -> OrganizationAiSettings | None:
    """El override de una organización, o `None` si hereda de plataforma."""
    fila: OrganizationAiSettings | None = await session.scalar(
        select(OrganizationAiSettings).where(
            OrganizationAiSettings.organization_id == organization_id
        )
    )
    return fila


async def delete_organization_settings(session: AsyncSession, organization_id: uuid.UUID) -> bool:
    """Borra el override. Devuelve si había algo que borrar."""
    fila = await get_organization_settings(session, organization_id)
    if fila is None:
        return False
    await session.delete(fila)
    await session.flush()
    return True


async def list_platform_services(session: AsyncSession) -> list[PlatformService]:
    filas = await session.scalars(select(PlatformService).order_by(PlatformService.service_key))
    return list(filas)


async def get_platform_service(session: AsyncSession, service_key: str) -> PlatformService | None:
    fila: PlatformService | None = await session.scalar(
        select(PlatformService).where(PlatformService.service_key == service_key)
    )
    return fila


async def set_platform_service(
    session: AsyncSession, service_key: str, *, enabled: bool
) -> PlatformService:
    """Enciende o apaga un interruptor global (solo el admin)."""
    fila = await get_platform_service(session, service_key)
    if fila is None:
        fila = PlatformService(service_key=service_key, enabled=enabled)
        session.add(fila)
    else:
        fila.enabled = enabled
    await session.flush()
    return fila


async def list_organization_service_overrides(
    session: AsyncSession, organization_id: uuid.UUID
) -> list[OrganizationService]:
    filas = await session.scalars(
        select(OrganizationService)
        .where(OrganizationService.organization_id == organization_id)
        .order_by(OrganizationService.service_key)
    )
    return list(filas)


async def force_organization_service_off(
    session: AsyncSession, organization_id: uuid.UUID, service_key: str
) -> None:
    """Fuerza el servicio a apagado para esa organización (idempotente)."""
    existente = await session.scalar(
        select(OrganizationService).where(
            OrganizationService.organization_id == organization_id,
            OrganizationService.service_key == service_key,
        )
    )
    if existente is None:
        session.add(
            OrganizationService(
                organization_id=organization_id, service_key=service_key, enabled=False
            )
        )
        await session.flush()


async def clear_organization_service_override(
    session: AsyncSession, organization_id: uuid.UUID, service_key: str
) -> None:
    """Vuelve a heredar: borra el override (idempotente).

    No existe «forzar on» (V-7): heredar es la única alternativa a apagado.
    """
    await session.execute(
        delete(OrganizationService).where(
            OrganizationService.organization_id == organization_id,
            OrganizationService.service_key == service_key,
        )
    )
    await session.flush()


# --- Uso y límite de gasto (fase 2) ------------------------------------------


def periodo_actual(ahora: datetime | None = None) -> str:
    """`'YYYY-MM'` en UTC. El periodo del límite de gasto es el mes natural.

    UTC y no la zona de la organización a propósito: el límite es un tope
    técnico de coste, no un cierre contable, y hacerlo depender de una zona
    horaria por organización abriría un solape en el que dos llamadas de la
    misma organización caerían en periodos distintos según el reloj.
    """
    momento = ahora or datetime.now(UTC)
    return f"{momento.year:04d}-{momento.month:02d}"


def rango_del_periodo(periodo: str) -> tuple[datetime, datetime]:
    """`[inicio, fin)` del periodo, en UTC. `fin` es el inicio del siguiente."""
    año, mes = (int(parte) for parte in periodo.split("-"))
    inicio = datetime(año, mes, 1, tzinfo=UTC)
    if mes == 12:
        return inicio, datetime(año + 1, 1, 1, tzinfo=UTC)
    return inicio, datetime(año, mes + 1, 1, tzinfo=UTC)


async def asegurar_periodo(session: AsyncSession, organization_id: uuid.UUID, periodo: str) -> None:
    """Crea la fila de periodo si no existe, sin fallar si otra la creó antes.

    `ON CONFLICT DO NOTHING` y no un `SELECT` previo: entre el `SELECT` y el
    `INSERT` cabe la llamada concurrente que esta fila existe justamente para
    serializar.
    """
    await session.execute(
        text(
            "INSERT INTO ai_usage_periods (organization_id, periodo) "
            "VALUES (:organization_id, :periodo) ON CONFLICT DO NOTHING"
        ),
        {"organization_id": organization_id, "periodo": periodo},
    )


async def bloquear_periodo(session: AsyncSession, organization_id: uuid.UUID, periodo: str) -> None:
    """`SELECT … FOR UPDATE` sobre la fila de periodo.

    El bloqueo dura lo que tarde la reserva —unos milisegundos— y se suelta
    con el `commit` de esa transacción, **antes** de la llamada de red: nunca
    bajo un bloqueo de fila mientras dura una llamada externa, la misma regla
    que `payments/refunds_service.py`.
    """
    await session.execute(
        select(AiUsagePeriod.periodo)
        .where(
            AiUsagePeriod.organization_id == organization_id,
            AiUsagePeriod.periodo == periodo,
        )
        .with_for_update()
    )


async def gasto_del_periodo(
    session: AsyncSession, organization_id: uuid.UUID, periodo: str
) -> Decimal:
    """Suma de `cost_usd` de las filas que gastan, reservas incluidas.

    Incluir las `reservado` es lo que cierra la carrera: la segunda llamada
    concurrente ve el importe que la primera ya apartó, aunque esta todavía
    esté hablando con el proveedor. Las `fallido` no suman — el proveedor no
    llegó a cobrarlas.
    """
    inicio, fin = rango_del_periodo(periodo)
    total = await session.scalar(
        select(func.coalesce(func.sum(AiUsageRecord.cost_usd), 0)).where(
            AiUsageRecord.organization_id == organization_id,
            AiUsageRecord.status.in_(ESTADOS_QUE_GASTAN),
            AiUsageRecord.created_at >= inicio,
            AiUsageRecord.created_at < fin,
        )
    )
    return Decimal(total or 0)


async def reservar_uso(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    periodo: str,
    use_case: str,
    provider: str,
    model: str,
    coste_estimado_usd: Decimal,
    limite_usd: Decimal | None,
) -> AiUsageRecord:
    """Aparta el importe estimado o rechaza la llamada. Bajo el bloqueo.

    Quien llama tiene que haber bloqueado ya la fila de periodo: sin ese
    bloqueo, dos reservas simultáneas leerían el mismo gasto acumulado y las
    dos pasarían.

    Se compara `gasto + estimación` con el límite, no solo el gasto ya
    consumido: una llamada que, de completarse, dejaría el periodo por encima
    del tope se rechaza antes de salir a la red, que es de lo que sirve tener
    un límite.

    El rechazo deja fila (`fallido` / `limite_superado`) antes de lanzar: sin
    ella, el único código de la taxonomía que el organizador necesita
    entender —«te has quedado sin presupuesto»— sería precisamente el único
    que nunca aparecería en su histórico. El importe que guarda es el que se
    habría apartado, para que quede constancia de cuánto se intentó gastar;
    como la fila es `fallido`, no suma al gasto del periodo.

    Quien llama tiene que dejar que la transacción se cierre con normalidad
    antes de propagar la excepción, o el `rollback` se llevará esa fila por
    delante (lo hace `client._reservar`).
    """
    if limite_usd is not None:
        gastado = await gasto_del_periodo(session, organization_id, periodo)
        if gastado + coste_estimado_usd > limite_usd:
            session.add(
                AiUsageRecord(
                    organization_id=organization_id,
                    use_case=use_case,
                    provider=provider,
                    model=model,
                    status=ESTADO_FALLIDO,
                    error_code=LIMITE_SUPERADO,
                    cost_usd=coste_estimado_usd,
                    cost_auditable=False,
                )
            )
            await session.flush()
            raise LimiteDeGastoSuperado(
                extra={
                    "limite_usd": str(limite_usd),
                    "gasto_usd": str(gastado),
                    "periodo": periodo,
                }
            )

    fila = AiUsageRecord(
        organization_id=organization_id,
        use_case=use_case,
        provider=provider,
        model=model,
        status=ESTADO_RESERVADO,
        cost_usd=coste_estimado_usd,
        cost_auditable=False,
    )
    session.add(fila)
    await session.flush()
    return fila


async def liquidar(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    record_id: uuid.UUID,
    coste_usd: Decimal,
    cost_auditable: bool,
    input_tokens: int | None,
    output_tokens: int | None,
    latency_ms: int,
) -> None:
    """Sustituye la reserva por el resultado real de la llamada.

    Condicionada a `status = 'reservado'`: si el barrido se adelantó y ya la
    marcó `reserva_abandonada`, la liquidación no la resucita — el gasto ya
    está contado y reescribirlo dejaría el histórico contradiciendo al aviso
    que el barrido registró.
    """
    await session.execute(
        update(AiUsageRecord)
        .where(
            AiUsageRecord.id == record_id,
            AiUsageRecord.organization_id == organization_id,
            AiUsageRecord.status == ESTADO_RESERVADO,
        )
        .values(
            status=ESTADO_LIQUIDADO,
            cost_usd=coste_usd,
            cost_auditable=cost_auditable,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            updated_at=datetime.now(UTC),
        )
    )


async def liquidar_fallo(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    record_id: uuid.UUID,
    error_code: str,
    latency_ms: int | None = None,
) -> None:
    """Cierra la reserva como fallida: deja de contar para el límite.

    Conserva `cost_usd` (la estimación) como dato histórico, pero el estado
    `fallido` la saca de la suma del periodo: lo que el proveedor no atendió
    no se cobra.
    """
    await session.execute(
        update(AiUsageRecord)
        .where(
            AiUsageRecord.id == record_id,
            AiUsageRecord.organization_id == organization_id,
            AiUsageRecord.status == ESTADO_RESERVADO,
        )
        .values(
            status=ESTADO_FALLIDO,
            error_code=error_code,
            latency_ms=latency_ms,
            updated_at=datetime.now(UTC),
        )
    )


@dataclass(frozen=True, slots=True)
class ResumenDeUso:
    """Agregado del periodo que consume el panel."""

    llamadas: int
    llamadas_fallidas: int
    gasto_usd: Decimal
    input_tokens: int
    output_tokens: int
    #: `False` si alguna fila que gasta lleva un importe solo estimado.
    gasto_auditable: bool


async def resumen_del_periodo(
    session: AsyncSession, organization_id: uuid.UUID, periodo: str
) -> ResumenDeUso:
    inicio, fin = rango_del_periodo(periodo)
    fila = (
        await session.execute(
            select(
                func.count(AiUsageRecord.id),
                func.count(AiUsageRecord.id).filter(AiUsageRecord.status == ESTADO_FALLIDO),
                func.coalesce(
                    func.sum(AiUsageRecord.cost_usd).filter(
                        AiUsageRecord.status.in_(ESTADOS_QUE_GASTAN)
                    ),
                    0,
                ),
                func.coalesce(func.sum(AiUsageRecord.input_tokens), 0),
                func.coalesce(func.sum(AiUsageRecord.output_tokens), 0),
                func.count(AiUsageRecord.id).filter(
                    AiUsageRecord.status.in_(ESTADOS_QUE_GASTAN),
                    AiUsageRecord.cost_auditable.is_(False),
                ),
            ).where(
                AiUsageRecord.organization_id == organization_id,
                AiUsageRecord.created_at >= inicio,
                AiUsageRecord.created_at < fin,
            )
        )
    ).one()
    llamadas, fallidas, gasto, entrada, salida, no_auditables = fila
    return ResumenDeUso(
        llamadas=int(llamadas),
        llamadas_fallidas=int(fallidas),
        gasto_usd=Decimal(gasto or 0),
        input_tokens=int(entrada),
        output_tokens=int(salida),
        gasto_auditable=int(no_auditables) == 0,
    )


async def ultimos_usos(
    session: AsyncSession, organization_id: uuid.UUID, *, limite: int
) -> list[AiUsageRecord]:
    """Las últimas llamadas, sin recortar por periodo: el panel enseña lo que
    pasó hace un momento aunque el mes acabe de cambiar."""
    filas = await session.scalars(
        select(AiUsageRecord)
        .where(AiUsageRecord.organization_id == organization_id)
        .order_by(AiUsageRecord.created_at.desc(), AiUsageRecord.id.desc())
        .limit(limite)
    )
    return list(filas)


@dataclass(frozen=True, slots=True)
class ErrorDeUso:
    error_code: str
    veces: int
    ultima_vez: datetime


async def ultimos_errores(
    session: AsyncSession, organization_id: uuid.UUID, *, limite: int
) -> list[ErrorDeUso]:
    """Los `error_code` recientes agrupados: la única pista de diagnóstico que
    tiene el panel, porque no hay vista de detalle (no-objetivo del PRD)."""
    filas = await session.execute(
        select(
            AiUsageRecord.error_code,
            func.count(AiUsageRecord.id),
            func.max(AiUsageRecord.created_at),
        )
        .where(
            AiUsageRecord.organization_id == organization_id,
            AiUsageRecord.error_code.is_not(None),
        )
        .group_by(AiUsageRecord.error_code)
        .order_by(func.max(AiUsageRecord.created_at).desc())
        .limit(limite)
    )
    return [
        ErrorDeUso(error_code=codigo, veces=int(veces), ultima_vez=ultima)
        for codigo, veces, ultima in filas
        if codigo is not None
    ]


async def organizaciones_con_reservas_colgadas(
    session: AsyncSession, *, minutos: int
) -> list[uuid.UUID]:
    """Qué organizaciones tienen reservas sin liquidar de más de N minutos.

    **Solo descubrimiento, y solo lectura.** Es la única consulta del barrido
    que no puede ir con el contexto de una organización fijado: averiguar
    *qué* organizaciones tienen trabajo pendiente es, por definición,
    transversal. La escritura sí va después organización a organización con
    `SessionApp` + `set_organization_context`, bajo RLS.
    """
    corte = datetime.now(UTC) - timedelta(minutes=minutos)
    filas = await session.scalars(
        select(AiUsageRecord.organization_id)
        .where(AiUsageRecord.status == ESTADO_RESERVADO, AiUsageRecord.created_at < corte)
        .group_by(AiUsageRecord.organization_id)
    )
    return list(filas)


async def marcar_reservas_abandonadas(
    session: AsyncSession, organization_id: uuid.UUID, *, minutos: int, error_code: str
) -> int:
    """Cierra como fallidas las reservas que nadie liquidó. Devuelve cuántas.

    El gasto no se pierde ni se inventa: la fila queda con la estimación que
    apartó y un `error_code` que dice que nadie confirmó qué pasó de verdad.
    """
    corte = datetime.now(UTC) - timedelta(minutes=minutos)
    resultado = await session.execute(
        update(AiUsageRecord)
        .where(
            AiUsageRecord.organization_id == organization_id,
            AiUsageRecord.status == ESTADO_RESERVADO,
            AiUsageRecord.created_at < corte,
        )
        .values(status=ESTADO_FALLIDO, error_code=error_code, updated_at=datetime.now(UTC))
    )
    # `session.execute` de un UPDATE/DELETE devuelve un `CursorResult`, que sí
    # tiene `rowcount`; los stubs de SQLAlchemy solo tipan `Result[Any]`.
    return int(resultado.rowcount or 0)  # type: ignore[attr-defined]


async def purgar_usos_antiguos(session: AsyncSession, *, dias: int) -> int:
    """Retención de `ai_usage_records`. Devuelve cuántas filas se borraron.

    Nunca borra una fila `reservado`: si quedara alguna tan antigua sería
    porque el barrido no llegó a cerrarla, y borrarla sin más escondería el
    gasto en vez de registrarlo.
    """
    corte = datetime.now(UTC) - timedelta(days=dias)
    resultado = await session.execute(
        delete(AiUsageRecord).where(
            AiUsageRecord.created_at < corte, AiUsageRecord.status != ESTADO_RESERVADO
        )
    )
    # `session.execute` de un UPDATE/DELETE devuelve un `CursorResult`, que sí
    # tiene `rowcount`; los stubs de SQLAlchemy solo tipan `Result[Any]`.
    return int(resultado.rowcount or 0)  # type: ignore[attr-defined]
