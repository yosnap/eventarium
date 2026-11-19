"""Herramientas MCP de los sitios cercanos a un evento (alojamiento,
restaurantes, parking…). Mismo patrón que las sedes: el esquema valida, el
evento debe estar permitido para la conexión y toda escritura se audita."""

from __future__ import annotations

from mcp.server import MCPServer

from app.modules.mcp import schemas
from app.modules.mcp.contexto import sesion
from app.modules.mcp.herramientas_escritura import (
    DELICADA,
    ESCRITURA,
    _auditar,
    _sin_nulos,
    _validar,
)
from app.modules.mcp.herramientas_idioma import exigir_idioma_original, idioma_pedido
from app.modules.mcp.herramientas_lectura import (
    LECTURA,
    _evento_permitido,
    _uuid,
    preparar,
    sitio_out,
)
from app.modules.mcp.scopes import Ambito
from app.modules.nearby import service as nearby_service
from app.modules.nearby.schemas import NearbyPlaceCreate


def registrar(mcp: MCPServer) -> None:
    @mcp.tool(annotations=LECTURA)
    async def listar_sitios_cercanos(event_id: str) -> list[schemas.SitioCercano]:
        """Sitios que el organizador señala cerca del evento (alojamiento,
        restaurantes, bares, parking, transporte, farmacias u otros)."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_LEER)
        async with sesion(contexto) as session:
            evento = await _evento_permitido(session, contexto, event_id)
            sitios = await nearby_service.listar(session, contexto.organization_id, evento.id)
            return [sitio_out(sitio) for sitio in sitios]

    @mcp.tool(annotations=ESCRITURA)
    async def anadir_sitio_cercano(
        event_id: str,
        tipo: str,
        nombre: str,
        tipo_libre: str | None = None,
        direccion: str | None = None,
        telefono: str | None = None,
        web: str | None = None,
        nota: str | None = None,
        idioma: str | None = None,
    ) -> schemas.SitioCercano:
        """Añade un sitio cercano al evento. `tipo`: hotel, restaurant, bar,
        parking, transport, pharmacy u other; con other, `tipo_libre` es su
        nombre (p. ej. «Gimnasio»). `web` con http(s)://; hasta 50 por evento.
        `idioma`: el de `nombre` y `nota`; tiene que ser el original del evento."""
        locale = idioma_pedido(idioma)
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_EDITAR)
        datos = _validar(
            NearbyPlaceCreate,
            _sin_nulos(
                kind=tipo,
                custom_kind=tipo_libre,
                name=nombre,
                address=direccion,
                phone=telefono,
                website=web,
                notes=nota,
            ),
        ).model_dump()
        async with sesion(contexto) as session:
            evento = await _evento_permitido(session, contexto, event_id)
            exigir_idioma_original(locale, evento)
            sitio = await nearby_service.crear(
                session, organization_id=contexto.organization_id, event_id=evento.id, datos=datos
            )
            respuesta = sitio_out(sitio)
        await _auditar(
            contexto,
            "anadir_sitio_cercano",
            "event_nearby_place",
            respuesta.id,
            {"event_id": event_id},
        )
        return respuesta

    @mcp.tool(annotations=DELICADA)
    async def quitar_sitio_cercano(event_id: str, sitio_id: str) -> str:
        """Quita un sitio cercano del evento indicado."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_EDITAR)
        async with sesion(contexto) as session:
            evento = await _evento_permitido(session, contexto, event_id)
            await nearby_service.borrar(
                session,
                organization_id=contexto.organization_id,
                event_id=evento.id,
                place_id=_uuid(sitio_id),
            )
        await _auditar(
            contexto, "quitar_sitio_cercano", "event_nearby_place", sitio_id, {"event_id": event_id}
        )
        return "Sitio quitado."
