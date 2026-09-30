"""Catálogo de categorías de eventos: lo gestiona la superadministración.

Mismo patrón que `theme_templates`: tabla de instalación, `app_user` solo
lee; aquí se escribe con la sesión de mantenimiento y `require_superadmin`. No
hay borrado: una categoría en uso se desactiva (`is_active`), y los eventos que
ya la tienen la conservan.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.deps import SCOPE_SESION, CurrentUser, get_maintenance_db, require_superadmin
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
    )


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
        raise ConflictError(f"Ya existe una categoría con el identificador «{datos.slug}».")
    categoria = EventCategory(
        id=new_uuid7(),
        slug=datos.slug,
        name=datos.name,
        display_order=datos.display_order,
        is_active=datos.is_active,
    )
    session.add(categoria)
    await session.flush()
    await registrar_auditoria(
        session,
        actor_user_id=superadmin.id,
        organization_id=None,
        action="event_category.created",
        entity_type="event_category",
        entity_id=str(categoria.id),
        detail={"slug": categoria.slug, "is_active": categoria.is_active},
    )
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
    for campo, valor in datos.model_dump(exclude_unset=True).items():
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
