"""Servicio de analítica externa de la plataforma: configuración de
proveedores y agregados de consentimientos (fase 1 del plan
`260916-2246-cookies-analitica-externa`)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.modules.admin.analytics_schemas import (
    UMBRAL_DE_SUPRESION,
    AnalyticsSettingsUpdate,
    CeldaDeConsentimientos,
)
from app.modules.platform.models import PlatformAnalyticsSettings

RANGO_MAXIMO_DIAS = 366
"""El agregado cubre como máximo un año: más rango no aporta (la vista es
semanal) y agranda la superficie de consulta sin necesidad."""


def _fila_de_reserva() -> PlatformAnalyticsSettings:
    """Objeto en memoria con todo a `None`: defensa si la fila `'default'`
    no existiera (mismo patrón que la identidad de plataforma)."""
    return PlatformAnalyticsSettings(singleton="default")


async def obtener_configuracion_analitica(
    session: AsyncSession,
) -> PlatformAnalyticsSettings:
    """La configuración única de proveedores (la fila `'default'`)."""
    fila = (await session.execute(
        select(PlatformAnalyticsSettings).where(
            PlatformAnalyticsSettings.singleton == "default"
        )
    )).scalar_one_or_none()
    return fila or _fila_de_reserva()


async def actualizar_configuracion_analitica(
    session: AsyncSession,
    datos: AnalyticsSettingsUpdate,
    actor_user_id: uuid.UUID,
) -> PlatformAnalyticsSettings:
    """Reemplaza los tres identificadores y lo deja registrado en auditoría."""
    fila = await obtener_configuracion_analitica(session)
    fila.ga4_measurement_id = datos.ga4_measurement_id
    fila.meta_pixel_id = datos.meta_pixel_id
    fila.cloudflare_analytics_token = datos.cloudflare_analytics_token
    fila.gtm_container_id = datos.gtm_container_id
    await session.flush()

    await registrar_auditoria(
        session,
        actor_user_id=actor_user_id,
        organization_id=None,
        action="platform.analytics_settings.update",
        entity_type="platform_analytics_settings",
        entity_id="default",
        detail={
            "ga4_measurement_id": fila.ga4_measurement_id,
            "meta_pixel_id": fila.meta_pixel_id,
            "cloudflare_analytics_token": fila.cloudflare_analytics_token,
            "gtm_container_id": fila.gtm_container_id,
        },
    )
    return fila


def _acotar_rango(desde: date | None, hasta: date | None) -> tuple[date, date]:
    """Rango semanal por defecto (últimas 12 semanas) y acotado a un año.

    El agregado es por semana (`date_trunc('week')`, lunes), así que el rango
    se redondea a lunes para que las celdas del borde estén completas.
    """
    hoy = date.today()
    hasta_efectivo = hasta or hoy
    desde_efectivo = desde or (hasta_efectivo - timedelta(days=12 * 7))
    if (hasta_efectivo - desde_efectivo).days > RANGO_MAXIMO_DIAS:
        raise ValueError("El rango no puede superar un año.")
    if desde_efectivo > hasta_efectivo:
        raise ValueError("El inicio no puede ser posterior al fin.")
    # Lunes de la semana de `desde` (weekday(): lunes=0).
    desde_efectivo -= timedelta(days=desde_efectivo.weekday())
    # Lunes siguiente al `hasta` (exclusivo): cubre la semana en curso completa.
    hasta_efectivo += timedelta(days=7 - hasta_efectivo.weekday())
    return desde_efectivo, hasta_efectivo


async def agregados_de_consentimiento(
    session: AsyncSession,
    desde: date | None,
    hasta: date | None,
) -> list[CeldaDeConsentimientos]:
    """Agregado semanal × categoría, con supresión de celdas pequeñas.

    El `GROUP BY` lo hace PostgreSQL (nunca un bucle Python sobre filas
    individuales): la consulta solo devuelve celdas ya agregadas, ninguna
    fila de `cookie_consents` sale de la base de datos.
    """
    desde_efectivo, hasta_efectivo = _acotar_rango(desde, hasta)

    filas = (await session.execute(
        text(
            """
            SELECT date_trunc('week', created_at AT TIME ZONE 'UTC')::date AS semana,
                   categoria,
                   count(*) AS total
            FROM cookie_consents,
                 jsonb_array_elements_text(categories_accepted) AS categoria
            WHERE created_at >= :desde
              AND created_at < :hasta
            GROUP BY semana, categoria
            ORDER BY semana, categoria
            """
        ),
        {"desde": desde_efectivo, "hasta": hasta_efectivo},
    )).all()

    return [
        CeldaDeConsentimientos(
            semana=semana,
            categoria=categoria,
            total=total if total >= UMBRAL_DE_SUPRESION else None,
        )
        for semana, categoria, total in filas
    ]
