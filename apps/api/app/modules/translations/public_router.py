"""Traducción al vuelo desde la web pública.

Cuando alguien navega en un idioma activo y lo que ve aún no está traducido, la
web (ya en el navegador, nunca el SSR) pide aquí la traducción de esa página y
consulta cada pocos segundos si ha terminado. El GET público que sirve el
contenido no lanza nada: no tiene efectos secundarios.

Frenos: solo idiomas activos de la organización, solo con su clave de IA propia,
un tope diario por organización y limitación de ritmo por IP.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Query
from fastapi.routing import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import set_organization_context
from app.core.deps import SessionDep
from app.core.locale import Locale
from app.core.ratelimit import PUBLICO_POR_IP, limit_per_ip
from app.core.redis_client import get_redis
from app.modules.events.models import Event
from app.modules.events.public_deps import EVENTO_PARA_MOSTRAR, ruta_de_evento
from app.modules.organizations import service as organizations_service
from app.modules.organizations.models import Organization
from app.modules.translations import cola
from app.modules.translations.models import ContentTranslation
from app.modules.translations.service import idiomas_de_contenido
from app.shared.errors import NotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public", tags=["público"])

#: Traducciones al vuelo por organización y día (decisión del dueño).
TOPE_DIARIO_AL_VUELO = 200
#: Cuánto vale la marca «en cola» mientras la tarea arranca.
MARCA_EN_COLA_S = 120
#: Peticiones de traducción por IP: pocas, la web pide una vez por página.
PETICIONES_POR_IP = 30

LocaleQuery = Annotated[Locale, Query(description="Idioma de la página")]


class TranslationRequestResult(BaseModel):
    """`queued`: hay traducción en marcha y merece la pena consultar el estado."""

    queued: bool


class TranslationStatus(BaseModel):
    in_progress: bool


async def _pedir_al_vuelo(session: AsyncSession, ambito: cola.Ambito) -> bool:
    """Encola la traducción del ámbito si se puede. No lanza: si algo falla, la
    web se queda con el original."""
    organizacion = await session.get(Organization, ambito.organization_id)
    if organizacion is None:
        return False
    activos = await idiomas_de_contenido(session, organizacion)
    if ambito.locale not in activos or len(activos) < 2:
        return False
    if not await cola.clave_propia(session, ambito.organization_id):
        return False
    try:
        redis = get_redis()
        if await redis.exists(cola.marca_en_cola(ambito)):
            return True  # Ya hay una en marcha: no se encola otra.
        clave_dia = f"traduccion-vuelo:{ambito.organization_id}:{datetime.now(UTC):%Y%m%d}"
        usadas = await redis.incr(clave_dia)
        if usadas == 1:
            await redis.expire(clave_dia, int(timedelta(days=2).total_seconds()))
        if usadas > TOPE_DIARIO_AL_VUELO:
            return False
        await redis.set(cola.marca_en_cola(ambito), "1", ex=MARCA_EN_COLA_S)
        from app.core.tasks import traducir_contenido_task

        await traducir_contenido_task.kiq(
            str(ambito.organization_id),
            str(ambito.event_id) if ambito.event_id else None,
            ambito.locale,
        )
    except Exception:
        # Sin Redis no hay cola: se sirve el original y nada más.
        logger.warning("No se ha podido encolar una traducción al vuelo.", exc_info=True)
        return False
    return True


async def _en_curso(session: AsyncSession, ambito: cola.Ambito) -> bool:
    """Hay campos del ámbito reservados por una tarea, o una tarea a punto de
    arrancar (marca en Redis)."""
    reciente = datetime.now(UTC) - cola.RESERVA_CADUCA
    filtro_evento = (
        ContentTranslation.event_id.is_(None)
        if ambito.event_id is None
        else ContentTranslation.event_id == ambito.event_id
    )
    reservados = await session.scalar(
        select(func.count())
        .select_from(ContentTranslation)
        .where(
            ContentTranslation.organization_id == ambito.organization_id,
            filtro_evento,
            ContentTranslation.locale == ambito.locale,
            ContentTranslation.status == "en_curso",
            ContentTranslation.updated_at > reciente,
        )
    )
    if reservados:
        return True
    try:
        return bool(await get_redis().exists(cola.marca_en_cola(ambito)))
    except Exception:
        return False


# ── Evento ──────────────────────────────────────────────────────────────────


@ruta_de_evento(
    router,
    "post",
    "/translations",
    summary="Pedir la traducción al vuelo de un evento",
    response_model=TranslationRequestResult,
    limite=("traduccion-al-vuelo", PETICIONES_POR_IP),
)
async def request_event_translation(
    evento: Annotated[Event, Depends(EVENTO_PARA_MOSTRAR)],
    session: SessionDep,
    locale: LocaleQuery,
) -> TranslationRequestResult:
    ambito = cola.Ambito(evento.organization_id, evento.id, locale)
    return TranslationRequestResult(queued=await _pedir_al_vuelo(session, ambito))


@ruta_de_evento(
    router,
    "get",
    "/translations/status",
    summary="Si la traducción al vuelo de un evento sigue en marcha",
    response_model=TranslationStatus,
    limite=("traduccion-estado", PUBLICO_POR_IP),
)
async def event_translation_status(
    evento: Annotated[Event, Depends(EVENTO_PARA_MOSTRAR)],
    session: SessionDep,
    locale: LocaleQuery,
) -> TranslationStatus:
    ambito = cola.Ambito(evento.organization_id, evento.id, locale)
    return TranslationStatus(in_progress=await _en_curso(session, ambito))


# ── Lo de la organización: su página y los perfiles de ponente ─────────────


async def _organizacion_de_ponente(session: SessionDep, public_slug: str) -> uuid.UUID:
    organization_id = await session.scalar(
        text("SELECT app_resolve_speaker_organization(:slug)"), {"slug": public_slug}
    )
    if organization_id is None:
        raise NotFoundError("El ponente no existe.")
    await set_organization_context(session, organization_id)
    return uuid.UUID(str(organization_id))


@router.post(
    "/organizations/{org_slug}/translations",
    summary="Pedir la traducción al vuelo de la página de una organización",
    response_model=TranslationRequestResult,
    dependencies=[limit_per_ip("traduccion-al-vuelo", PETICIONES_POR_IP)],
)
async def request_organization_translation(
    org_slug: str, session: SessionDep, locale: LocaleQuery
) -> TranslationRequestResult:
    organizacion = await organizations_service.resolve_public_organization(session, org_slug)
    ambito = cola.Ambito(organizacion.id, None, locale)
    return TranslationRequestResult(queued=await _pedir_al_vuelo(session, ambito))


@router.get(
    "/organizations/{org_slug}/translations/status",
    summary="Si la traducción al vuelo de una organización sigue en marcha",
    response_model=TranslationStatus,
    dependencies=[limit_per_ip("traduccion-estado", PUBLICO_POR_IP)],
)
async def organization_translation_status(
    org_slug: str, session: SessionDep, locale: LocaleQuery
) -> TranslationStatus:
    organizacion = await organizations_service.resolve_public_organization(session, org_slug)
    return TranslationStatus(
        in_progress=await _en_curso(session, cola.Ambito(organizacion.id, None, locale))
    )


@router.post(
    "/speakers/{public_slug}/translations",
    summary="Pedir la traducción al vuelo del perfil de un ponente",
    response_model=TranslationRequestResult,
    dependencies=[limit_per_ip("traduccion-al-vuelo", PETICIONES_POR_IP)],
)
async def request_speaker_translation(
    public_slug: str, session: SessionDep, locale: LocaleQuery
) -> TranslationRequestResult:
    organization_id = await _organizacion_de_ponente(session, public_slug)
    ambito = cola.Ambito(organization_id, None, locale)
    return TranslationRequestResult(queued=await _pedir_al_vuelo(session, ambito))


@router.get(
    "/speakers/{public_slug}/translations/status",
    summary="Si la traducción al vuelo del perfil de un ponente sigue en marcha",
    response_model=TranslationStatus,
    dependencies=[limit_per_ip("traduccion-estado", PUBLICO_POR_IP)],
)
async def speaker_translation_status(
    public_slug: str, session: SessionDep, locale: LocaleQuery
) -> TranslationStatus:
    organization_id = await _organizacion_de_ponente(session, public_slug)
    return TranslationStatus(
        in_progress=await _en_curso(session, cola.Ambito(organization_id, None, locale))
    )
