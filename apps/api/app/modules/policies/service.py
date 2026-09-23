"""Versiones de política: guardado y resolución del texto vigente.

Regla de resolución para un evento y un tipo: la última versión del evento si
tiene texto propio; si no la hay o su `content` es `None` («vuelve a
heredar»), la última de la organización; si está retirada (`''`) o no
existe, ninguno. Invariante: un texto vigente siempre lleva el `id` de la
fila cuyo contenido se muestra, nunca el de una fila de evento vacía.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.events.models import Event
from app.modules.policies.models import TIPOS_DE_POLITICA, OrganizationPolicyVersion
from app.modules.policies.schemas import LIMITE_CARACTERES
from app.shared.errors import ConflictError, NotFoundError, ValidationDomainError


@dataclass(frozen=True)
class Vigente:
    """Resolución de un tipo en un evento."""

    kind: str
    #: `evento`, `organizacion` o `ninguno`.
    origen: str
    #: La fila que se muestra y se acepta (`None` si `origen == "ninguno"`).
    version: OrganizationPolicyVersion | None
    #: El texto de la organización, vigente o no en el evento.
    de_organizacion: OrganizationPolicyVersion | None


def _tiene_texto(fila: OrganizationPolicyVersion | None) -> bool:
    return fila is not None and bool(fila.content)


def _validar_tipo(kind: str) -> None:
    if kind not in TIPOS_DE_POLITICA:
        raise NotFoundError("Ese tipo de texto no existe.")


async def _ultimas(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID | None
) -> dict[tuple[uuid.UUID | None, str], OrganizationPolicyVersion]:
    """Última versión por `(event_id, kind)` de la organización y, si se pide,
    del evento, en una sola consulta (`DISTINCT ON`)."""
    alcance: ColumnElement[bool] = OrganizationPolicyVersion.event_id.is_(None)
    if event_id is not None:
        alcance = or_(alcance, OrganizationPolicyVersion.event_id == event_id)
    consulta = (
        select(OrganizationPolicyVersion)
        .where(OrganizationPolicyVersion.organization_id == organization_id, alcance)
        .order_by(
            OrganizationPolicyVersion.event_id,
            OrganizationPolicyVersion.kind,
            OrganizationPolicyVersion.version.desc(),
        )
        .distinct(OrganizationPolicyVersion.event_id, OrganizationPolicyVersion.kind)
    )
    filas = (await session.scalars(consulta)).all()
    return {(fila.event_id, fila.kind): fila for fila in filas}


async def ultimas_de_organizacion(
    session: AsyncSession, organization_id: uuid.UUID
) -> dict[str, OrganizationPolicyVersion]:
    """Última versión de cada tipo de la organización, retirada o no."""
    ultimas = await _ultimas(session, organization_id, None)
    return {kind: fila for (_, kind), fila in ultimas.items()}


async def vigentes_de_evento(
    session: AsyncSession, organization_id: uuid.UUID, event_id: uuid.UUID
) -> list[Vigente]:
    """Resolución de los cuatro tipos para un evento, en orden de muestra."""
    ultimas = await _ultimas(session, organization_id, event_id)
    resultado: list[Vigente] = []
    for kind in TIPOS_DE_POLITICA:
        propia = ultimas.get((event_id, kind))
        de_organizacion = ultimas.get((None, kind))
        de_organizacion = de_organizacion if _tiene_texto(de_organizacion) else None
        if _tiene_texto(propia):
            resultado.append(Vigente(kind, "evento", propia, de_organizacion))
        elif de_organizacion is not None:
            resultado.append(Vigente(kind, "organizacion", de_organizacion, de_organizacion))
        else:
            resultado.append(Vigente(kind, "ninguno", None, None))
    return resultado


async def guardar_version(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID | None,
    kind: str,
    content: str | None,
    user_id: uuid.UUID | None,
) -> OrganizationPolicyVersion:
    """Guarda una versión nueva; nunca modifica una anterior.

    Organización: `content` obligatorio; vacío (o solo espacios) = retirar.
    Evento: `None` = volver a heredar; si no, texto propio no vacío.
    """
    _validar_tipo(kind)
    if content is not None and len(content) > LIMITE_CARACTERES:
        raise ValidationDomainError(
            f"El texto no puede superar los {LIMITE_CARACTERES} caracteres."
        )
    if event_id is None:
        if content is None:
            raise ValidationDomainError("El texto de la organización no puede ser nulo.")
        content = content if content.strip() else ""
    elif content is not None and not content.strip():
        raise ValidationDomainError(
            "Un texto propio del evento no puede estar vacío; para usar el de la "
            "organización, vuelve a heredarlo."
        )

    mismo_alcance = (
        OrganizationPolicyVersion.event_id.is_(None)
        if event_id is None
        else OrganizationPolicyVersion.event_id == event_id
    )
    ultima = await session.scalar(
        select(OrganizationPolicyVersion)
        .where(
            OrganizationPolicyVersion.organization_id == organization_id,
            OrganizationPolicyVersion.kind == kind,
            mismo_alcance,
        )
        .order_by(OrganizationPolicyVersion.version.desc())
        .limit(1)
    )
    # Idempotente: guardar sin cambios no crea versión. Si la creara, cada
    # «Guardar» sin tocar nada obligaría a volver a aceptar las condiciones a
    # quien tenga el formulario de inscripción abierto.
    if ultima is not None and ultima.content == content:
        return ultima
    fila = OrganizationPolicyVersion(
        organization_id=organization_id,
        event_id=event_id,
        kind=kind,
        content=content,
        version=(ultima.version if ultima is not None else 0) + 1,
        created_by=user_id,
    )
    # SAVEPOINT: si dos personas guardan a la vez, la segunda choca con el
    # índice único de versión y la transacción de la petición sigue viva para
    # responder con un 409 legible en vez de un 500.
    try:
        async with session.begin_nested():
            session.add(fila)
    except IntegrityError as exc:
        raise ConflictError(
            "Otra persona ha guardado este texto a la vez; recarga y vuelve a intentarlo."
        ) from exc
    await session.refresh(fila)
    return fila


async def obtener_version(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    version_id: uuid.UUID,
) -> OrganizationPolicyVersion:
    """Una versión concreta del evento o de su organización (para consultar lo
    que aceptó una inscripción). Las de otro evento no se devuelven."""
    fila = await session.scalar(
        select(OrganizationPolicyVersion).where(
            OrganizationPolicyVersion.id == version_id,
            OrganizationPolicyVersion.organization_id == organization_id,
            or_(
                OrganizationPolicyVersion.event_id.is_(None),
                OrganizationPolicyVersion.event_id == event_id,
            ),
        )
    )
    if fila is None or fila.content is None:
        raise NotFoundError("Esa versión no existe.")
    return fila


#: Código del 409 que el formulario de inscripción reconoce para recargar los
#: textos y pedir que se vuelvan a aceptar (distinto del 409 de «evento de
#: pago», que el cliente distingue por este código, no por el estado HTTP).
CODIGO_POLITICAS_CAMBIADAS = "politicas_cambiadas"


async def comprobar_aceptacion(
    session: AsyncSession, event: Event, aceptadas: list[uuid.UUID]
) -> list[uuid.UUID]:
    """Comprueba que se aceptaron exactamente los textos vigentes del evento.

    Compara conjuntos de valores, nunca resuelve cada id contra la BD: un id
    inventado, de otra organización o de una versión antigua cae siempre en
    el mismo 409 controlado. Sin textos vigentes no se exige nada. Devuelve
    las versiones aceptadas, para guardarlas en el consentimiento.
    """
    vigentes = [
        vigente.version.id
        for vigente in await vigentes_de_evento(session, event.organization_id, event.id)
        if vigente.version is not None
    ]
    if not vigentes:
        return []
    if set(aceptadas) != set(vigentes):
        raise ConflictError(
            "Las condiciones del organizador han cambiado mientras rellenabas el "
            "formulario. Revísalas y vuelve a aceptarlas.",
            extra={"code": CODIGO_POLITICAS_CAMBIADAS},
        )
    return vigentes


async def versiones_por_ids(
    session: AsyncSession, organization_id: uuid.UUID, ids: list[uuid.UUID]
) -> list[OrganizationPolicyVersion]:
    """Las versiones aceptadas por una inscripción, en orden de muestra."""
    if not ids:
        return []
    filas = (
        await session.scalars(
            select(OrganizationPolicyVersion).where(
                OrganizationPolicyVersion.organization_id == organization_id,
                OrganizationPolicyVersion.id.in_(ids),
            )
        )
    ).all()
    return sorted(filas, key=lambda fila: TIPOS_DE_POLITICA.index(fila.kind))
