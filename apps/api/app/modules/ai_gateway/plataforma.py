"""Llamadas de IA de la propia plataforma, para traducir su contenido (legal y
categorías).

Mismo núcleo que `client.completar` (argumentos, validación del destino, llamada
al proveedor, coste y tokens), con otra contabilidad: no es de ninguna
organización, así que su uso va en `platform_ai_usage` (sin RLS, rol de
mantenimiento) y tiene su propio tope mensual en USD y un máximo de llamadas al
día, obligatorios (`platform_ai_settings`). El bloqueo es la fila única de
`platform_ai_settings`: dos reservas simultáneas no pueden leer el mismo gasto.

Nunca se usa para el contenido de una organización: eso va siempre con su clave
propia (`translations/cola.py`).
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionMaintenance
from app.modules.ai_gateway import client, errores, repository, servicios
from app.modules.ai_gateway.errores import (
    ErrorDeProveedor,
    LimiteDeGastoSuperado,
    ServicioDesactivado,
    SinConfiguracion,
)
from app.modules.ai_gateway.models import (
    ESTADO_FALLIDO,
    ESTADO_LIQUIDADO,
    ESTADO_RESERVADO,
    ESTADOS_QUE_GASTAN,
    ID_FILA_DE_PLATAFORMA,
    PlatformAiSettings,
    PlatformAiUsage,
)
from app.modules.ai_gateway.service import ConfigEfectiva, config_de_la_plataforma

logger = logging.getLogger(__name__)


async def _servicio_activo(session: AsyncSession) -> bool:
    fila = await repository.get_platform_service(session, servicios.SERVICIO_IA)
    return fila is None or fila.enabled


async def disponible(session: AsyncSession) -> bool:
    """La plataforma tiene IA con la que traducir su contenido."""
    if not await _servicio_activo(session):
        return False
    return config_de_la_plataforma(await repository.get_platform_settings(session)) is not None


async def gasto_del_mes(session: AsyncSession, ahora: datetime | None = None) -> Decimal:
    """Lo gastado (o apartado) por la plataforma en el mes natural, en UTC."""
    inicio, fin = repository.rango_del_periodo(repository.periodo_actual(ahora))
    gastado = await session.scalar(
        select(func.coalesce(func.sum(PlatformAiUsage.cost_usd), 0)).where(
            PlatformAiUsage.status.in_(ESTADOS_QUE_GASTAN),
            PlatformAiUsage.created_at >= inicio,
            PlatformAiUsage.created_at < fin,
        )
    )
    return Decimal(gastado or 0)


async def llamadas_de_hoy(session: AsyncSession, ahora: datetime | None = None) -> int:
    """Llamadas que han salido (o están saliendo) hoy, en UTC. Las que fallan
    en el proveedor cuentan; las rechazadas por tope, no."""
    momento = ahora or datetime.now(UTC)
    inicio = momento.replace(hour=0, minute=0, second=0, microsecond=0)
    total = await session.scalar(
        select(func.count()).where(
            PlatformAiUsage.created_at >= inicio,
            func.coalesce(PlatformAiUsage.error_code, "") != errores.LIMITE_SUPERADO,
        )
    )
    return int(total or 0)


async def _reservar(
    *, use_case: str, messages: list[dict[str, Any]], max_tokens: int | None
) -> tuple[PlatformAiUsage, ConfigEfectiva]:
    """Bloquea, comprueba servicio, credencial y topes, y aparta el coste.

    El rechazo por tope deja su fila (`fallido` / `limite_superado`) y se lanza
    después de cerrar la transacción, para que el `rollback` no se la lleve.
    """
    rechazo: LimiteDeGastoSuperado | None = None
    async with SessionMaintenance() as tx, tx.begin():
        if not await _servicio_activo(tx):
            raise ServicioDesactivado()
        fila = await tx.scalar(
            select(PlatformAiSettings)
            .where(PlatformAiSettings.id == ID_FILA_DE_PLATAFORMA)
            .with_for_update()
        )
        config = config_de_la_plataforma(fila)
        if fila is None or config is None or config.provider is None or not config.default_model:
            raise SinConfiguracion()
        estimado = client.estimar_coste(
            model_litellm=client.modelo_de_litellm(config.provider, config.default_model),
            messages=messages,
            max_tokens=max_tokens,
        )
        gastado = await gasto_del_mes(tx)
        llamadas = await llamadas_de_hoy(tx)
        base = {
            "use_case": use_case,
            "provider": config.provider,
            "model": config.default_model,
        }
        if (
            gastado + estimado > fila.translation_monthly_cap_usd
            or llamadas >= fila.translation_daily_calls
        ):
            tx.add(
                PlatformAiUsage(
                    **base,
                    status=ESTADO_FALLIDO,
                    error_code=errores.LIMITE_SUPERADO,
                    cost_usd=estimado,
                    cost_auditable=False,
                )
            )
            rechazo = LimiteDeGastoSuperado(
                extra={
                    "limite_usd": str(fila.translation_monthly_cap_usd),
                    "gasto_usd": str(gastado),
                    "llamadas_hoy": str(llamadas),
                }
            )
        else:
            reserva = PlatformAiUsage(
                **base, status=ESTADO_RESERVADO, cost_usd=estimado, cost_auditable=False
            )
            tx.add(reserva)
            await tx.flush()
            return reserva, config
    if rechazo is None:  # pragma: no cover - las dos ramas devuelven o rechazan
        raise SinConfiguracion()
    raise rechazo


async def _cerrar(reserva_id: Any, **valores: Any) -> None:  # noqa: ANN401
    async with SessionMaintenance() as tx, tx.begin():
        await tx.execute(
            update(PlatformAiUsage).where(PlatformAiUsage.id == reserva_id).values(**valores)
        )


async def completar(
    *,
    use_case: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    temperature: float | None = None,
    response_format: dict[str, Any] | None = None,
    timeout: float = client.TIMEOUT_POR_DEFECTO_S,
) -> client.Resultado:
    """Pide una respuesta de IA a nombre de la plataforma.

    Lanza `ServicioDesactivado`, `SinConfiguracion` o `LimiteDeGastoSuperado`
    antes de salir a la red, y `ErrorDeProveedor` si la llamada falla.
    """
    await client._precalentar_litellm()  # noqa: SLF001 - mismo núcleo que `completar`
    reserva, config = await _reservar(use_case=use_case, messages=messages, max_tokens=max_tokens)
    arranque = time.monotonic()
    try:
        argumentos = client._argumentos(config)  # noqa: SLF001
        await client._validar_destino(argumentos.api_base)  # noqa: SLF001
        respuesta = await client._llamar_proveedor(  # noqa: SLF001
            argumentos,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format,
            timeout=timeout,
        )
    except Exception as exc:
        codigo = errores.clasificar(exc)
        await _cerrar(
            reserva.id,
            status=ESTADO_FALLIDO,
            error_code=codigo,
            latency_ms=int((time.monotonic() - arranque) * 1000),
        )
        if isinstance(exc, errores.CredencialIlegible):
            raise
        # Sin encadenar: la excepción de LiteLLM lleva la clave dentro.
        raise ErrorDeProveedor(error_code=codigo) from None

    latencia = int((time.monotonic() - arranque) * 1000)
    coste, auditable = client._coste_liquidado(respuesta, reserva.cost_usd)  # noqa: SLF001
    entrada, salida = client._tokens(respuesta)  # noqa: SLF001
    await _cerrar(
        reserva.id,
        status=ESTADO_LIQUIDADO,
        cost_usd=coste,
        cost_auditable=auditable,
        input_tokens=entrada,
        output_tokens=salida,
        latency_ms=latencia,
    )
    return client.Resultado(
        contenido=client._contenido(respuesta),  # noqa: SLF001
        provider=reserva.provider,
        model=reserva.model,
        input_tokens=entrada,
        output_tokens=salida,
        cost_usd=coste,
        cost_auditable=auditable,
        latency_ms=latencia,
        usage_record_id=reserva.id,
    )


async def cerrar_reservas_abandonadas(*, minutos: int) -> int:
    """Como `client.cerrar_reservas_abandonadas`, para el uso de plataforma."""
    corte = datetime.now(UTC) - timedelta(minutes=minutos)
    async with SessionMaintenance() as tx, tx.begin():
        resultado = await tx.execute(
            update(PlatformAiUsage)
            .where(PlatformAiUsage.status == ESTADO_RESERVADO, PlatformAiUsage.created_at < corte)
            .values(status=ESTADO_FALLIDO, error_code=errores.RESERVA_ABANDONADA)
        )
    cerradas = int(getattr(resultado, "rowcount", 0) or 0)
    if cerradas:
        logger.warning("El barrido ha cerrado %s reserva(s) de IA de plataforma.", cerradas)
    return cerradas
