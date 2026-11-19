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
from app.core.locale import normalizar_locale
from app.core.ratelimit import TooManyRequestsError, consumir_por_conexion_mcp
from app.modules.events import categories as events_categories
from app.modules.events import repository as events_repository
from app.modules.events import session_types
from app.modules.events.models import Event
from app.modules.mcp import schemas
from app.modules.mcp.contexto import ContextoMcp, ErrorDeHerramienta, contexto_actual, sesion
from app.modules.mcp.herramientas_idioma import idioma_pedido
from app.modules.mcp.scopes import Ambito
from app.modules.nearby import service as nearby_service
from app.modules.nearby.models import EventNearbyPlace
from app.modules.organizations import service as organizations_service
from app.modules.registrations import repository as registrations_repository
from app.modules.sponsors import repository as sponsors_repository
from app.modules.sponsors.models import SponsorTier
from app.modules.translations.campos import TipoDeEntidad
from app.modules.translations.service import (
    Traductor,
    traductor_de_evento,
    traductores_de_listado,
)

LECTURA = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
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


def _resumen(evento: Event, traductor: Traductor | None = None) -> schemas.EventoResumen:
    """Resumen del evento; con `traductor`, el título y el lugar en su idioma."""
    base = get_settings().web_base_url.rstrip("/")
    titulo, lugar = evento.title, evento.location_name
    if traductor is not None:
        titulo = traductor.campo("event", evento.id, "title", titulo, principal=True) or titulo
        lugar = traductor.campo("event", evento.id, "location_name", lugar)
    return schemas.EventoResumen(
        id=str(evento.id),
        slug=evento.slug,
        titulo=titulo,
        estado=evento.status,
        visibilidad=evento.visibility,
        inicio=evento.starts_at,
        fin=evento.ends_at,
        formato=evento.location_mode,
        lugar=lugar,
        ciudad=evento.city,
        aforo=evento.capacity,
        modo_inscripcion=evento.registration_mode,
        categoria=evento.category.slug if evento.category else None,
        etiquetas=list(evento.tags),
        enlace_panel=f"{base}/dashboard/events/{evento.id}",
        idioma_original=normalizar_locale(evento.source_locale),
        idioma_servido=traductor.idioma_servido if traductor is not None else None,
    )


async def _evento_permitido(session, contexto: ContextoMcp, event_id: str) -> Event:  # type: ignore[no-untyped-def]
    identificador = _uuid(event_id)
    contexto.exigir_evento(identificador)
    evento = await events_repository.get_event(session, contexto.organization_id, identificador)
    if evento is None:
        raise ErrorDeHerramienta("El evento no existe.")
    return evento


def _etiquetas_de_filtro(etiquetas: list[str] | None) -> tuple[str, ...]:
    if not etiquetas:
        return ()
    if len(etiquetas) > events_categories.MAX_ETIQUETAS_EN_UN_FILTRO:
        raise ErrorDeHerramienta(
            f"Se puede filtrar por {events_categories.MAX_ETIQUETAS_EN_UN_FILTRO} etiquetas "
            "como máximo."
        )
    try:
        return tuple(events_categories.normalizar_etiquetas(etiquetas))
    except ValueError as exc:
        raise ErrorDeHerramienta(str(exc)) from exc


def sitio_out(sitio: EventNearbyPlace) -> schemas.SitioCercano:
    return schemas.SitioCercano(
        id=str(sitio.id),
        tipo=sitio.kind,
        tipo_libre=sitio.custom_kind,
        nombre=sitio.name,
        direccion=sitio.address,
        telefono=sitio.phone,
        web=sitio.website,
        nota=sitio.notes,
    )


