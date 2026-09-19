"""Métricas del escritorio de la plataforma.

Lo que el administrador de la instalación necesita para operarla: si las
dependencias responden, cuánto hay, y qué hacen las organizaciones — **sin ver
las cifras de ninguna**, que es la frontera del producto. Para mirar el negocio
de una organización hay que suplantar una cuenta.

Corre con el motor de mantenimiento (`BYPASSRLS`), así que ve todas las filas de
todas las organizaciones. Ese poder es lo que hace que el allowlist de
`metrics_schemas.py` no sea una formalidad: aquí no puede salir ningún importe.

**Agregados en SQL, no recorridos en el cliente.** Las cifras por organización
salen de consultas agrupadas; una instalación con muchas organizaciones y muchos
eventos no debe provocar que el escritorio se traiga las filas para contarlas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import redis_healthy
from app.core.storage import get_storage
from app.modules.admin.metrics_schemas import (
    ActividadDeOrganizacionOut,
    CifrasDeLaInstalacionOut,
    MetricasDePlataformaOut,
    SaludDeLaInstalacionOut,
)
from app.modules.events.models import Event
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.payments.models import OrganizationStripeAccount
from app.modules.registrations.models import EventRegistration
from app.modules.users.models import User

#: Días sin ningún acceso a partir de los cuales una organización se considera
#: parada. Se declara aquí y no en la interfaz: la bandera se calcula en el
#: servidor, porque es un juicio sobre los datos, no una decisión de pintado.
_DIAS_SIN_ACCESO = 30


async def _salud(session: AsyncSession) -> SaludDeLaInstalacionOut:
    """El estado de las dependencias.

    Se comprueban aquí y no se llama a `GET /health`: una petición HTTP interna
    añadiría un salto de red y un modo de fallo nuevos para leer un booleano que
    se obtiene igual de directo. Las tres comprobaciones son las mismas que usa
    aquel endpoint.
    """
    from sqlalchemy import text

    try:
        await session.execute(text("SELECT 1"))
        base = "ok"
    except Exception:  # noqa: BLE001 — cualquier fallo de conexión es «error»
        base = "error"

    try:
        almacen = await get_storage().healthcheck()
    except Exception:  # noqa: BLE001
        almacen = False

    try:
        cache = await redis_healthy()
    except Exception:  # noqa: BLE001
        cache = False

    return SaludDeLaInstalacionOut(
        database=base,
        storage="ok" if almacen else "error",
        redis="ok" if cache else "error",
    )


async def _cifras(session: AsyncSession) -> CifrasDeLaInstalacionOut:
    """Los totales de la instalación, cada uno una consulta agregada."""

    async def contar(modelo: Any, **filtros: Any) -> int:
        consulta = select(func.count()).select_from(modelo)
        if filtros:
            consulta = consulta.filter_by(**filtros)
        return int(await session.scalar(consulta) or 0)

    return CifrasDeLaInstalacionOut(
        organizaciones_activas=await contar(Organization, is_active=True),
        organizaciones_totales=await contar(Organization),
        eventos_totales=await contar(Event),
        eventos_publicados=await contar(Event, status="published"),
        usuarios=await contar(User),
        miembros=await contar(OrganizationMember),
    )


async def _actividad(session: AsyncSession) -> list[ActividadDeOrganizacionOut]:
    """Qué hace cada organización, contado en SQL y sin ningún importe.

    Los conteos por organización salen de subconsultas escalares dentro de una
    sola consulta: hacer una por organización y por métrica sería un viaje por
    celda de la tabla.
    """
    sub_eventos = (
        select(func.count())
        .select_from(Event)
        .where(Event.organization_id == Organization.id)
        .scalar_subquery()
    )
    sub_publicados = (
        select(func.count())
        .select_from(Event)
        .where(Event.organization_id == Organization.id, Event.status == "published")
        .scalar_subquery()
    )
    sub_inscripciones = (
        select(func.count())
        .select_from(EventRegistration)
        .where(EventRegistration.organization_id == Organization.id)
        .scalar_subquery()
    )
    sub_miembros = (
        select(func.count())
        .select_from(OrganizationMember)
        .where(OrganizationMember.organization_id == Organization.id)
        .scalar_subquery()
    )
    # Las tres marcas y su diferencia: `updated_at` es «última vez que se tocó»,
    # `created_at` «último dado de alta».
    sub_evento_tocado = (
        select(func.max(Event.updated_at))
        .where(Event.organization_id == Organization.id)
        .scalar_subquery()
    )
    sub_evento_creado = (
        select(func.max(Event.created_at))
        .where(Event.organization_id == Organization.id)
        .scalar_subquery()
    )
    sub_inscripcion = (
        select(func.max(EventRegistration.created_at))
        .where(EventRegistration.organization_id == Organization.id)
        .scalar_subquery()
    )
    sub_acceso = (
        select(func.max(OrganizationMember.last_seen_at))
        .where(OrganizationMember.organization_id == Organization.id)
        .scalar_subquery()
    )
    sub_stripe = (
        select(func.count())
        .select_from(OrganizationStripeAccount)
        .where(
            OrganizationStripeAccount.organization_id == Organization.id,
            OrganizationStripeAccount.deauthorized_at.is_(None),
        )
        .scalar_subquery()
    )
    # «Tiene eventos de pago publicados» es un booleano, no un importe: dice que
    # quiere cobrar, no cuánto cobra.
    sub_pago_publicado = (
        select(func.count())
        .select_from(Event)
        .where(
            Event.organization_id == Organization.id,
            Event.status == "published",
            Event.registration_mode == "paid",
        )
        .scalar_subquery()
    )

    filas = (
        await session.execute(
            select(
                Organization.id,
                Organization.name,
                Organization.slug,
                Organization.is_active,
                sub_eventos.label("eventos"),
                sub_publicados.label("publicados"),
                sub_inscripciones.label("inscripciones"),
                sub_miembros.label("miembros"),
                sub_evento_tocado.label("evento_tocado"),
                sub_evento_creado.label("evento_creado"),
                sub_inscripcion.label("inscripcion"),
                sub_acceso.label("acceso"),
                sub_stripe.label("stripe"),
                sub_pago_publicado.label("pago_publicado"),
            ).order_by(Organization.name)
        )
    ).all()

    return [_fila_a_actividad(fila) for fila in filas]


def _fila_a_actividad(fila: Any) -> ActividadDeOrganizacionOut:
    eventos = int(fila[4] or 0)
    publicados = int(fila[5] or 0)
    inscripciones = int(fila[6] or 0)
    stripe = int(fila[12] or 0) > 0
    publicados_de_pago = int(fila[13] or 0) > 0

    return ActividadDeOrganizacionOut(
        id=str(fila[0]),
        name=fila[1],
        slug=fila[2],
        is_active=fila[3],
        eventos=eventos,
        eventos_publicados=publicados,
        inscripciones=inscripciones,
        miembros=int(fila[7] or 0),
        evento_mas_reciente=_iso(fila[8]),
        ultimo_evento_creado=_iso(fila[9]),
        ultima_inscripcion=_iso(fila[10]),
        ultimo_acceso=_iso(fila[11]),
        stripe_conectada=stripe,
        # Las dos banderas que convierten los datos sueltos en una alerta.
        tiene_stripe_pendiente_con_eventos_de_pago=publicados_de_pago and not stripe,
        publicados_sin_inscripciones=publicados > 0 and inscripciones == 0,
    )


def _iso(valor: Any) -> str | None:
    """`None` se mantiene como `None`: «no consta» no es una fecha."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.isoformat()
    return str(valor)


async def metricas_de_la_plataforma(session: AsyncSession) -> MetricasDePlataformaOut:
    """Compone el escritorio de la instalación."""
    return MetricasDePlataformaOut(
        salud=await _salud(session),
        cifras=await _cifras(session),
        organizaciones=await _actividad(session),
    )
