"""Herramientas de solo lectura del MCP.

Todas empiezan con `preparar()` (contexto + límite por conexión) y pasan por
`exigir_ambito`/`exigir_evento` antes de leer nada. Leen con los mismos
repositorios que la web, bajo el RLS de la organización de la conexión.
"""

from __future__ import annotations

import uuid

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from sqlalchemy import select

from app.core.config import get_settings
from app.core.ratelimit import TooManyRequestsError, consumir_por_conexion_mcp
from app.modules.events import repository as events_repository
from app.modules.events.models import Event
from app.modules.mcp import schemas
from app.modules.mcp.contexto import ContextoMcp, ErrorDeHerramienta, contexto_actual, sesion
from app.modules.mcp.scopes import Ambito
from app.modules.registrations import repository as registrations_repository
from app.modules.sponsors import repository as sponsors_repository
from app.modules.sponsors.models import SponsorTier

LECTURA = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
LIMITE_LISTADO = 50


async def preparar() -> ContextoMcp:
    """Primer paso de toda herramienta: contexto de la conexión y límite."""
    contexto = contexto_actual()
    try:
        await consumir_por_conexion_mcp(str(contexto.connection_id))
    except TooManyRequestsError as exc:
        raise ErrorDeHerramienta(
            "Demasiadas llamadas seguidas desde esta conexión. Espera un minuto."
        ) from exc
    return contexto


def _uuid(valor: str) -> uuid.UUID:
    try:
        return uuid.UUID(valor)
    except ValueError as exc:
        raise ErrorDeHerramienta("El evento no existe.") from exc


def _resumen(evento: Event) -> schemas.EventoResumen:
    base = get_settings().web_base_url.rstrip("/")
    return schemas.EventoResumen(
        id=str(evento.id),
        slug=evento.slug,
        titulo=evento.title,
        estado=evento.status,
        visibilidad=evento.visibility,
        inicio=evento.starts_at,
        fin=evento.ends_at,
        formato=evento.location_mode,
        lugar=evento.location_name,
        ciudad=evento.city,
        aforo=evento.capacity,
        modo_inscripcion=evento.registration_mode,
        enlace_panel=f"{base}/dashboard/events/{evento.id}",
    )


async def _evento_permitido(session, contexto: ContextoMcp, event_id: str) -> Event:  # type: ignore[no-untyped-def]
    identificador = _uuid(event_id)
    contexto.exigir_evento(identificador)
    evento = await events_repository.get_event(session, contexto.organization_id, identificador)
    if evento is None:
        raise ErrorDeHerramienta("El evento no existe.")
    return evento


def registrar(mcp: MCPServer) -> None:
    @mcp.tool(annotations=LECTURA)
    async def listar_eventos(estado: str | None = None) -> list[schemas.EventoResumen]:
        """Lista los eventos de la organización a los que tiene acceso esta
        conexión, del más reciente al más antiguo. `estado` filtra por
        draft, published, archived o cancelled."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_LEER)
        async with sesion(contexto) as session:
            consulta = events_repository.events_query(contexto.organization_id, status=estado)
            if contexto.event_ids is not None:
                consulta = consulta.where(Event.id.in_(contexto.event_ids))
            eventos = list(await session.scalars(consulta.limit(LIMITE_LISTADO)))
            return [_resumen(evento) for evento in eventos]

    @mcp.tool(annotations=LECTURA)
    async def ver_evento(event_id: str) -> schemas.EventoDetalle:
        """Detalle de un evento: datos, sedes, agenda y patrocinadores (sin
        importes). Para inscripciones usa `cifras_de_inscripcion`."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_LEER)
        async with sesion(contexto) as session:
            evento = await _evento_permitido(session, contexto, event_id)
            sedes = list(
                await session.scalars(
                    events_repository.venues_query(contexto.organization_id, evento.id)
                )
            )
            sesiones = list(
                await session.scalars(
                    events_repository.sessions_query(contexto.organization_id, evento.id)
                )
            )
            patrocinadores = list(
                await session.scalars(
                    sponsors_repository.sponsors_query(contexto.organization_id, evento.id)
                )
            )
            niveles = {
                nivel.id: nivel.name
                for nivel in await session.scalars(
                    select(SponsorTier).where(
                        SponsorTier.organization_id == contexto.organization_id
                    )
                )
            }
            base = get_settings().web_base_url.rstrip("/")
            return schemas.EventoDetalle(
                **_resumen(evento).model_dump(),
                resumen=evento.summary,
                descripcion=evento.description,
                zona_horaria=evento.timezone,
                enlace_publico=f"{base}/eventos/{evento.slug}",
                motivo_cancelacion=evento.cancellation_reason,
                sedes=[
                    schemas.Sede(id=str(s.id), nombre=s.name, direccion=s.address) for s in sedes
                ],
                sesiones=[
                    schemas.Sesion(
                        id=str(s.id),
                        titulo=s.title,
                        tipo=s.session_type,
                        inicio=s.starts_at,
                        fin=s.ends_at,
                        sala=s.room,
                        sede_id=str(s.venue_id) if s.venue_id else None,
                    )
                    for s in sesiones
                ],
                patrocinadores=[
                    schemas.Patrocinador(
                        id=str(p.id),
                        nombre=p.name,
                        nivel=niveles.get(p.tier_id),
                        web=p.website,
                        tipo_aportacion=p.contribution_type,
                    )
                    for p in patrocinadores
                ],
            )

    @mcp.tool(annotations=LECTURA)
    async def cifras_de_inscripcion(event_id: str) -> schemas.CifrasDeInscripcion:
        """Cuántas inscripciones tiene un evento en cada estado y cuántas
        plazas quedan. Nunca devuelve datos de las personas inscritas."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.INSCRIPCIONES_CIFRAS)
        async with sesion(contexto) as session:
            evento = await _evento_permitido(session, contexto, event_id)
            por_estado = await registrations_repository.count_registrations_by_status(
                session, contexto.organization_id, evento.id
            )
            reservadas = await registrations_repository.count_reserved_registrations(
                session, contexto.organization_id, evento.id
            )
            return schemas.CifrasDeInscripcion(
                evento_id=str(evento.id),
                confirmadas=por_estado.get("confirmed", 0),
                pendientes_de_aprobar=por_estado.get("pending_approval", 0),
                pendientes_de_verificar=por_estado.get("pending_verification", 0),
                pendientes_de_pago=por_estado.get("pending_payment", 0),
                en_lista_de_espera=por_estado.get("waitlisted", 0),
                canceladas=por_estado.get("cancelled", 0),
                rechazadas=por_estado.get("rejected", 0),
                plazas_reservadas=reservadas,
                aforo=evento.capacity,
                plazas_libres=(
                    max(evento.capacity - reservadas, 0) if evento.capacity is not None else None
                ),
            )
