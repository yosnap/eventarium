"""Métricas del escritorio de un evento.

Un solo endpoint de lectura que junta lo que el organizador necesita para saber
cómo va su evento, en vez de obligar a la pantalla a llamar a seis módulos y
cuadrar las cifras por su cuenta.

Va montado en `/events/{event_id}/metrics`, junto al resto de rutas de evento:
la organización se resuelve del token (`usuario.organization_id`), nunca de la
URL, y el acceso al evento pasa por el mismo `get_event` que las demás — quien
no sea miembro de la organización no lo encuentra, y la respuesta es 404.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, DbDep, get_user_permissions
from app.modules.events import repository as events_repository
from app.modules.events.models import Event
from app.modules.metrics import service
from app.modules.metrics.schemas import MetricasDelEventoOut
from app.shared.errors import NotFoundError

router = APIRouter(prefix="/events/{event_id}", tags=["métricas"])


async def _obtener_evento_o_404(usuario: CurrentUserDep, session: DbDep, event_id: str) -> Event:
    evento = await events_repository.get_event(
        session, usuario.organization_id, uuid.UUID(event_id)
    )
    if evento is None:
        raise NotFoundError("El evento no existe.")
    return evento


@router.get(
    "/metrics",
    summary="Métricas del evento para su escritorio",
    description=(
        "Compone en una llamada el embudo, la ocupación, las cifras de "
        "inscripción y el estado de las piezas del evento. Los bloques para los "
        "que quien pide no tiene permiso **se omiten**, no se esconden en la "
        "interfaz: el escritorio junta recursos con permisos propios y no todos "
        "los miembros pueden verlos todos."
    ),
    response_model=MetricasDelEventoOut,
)
async def get_event_metrics(
    evento: Annotated[Event, Depends(_obtener_evento_o_404)],
    usuario: CurrentUserDep,
    session: DbDep,
) -> MetricasDelEventoOut:
    permisos = await get_user_permissions(session, usuario)
    return await service.metricas_del_evento(session, evento, permisos)
