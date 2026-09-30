"""Categorías activas, para el selector del formulario de evento (panel)."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import DbDep, require_permission
from app.core.permissions import Permission
from app.modules.events import categories
from app.modules.events.schemas import EventCategoryOut

router = APIRouter(prefix="/event-categories", tags=["eventos"])


@router.get(
    "",
    summary="Categorías que se pueden asignar a un evento",
    description=(
        "Solo las activas. El panel añade además la categoría actual del evento aunque "
        "esté desactivada (viene en el propio evento)."
    ),
    response_model=list[EventCategoryOut],
    dependencies=[require_permission(Permission.EVENTS_READ)],
)
async def list_assignable_categories(session: DbDep) -> list[EventCategoryOut]:
    return [
        EventCategoryOut(
            id=str(c.id),
            slug=c.slug,
            name=c.name,
            display_order=c.display_order,
            is_active=c.is_active,
        )
        for c in await categories.list_categories(session, solo_activas=True)
    ]
