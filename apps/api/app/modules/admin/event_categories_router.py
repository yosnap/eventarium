"""Catálogo de categorías de eventos: lo gestiona la superadministración.

Mismo patrón que `theme_templates`: tabla de instalación, `app_user` solo
lee; aquí se escribe con la sesión de mantenimiento y `require_superadmin`. No
hay borrado: una categoría en uso se desactiva (`is_active`), y los eventos que
ya la tienen la conservan.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.deps import SCOPE_SESION, CurrentUser, get_maintenance_db, require_superadmin
from app.core.locale import LOCALES, Locale
from app.core.tras_commit import encolar_tras_commit
from app.modules.events import categories
from app.modules.events.models import EventCategory
from app.modules.events.schemas import (
    EventCategoryCreate,
    EventCategoryOut,
    EventCategoryUpdate,
)
from app.shared.errors import ConflictError, NotFoundError
from app.shared.identifiers import new_uuid7

router = APIRouter(prefix="/admin/event-categories", tags=["administración"])

MaintenanceDb = Annotated[AsyncSession, Depends(get_maintenance_db, scope=SCOPE_SESION)]
Superadmin = Annotated[CurrentUser, Depends(require_superadmin)]


def _out(categoria: EventCategory) -> EventCategoryOut:
    return EventCategoryOut(
        id=str(categoria.id),
        slug=categoria.slug,
        name=categoria.name,
        display_order=categoria.display_order,
        is_active=categoria.is_active,
        name_i18n=_traducciones(categoria.name_i18n),
        name_i18n_origin={
            locale: origen
            for locale, origen in (categoria.name_i18n_origin or {}).items()
            if locale in LOCALES and locale in (categoria.name_i18n or {})
        },
    )


def _aplicar_nombres(
    categoria: EventCategory, nombre: str | None, nombres: Mapping[Any, str] | None
) -> None:
    """Fija el nombre y sus traducciones llevando la cuenta de quién escribió cada
    idioma: lo que llega distinto de lo guardado es del superadmin (`manual`); lo
    que no cambia conserva su origen. Si cambia el nombre original, los idiomas
    que puso la IA se quitan para que los rehaga. Un idioma vacío lo rellena la IA."""
    anteriores = dict(categoria.name_i18n or {})
    origenes = dict(categoria.name_i18n_origin or {})
    renombrada = nombre is not None and nombre != categoria.name
    if nombre is not None:
        categoria.name = nombre
    nuevos = _traducciones(nombres) if nombres is not None else dict(anteriores)
    resultado: dict[str, str] = {}
    origen_resultado: dict[str, str] = {}
    for locale, texto in nuevos.items():
        if texto == anteriores.get(locale):
            origen = origenes.get(locale, "manual")
            if renombrada and origen == "ia":
                continue
        else:
            origen = "manual"
        resultado[locale] = texto
        origen_resultado[locale] = origen
    categoria.name_i18n = resultado
    categoria.name_i18n_origin = origen_resultado


async def _traducir_contenido_de_plataforma() -> None:
    from app.core.tasks import traducir_contenido_de_plataforma_task

    await traducir_contenido_de_plataforma_task.kiq()


def _traducciones(valor: Mapping[Any, str] | None) -> dict[Locale, str]:
    """Solo idiomas del catálogo y sin textos vacíos."""
    return {
        locale: texto.strip()
        for locale, texto in (valor or {}).items()
        if locale in LOCALES and texto and texto.strip()
    }


@router.get(
    "",
    summary="Listar el catálogo de categorías de eventos",
    response_model=list[EventCategoryOut],
)
async def list_event_categories(_: Superadmin, session: MaintenanceDb) -> list[EventCategoryOut]:
    return [_out(c) for c in await categories.list_categories(session)]


@router.post(
    "",
    summary="Crear una categoría de eventos",
    status_code=status.HTTP_201_CREATED,
    response_model=EventCategoryOut,
)
async def create_event_category(
    datos: EventCategoryCreate, superadmin: Superadmin, session: MaintenanceDb
) -> EventCategoryOut:
    if await categories.get_category_by_slug(session, datos.slug) is not None:
        raise ConflictError(
            "Ya existe una categoría con el identificador «{slug}».", params={"slug": datos.slug}
        )
    categoria = EventCategory(
        id=new_uuid7(),
        slug=datos.slug,
        name=datos.name,
        display_order=datos.display_order,
        is_active=datos.is_active,
    )
    categoria.name_i18n = {}
    categoria.name_i18n_origin = {}
    _aplicar_nombres(categoria, None, datos.name_i18n)
    session.add(categoria)
    try:
        await session.flush()
    except IntegrityError as exc:
        # Dos superadmins creando el mismo identificador a la vez.
        raise ConflictError(
            "Ya existe una categoría con el identificador «{slug}».", params={"slug": datos.slug}
        ) from exc
    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=None,
        action="event_category.created",
        entity_type="event_category",
        entity_id=str(categoria.id),
        detail={"slug": categoria.slug, "is_active": categoria.is_active},
    )
    encolar_tras_commit(session, _traducir_contenido_de_plataforma)
    return _out(categoria)


@router.patch(
    "/{category_id}",
    summary="Editar una categoría de eventos",
    description=(
        "Edita `name`, `display_order` e `is_active`. El identificador no cambia y no "
        "hay borrado: se desactiva. Desactivar una categoría no toca los eventos que "
        "ya la tienen, pero deja de poder asignarse y de mostrarse en público."
    ),
    response_model=EventCategoryOut,
)
async def update_event_category(
    category_id: uuid.UUID,
    datos: EventCategoryUpdate,
    superadmin: Superadmin,
    session: MaintenanceDb,
) -> EventCategoryOut:
    categoria = await categories.get_category(session, category_id)
    if categoria is None:
        raise NotFoundError("La categoría no existe.")
    cambios = datos.model_dump(exclude_unset=True)
    nombre = cambios.pop("name", None)
    nombres = cambios.pop("name_i18n", None)
    if nombre is not None or nombres is not None:
        _aplicar_nombres(categoria, nombre, nombres)
        encolar_tras_commit(session, _traducir_contenido_de_plataforma)
    for campo, valor in cambios.items():
        if valor is not None:
            setattr(categoria, campo, valor)
    await session.flush()
    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=None,
        action="event_category.updated",
        entity_type="event_category",
        entity_id=str(categoria.id),
        detail={"slug": categoria.slug, "is_active": categoria.is_active},
    )
    return _out(categoria)