def registrar(mcp: MCPServer) -> None:
    @mcp.tool(annotations=LECTURA)
    async def listar_eventos(
        estado: str | None = None,
        categoria: str | None = None,
        etiquetas: list[str] | None = None,
        idioma: str | None = None,
    ) -> list[schemas.EventoResumen]:
        """Lista los eventos de la organización a los que tiene acceso esta
        conexión, del más reciente al más antiguo. `estado` filtra por
        draft, published, archived o cancelled; `categoria`, por el slug de una
        categoría (ver `listar_categorias`); `etiquetas`, por hasta 3 etiquetas
        que el evento debe tener todas. `idioma` (es-ES, en-US): devuelve los
        títulos traducidos si lo están; si no, en su idioma original."""
        locale = idioma_pedido(idioma)
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_LEER)
        filtro_etiquetas = _etiquetas_de_filtro(etiquetas)
        async with sesion(contexto) as session:
            if categoria:
                existente = await events_categories.get_category_by_slug(session, categoria)
                if existente is None or not existente.is_active:
                    raise ErrorDeHerramienta(
                        f"La categoría «{categoria}» no existe o está desactivada. "
                        "Consulta `listar_categorias`."
                    )
            consulta = events_repository.filtrar_por_categoria_y_etiquetas(
                events_repository.events_query(contexto.organization_id, status=estado),
                categoria or None,
                filtro_etiquetas,
            )
            if contexto.event_ids is not None:
                consulta = consulta.where(Event.id.in_(contexto.event_ids))
            eventos = list(await session.scalars(consulta.limit(LIMITE_LISTADO)))
            traductores = await traductores_de_listado(session, eventos, locale) if locale else {}
            return [_resumen(evento, traductores.get(evento.id)) for evento in eventos]

    @mcp.tool(annotations=LECTURA)
    async def listar_tipos_de_sesion() -> list[schemas.TipoDeSesion]:
        """Tipos de sesión activos de la organización (Charla, Taller, Mesa
        redonda…), para usar su nombre como `tipo` al añadir o editar sesiones.
        Las pausas (descanso, comida…) no piden ponentes."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_LEER)
        async with sesion(contexto) as session:
            filas = await session_types.listar(session, contexto.organization_id, solo_activos=True)
            return [
                schemas.TipoDeSesion(
                    id=str(tipo.id),
                    nombre=tipo.name,
                    descripcion=tipo.description,
                    es_pausa=tipo.is_break,
                    clave_base=tipo.base_key,
                )
                for tipo, _ in filas
            ]

    @mcp.tool(annotations=LECTURA)
    async def listar_categorias() -> list[schemas.Categoria]:
        """Categorías activas del catálogo de la plataforma, para usar su
        `slug` como `categoria` al crear o editar un evento o al filtrar."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_LEER)
        async with sesion(contexto) as session:
            activas = await events_categories.list_categories(session, solo_activas=True)
            return [schemas.Categoria(slug=c.slug, nombre=c.name) for c in activas]

    @mcp.tool(annotations=LECTURA)
    async def ver_evento(event_id: str, idioma: str | None = None) -> schemas.EventoDetalle:
        """Detalle de un evento: datos, sedes, agenda y patrocinadores (sin
        importes). Para inscripciones usa `cifras_de_inscripcion`. `idioma`
        (es-ES, en-US): devuelve cada texto traducido si su traducción está al
        día; si no, el original (`textos_sin_traducir` dice cuántos)."""
        locale = idioma_pedido(idioma)
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
            organizacion = await organizations_service.public_ref(session, contexto.organization_id)
            traductor = await traductor_de_evento(session, evento, locale) if locale else None

            def texto(
                tipo: TipoDeEntidad, entity_id: uuid.UUID, campo: str, valor: str | None
            ) -> str | None:
                if traductor is None:
                    return valor
                return traductor.campo(tipo, entity_id, campo, valor, principal=tipo == "event")

            sitios = await nearby_service.listar(session, contexto.organization_id, evento.id)
            detalle = schemas.EventoDetalle(
                **_resumen(evento, traductor).model_dump(),
                resumen=texto("event", evento.id, "summary", evento.summary),
                descripcion=texto("event", evento.id, "description", evento.description),
                zona_horaria=evento.timezone,
                enlace_publico=(
                    f"{base}/{organizacion.slug}/{evento.slug}"
                    if evento.visibility != "private"
                    else None
                ),
                motivo_cancelacion=texto(
                    "event", evento.id, "cancellation_reason", evento.cancellation_reason
                ),
                recordatorio=evento.reminder_enabled,
                recordatorio_horas=evento.reminder_hours_before,
                sitios_cercanos=[
                    sitio_out(sitio).model_copy(
                        update={
                            "nombre": texto("nearby_place", sitio.id, "name", sitio.name),
                            "nota": texto("nearby_place", sitio.id, "notes", sitio.notes),
                        }
                    )
                    for sitio in sitios
                ],
                sedes=[
                    schemas.Sede(
                        id=str(s.id),
                        nombre=texto("venue", s.id, "name", s.name) or s.name,
                        direccion=s.address,
                    )
                    for s in sedes
                ],
                sesiones=[
                    schemas.Sesion(
                        id=str(s.id),
                        titulo=texto("session", s.id, "title", s.title) or s.title,
                        tipo=s.tipo.name,
                        inicio=s.starts_at,
                        fin=s.ends_at,
                        sala=texto("session", s.id, "room", s.room),
                        sede_id=str(s.venue_id) if s.venue_id else None,
                    )
                    for s in sesiones
                ],
                patrocinadores=[
                    schemas.Patrocinador(
                        id=str(p.id),
                        nombre=texto("sponsor", p.id, "name", p.name) or p.name,
                        nivel=niveles.get(p.tier_id),
                        web=p.website,
                        tipo_aportacion=p.contribution_type,
                    )
                    for p in patrocinadores
                ],
            )
            if traductor is not None:
                detalle.idioma_servido = traductor.idioma_servido
                detalle.idiomas_al_dia = list(traductor.idiomas_al_dia)
                detalle.textos_sin_traducir = traductor.campos_pendientes
            return detalle

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
