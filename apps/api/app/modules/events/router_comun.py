"""Dependencias compartidas por los routers de eventos de la organización actual."""

from __future__ import annotations

import uuid

from app.core.deps import CurrentUserDep, DbDep
from app.modules.events import repository
from app.modules.events.models import Event
from app.shared.errors import NotFoundError


async def obtener_evento_o_404(session: DbDep, usuario: CurrentUserDep, event_id: str) -> Event:
    try:
        id_evento = uuid.UUID(event_id)
    except ValueError as exc:
        # Un enlace mal copiado (p. ej. a la vista previa) no es un error del servidor.
        raise NotFoundError("El evento no existe.") from exc
    evento = await repository.get_event(session, usuario.organization_id, id_evento)
    if evento is None:
        raise NotFoundError("El evento no existe.")
    return evento
