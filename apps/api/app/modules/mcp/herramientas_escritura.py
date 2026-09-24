"""Herramientas de escritura del MCP: preparar eventos, publicarlos y cancelarlos.

Reglas que cumplen todas:

- Empiezan con `preparar()` y exigen su ámbito y, si tocan un evento, que
  esté entre los permitidos de la conexión (`exigir_evento`). Las de agenda,
  sedes y patrocinadores reciben siempre `event_id` y comprueban que el
  sub-recurso pertenece a ese evento (lo garantizan los servicios, que
  buscan por `event_id`).
- Validan con los mismos schemas y servicios que la web: ninguna se salta una
  regla del panel.
- `crear_evento` deja el evento **siempre en borrador**, y `editar_evento` no
  acepta `status`: publicar, despublicar y cancelar son herramientas aparte,
  con su propio ámbito.
- Cada escritura queda en la auditoría con `via = "mcp"` y la conexión.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.audit import registrar_auditoria
from app.core.config import get_settings
from app.core.database import maintenance_session
from app.core.permissions import Permission
from app.modules.events import cancelacion
from app.modules.events import service as events_service
from app.modules.events.schemas import (
    EventCreate,
    EventSessionCreate,
    EventSessionUpdate,
    EventUpdate,
    EventVenueCreate,
)
from app.modules.mcp import schemas
from app.modules.mcp.contexto import ContextoMcp, ErrorDeHerramienta, sesion
from app.modules.mcp.herramientas_lectura import _evento_permitido, _resumen, _uuid, preparar
from app.modules.mcp.scopes import Ambito
from app.modules.registrations.models import EventRegistration
from app.modules.sponsors import service as sponsors_service
from app.modules.sponsors.models import SponsorTier
from app.modules.sponsors.schemas import SponsorCreate, SponsorUpdate

ESCRITURA = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
DELICADA = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False
)
ACCIONES_DE_LA_WEB = {"cancelar_evento": "events.cancelled"}
logger = logging.getLogger(__name__)
LECTURA_NIVELES = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, open_world_hint=False
)
# Vida del código de confirmación de `cancelar_evento`, en ventanas de 5 min:
# vale la ventana actual y la anterior (entre 5 y 10 minutos).
_VENTANA_CONFIRMACION = 300


def _validar(modelo: type, datos: dict[str, Any]) -> Any:
    try:
        return modelo(**datos)
    except ValidationError as exc:
        errores = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise ErrorDeHerramienta(f"Datos no válidos: {errores}") from exc


async def _auditar(
    contexto: ContextoMcp, herramienta: str, entidad: str, entidad_id: str, detalle: dict[str, Any]
) -> None:
    """Tras el `commit` de la escritura (`audit_log` solo lo escribe
    `app_maintainer`, `core/audit.py`). Si falla, se registra en el log y la
    herramienta responde igual: la escritura ya está hecha, y devolver un error
    haría que el asistente la repitiera (duplicando una sesión o una sede).
    Mismo criterio que el panel, que audita en una tarea tras la respuesta.

    `action` es el de la web cuando existe (`events.cancelled`); el resto de
    escrituras no se auditan en el panel, y van con `mcp.<herramienta>`.
    `detail.via = "mcp"` distingue siempre el origen.
    """
    try:
        async with maintenance_session() as auditoria:
            await registrar_auditoria(
                auditoria,
                actor_user_id=contexto.user_id,
                organization_id=contexto.organization_id,
                action=ACCIONES_DE_LA_WEB.get(herramienta, f"mcp.{herramienta}"),
                entity_type=entidad,
                entity_id=entidad_id,
                detail={"via": "mcp", "connection_id": str(contexto.connection_id), **detalle},
            )
    except Exception:
        logger.exception(
            "No se pudo auditar %s de la conexión %s", herramienta, contexto.connection_id
        )


def _sin_nulos(**campos: Any) -> dict[str, Any]:
    return {clave: valor for clave, valor in campos.items() if valor is not None}


def _codigo_de_cancelacion(
    contexto: ContextoMcp,
    event_id: uuid.UUID,
    resumen: cancelacion.ResumenCancelacion,
    ventana: int,
) -> str:
    """Sin estado: el código ata la conexión, el evento, las cifras que se han
    enseñado y una ventana de tiempo. Si cambian las cifras, deja de valer."""
    # Etiqueta de propósito: la clave (`jwt_secret`) también firma otras cosas.
    mensaje = (
        f"mcp:cancelar_evento:v1:{contexto.connection_id}:{event_id}:"
        f"{resumen.inscripciones_afectadas}:{resumen.importe_a_reembolsar_cents}:{ventana}"
    ).encode()
    return hmac.new(get_settings().jwt_secret.encode(), mensaje, hashlib.sha256).hexdigest()[:16]


_FORMATO_CODIGO = re.compile(r"[0-9a-f]{16}")


def _enlace_panel(event_id: uuid.UUID | str, seccion: str = "") -> str:
    base = get_settings().web_base_url.rstrip("/")
    return f"{base}/dashboard/events/{event_id}{seccion}"


def _sesion_out(sesion_agenda: Any) -> schemas.Sesion:  # noqa: ANN401 - EventSession
    return schemas.Sesion(
        id=str(sesion_agenda.id),
        titulo=sesion_agenda.title,
        tipo=sesion_agenda.session_type,
        inicio=sesion_agenda.starts_at,
        fin=sesion_agenda.ends_at,
        sala=sesion_agenda.room,
        sede_id=str(sesion_agenda.venue_id) if sesion_agenda.venue_id else None,
        enlace_panel=_enlace_panel(sesion_agenda.event_id, "/agenda"),
    )


def registrar(mcp: MCPServer) -> None:
    @mcp.tool(annotations=ESCRITURA)
    async def crear_evento(
        slug: str,
        titulo: str,
        inicio: datetime,
        fin: datetime,
        formato: str = "in_person",
        lugar: str | None = None,
        direccion: str | None = None,
        ciudad: str | None = None,
        url_online: str | None = None,
        aforo: int | None = None,
        modo_inscripcion: str = "free",
        resumen: str | None = None,
        descripcion: str | None = None,
        zona_horaria: str = "Europe/Madrid",
    ) -> schemas.EventoResumen:
        """Crea un evento **en borrador**. La persona lo revisa y lo publica
        desde Eventarium (o con `publicar_evento`, si la conexión lo permite).
        `formato`: in_person, online o hybrid. `modo_inscripcion`: free,
        approval o paid."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_EDITAR)
        if contexto.event_ids is not None:
            raise ErrorDeHerramienta(
                "Esta conexión está limitada a eventos concretos y no puede crear otros."
            )
        datos = _validar(
            EventCreate,
            _sin_nulos(
                slug=slug,
                title=titulo,
                starts_at=inicio,
                ends_at=fin,
                location_mode=formato,
                location_name=lugar,
                location_address=direccion,
                city=ciudad,
                online_url=url_online,
                capacity=aforo,
                registration_mode=modo_inscripcion,
                summary=resumen,
                description=descripcion,
                timezone=zona_horaria,
            ),
        ).model_dump(exclude_unset=True)
        datos["status"] = "draft"
        async with sesion(contexto) as session:
            evento = await events_service.create_event(
                session, organization_id=contexto.organization_id, datos=datos
            )
            respuesta = _resumen(evento)
        await _auditar(contexto, "crear_evento", "event", respuesta.id, {"slug": slug})
        return respuesta

    @mcp.tool(annotations=ESCRITURA)
    async def editar_evento(
        event_id: str,
        titulo: str | None = None,
        inicio: datetime | None = None,
        fin: datetime | None = None,
        formato: str | None = None,
        lugar: str | None = None,
        direccion: str | None = None,
        ciudad: str | None = None,
        url_online: str | None = None,
        aforo: int | None = None,
        modo_inscripcion: str | None = None,
        visibilidad: str | None = None,
        resumen: str | None = None,
        descripcion: str | None = None,
    ) -> schemas.EventoResumen:
        """Cambia los datos de un evento. No cambia su estado: para eso están
        `publicar_evento`, `despublicar_evento` y `cancelar_evento`."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_EDITAR)
        cambios = _sin_nulos(
            title=titulo,
            starts_at=inicio,
            ends_at=fin,
            location_mode=formato,
            location_name=lugar,
            location_address=direccion,
            city=ciudad,
            online_url=url_online,
            capacity=aforo,
            registration_mode=modo_inscripcion,
            visibility=visibilidad,
            summary=resumen,
            description=descripcion,
        )
        if not cambios:
            raise ErrorDeHerramienta("Indica al menos un dato que cambiar.")
        datos = _validar(EventUpdate, cambios).model_dump(exclude_unset=True)
        async with sesion(contexto) as session:
            evento = await _evento_permitido(session, contexto, event_id)
            evento = await events_service.update_event(
                session, organization_id=contexto.organization_id, event_id=evento.id, datos=datos
            )
            respuesta = _resumen(evento)
        await _auditar(contexto, "editar_evento", "event", respuesta.id, {"campos": sorted(datos)})
        return respuesta

    @mcp.tool(annotations=ESCRITURA)
    async def anadir_sesion(
        event_id: str,
        titulo: str,
        inicio: datetime,
        fin: datetime,
        tipo: str = "talk",
        sala: str | None = None,
        descripcion: str | None = None,
        sede_id: str | None = None,
    ) -> schemas.Sesion:
        """Añade una sesión a la agenda. `tipo`: talk, break, service u other.
        Debe caer dentro de las fechas del evento."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_EDITAR)
        datos = _validar(
            EventSessionCreate,
            _sin_nulos(
                session_type=tipo,
                title=titulo,
                starts_at=inicio,
                ends_at=fin,
                room=sala,
                description=descripcion,
                venue_id=sede_id,
            ),
        ).model_dump(exclude_unset=True)
        async with sesion(contexto) as session:
            evento = await _evento_permitido(session, contexto, event_id)
            nueva = await events_service.create_session(
                session, organization_id=contexto.organization_id, event_id=evento.id, datos=datos
            )
            respuesta = _sesion_out(nueva)
        await _auditar(
            contexto, "anadir_sesion", "event_session", respuesta.id, {"event_id": event_id}
        )
        return respuesta

    @mcp.tool(annotations=ESCRITURA)
    async def editar_sesion(
        event_id: str,
        session_id: str,
        titulo: str | None = None,
        inicio: datetime | None = None,
        fin: datetime | None = None,
        tipo: str | None = None,
        sala: str | None = None,
        descripcion: str | None = None,
        sede_id: str | None = None,
    ) -> schemas.Sesion:
        """Cambia una sesión de la agenda del evento indicado."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_EDITAR)
        cambios = _sin_nulos(
            session_type=tipo,
            title=titulo,
            starts_at=inicio,
            ends_at=fin,
            room=sala,
            description=descripcion,
            venue_id=sede_id,
        )
        if not cambios:
            raise ErrorDeHerramienta("Indica al menos un dato que cambiar.")
        datos = _validar(EventSessionUpdate, cambios).model_dump(exclude_unset=True)
        async with sesion(contexto) as session:
            evento = await _evento_permitido(session, contexto, event_id)
            cambiada = await events_service.update_session(
                session,
                organization_id=contexto.organization_id,
                event_id=evento.id,
                session_id=_uuid(session_id),
                datos=datos,
            )
            respuesta = _sesion_out(cambiada)
        await _auditar(
            contexto, "editar_sesion", "event_session", respuesta.id, {"event_id": event_id}
        )
        return respuesta

    @mcp.tool(annotations=DELICADA)
    async def quitar_sesion(event_id: str, session_id: str) -> str:
        """Borra una sesión de la agenda del evento indicado."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_EDITAR)
        async with sesion(contexto) as session:
            evento = await _evento_permitido(session, contexto, event_id)
            await events_service.delete_session(
                session,
                organization_id=contexto.organization_id,
                event_id=evento.id,
                session_id=_uuid(session_id),
            )
        await _auditar(
            contexto, "quitar_sesion", "event_session", session_id, {"event_id": event_id}
        )
        return "Sesión borrada."

    @mcp.tool(annotations=ESCRITURA)
    async def anadir_sede(
        event_id: str, nombre: str, direccion: str | None = None, aforo: int | None = None
    ) -> schemas.Sede:
        """Añade una sede a un evento (para eventos con varias sedes)."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_EDITAR)
        datos = _validar(
            EventVenueCreate, _sin_nulos(name=nombre, address=direccion, capacity=aforo)
        ).model_dump(exclude_unset=True)
        async with sesion(contexto) as session:
            evento = await _evento_permitido(session, contexto, event_id)
            sede = await events_service.create_venue(
                session, organization_id=contexto.organization_id, event_id=evento.id, datos=datos
            )
            respuesta = schemas.Sede(
                id=str(sede.id),
                nombre=sede.name,
                direccion=sede.address,
                enlace_panel=_enlace_panel(evento.id, "/sedes"),
            )
        await _auditar(contexto, "anadir_sede", "event_venue", respuesta.id, {"event_id": event_id})
        return respuesta

    @mcp.tool(annotations=LECTURA_NIVELES)
    async def listar_niveles_de_patrocinio() -> list[dict[str, str]]:
        """Niveles de patrocinio de la organización (Oro, Plata…), para usar
        su `id` en `anadir_patrocinador`. Son de la organización, no de un
        evento: una conexión limitada a eventos concretos también los ve (solo
        nombres, nada sensible)."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.PATROCINADORES_EDITAR)
        async with sesion(contexto) as session:
            niveles = await session.scalars(
                select(SponsorTier)
                .where(SponsorTier.organization_id == contexto.organization_id)
                .order_by(SponsorTier.display_order)
            )
            return [{"id": str(n.id), "nombre": n.name} for n in niveles]

    @mcp.tool(annotations=ESCRITURA)
    async def anadir_patrocinador(
        event_id: str,
        nombre: str,
        nivel_id: str,
        tipo_aportacion: str = "en_especie",
        descripcion_aportacion: str | None = None,
        importe: float | None = None,
        web: str | None = None,
    ) -> schemas.Patrocinador:
        """Añade un patrocinador a un evento. `tipo_aportacion`: monetaria
        (con `importe`) o en_especie (con `descripcion_aportacion`). El importe
        nunca se devuelve en ninguna respuesta del MCP."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.PATROCINADORES_EDITAR)
        datos = _validar(
            SponsorCreate,
            _sin_nulos(
                tier_id=nivel_id,
                name=nombre,
                website=web,
                contribution_type=tipo_aportacion,
                contribution_amount=importe,
                contribution_description=descripcion_aportacion,
            ),
        ).model_dump(exclude_unset=True)
        datos["tier_id"] = _uuid(datos["tier_id"])
        async with sesion(contexto) as session:
            evento = await _evento_permitido(session, contexto, event_id)
            patrocinador = await sponsors_service.create_sponsor(
                session, organization_id=contexto.organization_id, event_id=evento.id, datos=datos
            )
            nivel = await session.get(SponsorTier, patrocinador.tier_id)
            respuesta = schemas.Patrocinador(
                id=str(patrocinador.id),
                nombre=patrocinador.name,
                nivel=nivel.name if nivel else None,
                web=patrocinador.website,
                tipo_aportacion=patrocinador.contribution_type,
                enlace_panel=_enlace_panel(evento.id, "/patrocinadores"),
            )
        await _auditar(
            contexto, "anadir_patrocinador", "sponsor", respuesta.id, {"event_id": event_id}
        )
        return respuesta

    @mcp.tool(annotations=ESCRITURA)
    async def editar_patrocinador(
        event_id: str,
        patrocinador_id: str,
        nombre: str | None = None,
        nivel_id: str | None = None,
        tipo_aportacion: str | None = None,
        descripcion_aportacion: str | None = None,
        importe: float | None = None,
        web: str | None = None,
    ) -> schemas.Patrocinador:
        """Cambia un patrocinador del evento indicado."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.PATROCINADORES_EDITAR)
        cambios = _sin_nulos(
            tier_id=nivel_id,
            name=nombre,
            website=web,
            contribution_type=tipo_aportacion,
            contribution_amount=importe,
            contribution_description=descripcion_aportacion,
        )
        if not cambios:
            raise ErrorDeHerramienta("Indica al menos un dato que cambiar.")
        datos = _validar(SponsorUpdate, cambios).model_dump(exclude_unset=True)
        if "tier_id" in datos:
            datos["tier_id"] = _uuid(datos["tier_id"])
        async with sesion(contexto) as session:
            evento = await _evento_permitido(session, contexto, event_id)
            patrocinador = await sponsors_service.update_sponsor(
                session,
                organization_id=contexto.organization_id,
                event_id=evento.id,
                sponsor_id=_uuid(patrocinador_id),
                datos=datos,
            )
            nivel = await session.get(SponsorTier, patrocinador.tier_id)
            respuesta = schemas.Patrocinador(
                id=str(patrocinador.id),
                nombre=patrocinador.name,
                nivel=nivel.name if nivel else None,
                web=patrocinador.website,
                tipo_aportacion=patrocinador.contribution_type,
                enlace_panel=_enlace_panel(evento.id, "/patrocinadores"),
            )
        await _auditar(
            contexto, "editar_patrocinador", "sponsor", respuesta.id, {"event_id": event_id}
        )
        return respuesta

    @mcp.tool(annotations=DELICADA)
    async def publicar_evento(event_id: str) -> schemas.EventoResumen:
        """Publica un evento en borrador: pasa a verse en la web y admite
        inscripciones. Aplica las mismas comprobaciones que el panel."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_PUBLICAR)
        async with sesion(contexto) as session:
            evento = await _evento_permitido(session, contexto, event_id)
            evento = await events_service.update_event(
                session,
                organization_id=contexto.organization_id,
                event_id=evento.id,
                datos={"status": "published"},
            )
            respuesta = _resumen(evento)
        await _auditar(contexto, "publicar_evento", "event", respuesta.id, {})
        return respuesta

    @mcp.tool(annotations=DELICADA)
    async def despublicar_evento(event_id: str) -> schemas.EventoResumen:
        """Vuelve a poner en borrador un evento publicado que todavía no
        tiene inscripciones. Con inscripciones, usa `cancelar_evento`."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_PUBLICAR)
        async with sesion(contexto) as session:
            evento = await _evento_permitido(session, contexto, event_id)
            vivas = await session.scalar(
                select(func.count()).where(
                    EventRegistration.organization_id == contexto.organization_id,
                    EventRegistration.event_id == evento.id,
                    EventRegistration.status.in_(cancelacion.ESTADOS_VIVOS),
                )
            )
            if vivas:
                raise ErrorDeHerramienta(
                    f"El evento tiene {vivas} inscripciones: no se puede despublicar sin "
                    "dejarlas colgadas. Si ya no se celebra, cancélalo."
                )
            evento = await events_service.update_event(
                session,
                organization_id=contexto.organization_id,
                event_id=evento.id,
                datos={"status": "draft"},
            )
            respuesta = _resumen(evento)
        await _auditar(contexto, "despublicar_evento", "event", respuesta.id, {})
        return respuesta

    @mcp.tool(annotations=DELICADA)
    async def cancelar_evento(
        event_id: str, codigo_de_confirmacion: str | None = None, motivo: str | None = None
    ) -> schemas.ConfirmacionDeCancelacion | schemas.CancelacionHecha:
        """Cancela un evento publicado. **Definitivo**: cancela todas las
        inscripciones, reembolsa íntegramente lo cobrado y avisa a cada
        inscrito. Dos pasos: llámala primero sin `codigo_de_confirmacion` para
        ver a cuántas personas afecta y cuánto se reembolsa, confírmalo con la
        persona y vuelve a llamarla con el código devuelto."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_CANCELAR)
        async with sesion(contexto) as session:
            evento = await _evento_permitido(session, contexto, event_id)
            resumen = await cancelacion.resumen_de_cancelacion(
                session, organization_id=contexto.organization_id, event_id=evento.id
            )
            if resumen.pagos_a_reembolsar > 0:
                contexto.exigir_permiso(
                    Permission.PAYMENTS_WRITE,
                    "Cancelar este evento reembolsa pagos: hace falta también el permiso de "
                    "pagos en tu rol.",
                )
            ventana = int(time.time()) // _VENTANA_CONFIRMACION
            if codigo_de_confirmacion is None:
                return schemas.ConfirmacionDeCancelacion(
                    inscripciones_afectadas=resumen.inscripciones_afectadas,
                    pagos_a_reembolsar=resumen.pagos_a_reembolsar,
                    importe_a_reembolsar_cents=resumen.importe_a_reembolsar_cents,
                    moneda=resumen.moneda,
                    codigo_de_confirmacion=_codigo_de_cancelacion(
                        contexto, evento.id, resumen, ventana
                    ),
                    aviso="Confirma con la persona antes de volver a llamar con el código.",
                )
            # `compare_digest` falla con texto no ASCII: se filtra el formato antes.
            if not _FORMATO_CODIGO.fullmatch(codigo_de_confirmacion):
                raise ErrorDeHerramienta("El código no es válido. Vuelve a pedir el resumen.")
            validos = {
                _codigo_de_cancelacion(contexto, evento.id, resumen, v)
                for v in (ventana, ventana - 1)
            }
            if not any(hmac.compare_digest(codigo_de_confirmacion, c) for c in validos):
                raise ErrorDeHerramienta(
                    "El código no es válido: ha caducado o las cifras del evento han cambiado. "
                    "Vuelve a pedir el resumen."
                )
            await cancelacion.cancelar_evento(
                session,
                organization_id=contexto.organization_id,
                event_id=evento.id,
                motivo=motivo,
            )
        # Tras el `commit` de la cancelación, como en el panel.
        from app.core.tasks import sweep_event_cancellation_task

        await sweep_event_cancellation_task.kiq(str(contexto.organization_id), event_id)
        await _auditar(
            contexto,
            "cancelar_evento",
            "event",
            event_id,
            {"inscripciones_afectadas": resumen.inscripciones_afectadas},
        )
        return schemas.CancelacionHecha(
            inscripciones_afectadas=resumen.inscripciones_afectadas,
            pagos_a_reembolsar=resumen.pagos_a_reembolsar,
            enlace_panel=_enlace_panel(evento.id),
        )
