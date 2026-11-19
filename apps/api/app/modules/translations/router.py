"""Traducciones del contenido en el panel (`/translations`).

La pestaña de idioma de cada formulario lee y guarda aquí los textos de su
entidad. Cada entidad exige el mismo permiso que editar su original.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.deps import CurrentUserDep, DbDep, PermissionsDep
from app.core.locale import Locale
from app.core.permissions import Permission
from app.modules.events.models import EventSession, EventVenue
from app.modules.nearby.models import EventNearbyPlace
from app.modules.payments.models import EventTicketType
from app.modules.registrations.models import EventRegistrationQuestion
from app.modules.sponsors.models import Sponsor
from app.modules.translations import panel, service
from app.modules.translations.campos import TipoDeEntidad
from app.modules.translations.schemas import (
    EventTranslationSummary,
    LocaleProgress,
    TranslationEditor,
    TranslationItem,
    TranslationReview,
    TranslationSave,
)
from app.shared.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationDomainError,
)

router = APIRouter(prefix="/translations", tags=["traducciones"])

LocaleQuery = Annotated[Locale, Query(description="Idioma de la traducción")]


def _uuid_o_404(valor: str) -> uuid.UUID:
    try:
        return uuid.UUID(valor)
    except ValueError as exc:
        raise NotFoundError("No existe.") from exc


def _tipo_o_404(valor: str) -> TipoDeEntidad:
    if valor not in panel.TIPOS_EDITABLES:
        raise NotFoundError("No existe.")
    return valor


async def _editor(session: DbDep, entidad: panel.Entidad, locale: Locale) -> TranslationEditor:
    campos = [
        campo
        for campo in await panel.campos_de(session, entidad)
        if entidad.origen_de(campo) != locale
    ]
    if locale not in entidad.activos:
        campos = []
    return TranslationEditor(
        locale=locale,
        source_locale=entidad.origen,
        locales=list(entidad.activos),
        items=[
            TranslationItem.model_validate(item)
            for item in await panel.estado(session, entidad, campos, locale)
        ],
    )


@router.get(
    "/{entity_type}/{entity_id}",
    summary="Textos de una entidad en un idioma",
    response_model=TranslationEditor,
)
async def get_translations(
    entity_type: str,
    entity_id: str,
    locale: LocaleQuery,
    session: DbDep,
    usuario: CurrentUserDep,
    permisos: PermissionsDep,
) -> TranslationEditor:
    entidad = await panel.abrir(
        session,
        usuario,
        permisos,
        _tipo_o_404(entity_type),
        _uuid_o_404(entity_id),
        escribir=False,
    )
    return await _editor(session, entidad, locale)


@router.put(
    "/{entity_type}/{entity_id}",
    summary="Guardar las traducciones escritas a mano",
    response_model=TranslationEditor,
)
async def save_translations(
    entity_type: str,
    entity_id: str,
    locale: LocaleQuery,
    datos: TranslationSave,
    session: DbDep,
    usuario: CurrentUserDep,
    permisos: PermissionsDep,
) -> TranslationEditor:
    entidad = await panel.abrir(
        session,
        usuario,
        permisos,
        _tipo_o_404(entity_type),
        _uuid_o_404(entity_id),
        escribir=True,
    )
    campos: dict[tuple[str, str, str], panel.Campo] = {
        (campo.tipo, str(campo.entity_id), campo.campo): campo
        for campo in await panel.campos_de(session, entidad)
    }
    for item in datos.items:
        campo = campos.get((item.entity_type, item.entity_id, item.field))
        if campo is None:
            raise ValidationDomainError("Ese campo no se puede traducir.")
        if entidad.origen_de(campo) == locale or locale not in entidad.activos:
            raise ValidationDomainError("La organización no publica en ese idioma.")
        if not (item.value or "").strip():
            await service.borrar_campos(
                session,
                usuario.organization_id,
                campo.tipo,
                campo.entity_id,
                [campo.campo],
                locale=locale,
            )
            continue
        await service.guardar_manual(
            session,
            organization_id=usuario.organization_id,
            event_id=entidad.event_id,
            tipo=campo.tipo,
            entity_id=campo.entity_id,
            campo=campo.campo,
            locale=locale,
            valor=item.value or "",
            original=campo.original,
            origen_del_contenido=entidad.origen_de(campo),
            idiomas_activos=entidad.activos,
            user_id=usuario.id,
        )
    return await _editor(session, entidad, locale)


@router.post(
    "/{entity_type}/{entity_id}/review",
    summary="Marcar una traducción como revisada",
    response_model=TranslationEditor,
)
async def review_translation(
    entity_type: str,
    entity_id: str,
    locale: LocaleQuery,
    datos: TranslationReview,
    session: DbDep,
    usuario: CurrentUserDep,
    permisos: PermissionsDep,
) -> TranslationEditor:
    entidad = await panel.abrir(
        session,
        usuario,
        permisos,
        _tipo_o_404(entity_type),
        _uuid_o_404(entity_id),
        escribir=True,
    )
    campo = next(
        (
            c
            for c in await panel.campos_de(session, entidad)
            if (c.tipo, str(c.entity_id), c.campo)
            == (datos.entity_type, datos.entity_id, datos.field)
        ),
        None,
    )
    if campo is None:
        raise ValidationDomainError("Ese campo no se puede traducir.")
    if datos.original is not None and datos.original != campo.original:
        # El original cambió mientras se revisaba: se revisaría contra otro texto.
        raise ConflictError(
            "El texto original ha cambiado mientras lo revisabas. Recarga y vuelve a revisarlo."
        )
    await service.marcar_revisada(
        session,
        organization_id=usuario.organization_id,
        tipo=campo.tipo,
        entity_id=campo.entity_id,
        campo=campo.campo,
        locale=locale,
        original=campo.original,
        user_id=usuario.id,
    )
    return await _editor(session, entidad, locale)


#: Lo que cuelga de un evento y cuenta en su resumen de traducción.
_HIJOS_DEL_EVENTO: tuple[tuple[TipoDeEntidad, Any], ...] = (
    ("session", EventSession),
    ("venue", EventVenue),
    ("ticket_type", EventTicketType),
    ("question", EventRegistrationQuestion),
    ("sponsor", Sponsor),
    ("nearby_place", EventNearbyPlace),
)


@router.get(
    "/events/{event_id}/summary",
    summary="Cuántos textos del evento están al día en cada idioma",
    response_model=EventTranslationSummary,
)
async def event_translation_summary(
    event_id: str, session: DbDep, usuario: CurrentUserDep, permisos: PermissionsDep
) -> EventTranslationSummary:
    if Permission.EVENTS_READ not in permisos:
        raise PermissionDeniedError("No tienes permiso para traducir este contenido.")
    evento = await panel.abrir(
        session, usuario, permisos, "event", _uuid_o_404(event_id), escribir=False
    )
    entidades = [evento]
    for tipo, modelo in _HIJOS_DEL_EVENTO:
        filas: Any = await session.scalars(
            select(modelo).where(
                modelo.organization_id == usuario.organization_id,
                modelo.event_id == evento.fila.id,
            )
        )
        entidades += [
            panel.Entidad(
                tipo=tipo,
                fila=fila,
                event_id=evento.fila.id,
                origen=evento.origen,
                origen_organizacion=evento.origen_organizacion,
                activos=evento.activos,
            )
            for fila in filas
        ]
    destinos = [locale for locale in evento.activos if locale != evento.origen]
    cuentas = await panel.progreso(session, entidades, destinos)
    progreso = [
        LocaleProgress(locale=locale, total=cuentas[locale][0], up_to_date=cuentas[locale][1])
        for locale in destinos
    ]
    return EventTranslationSummary(source_locale=evento.origen, locales=progreso)
