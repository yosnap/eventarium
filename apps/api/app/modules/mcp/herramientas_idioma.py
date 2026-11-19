"""Idioma en el MCP: leer el contenido traducido, escribir traducciones a mano y
lanzar la traducción con IA.

Las herramientas de lectura aceptan `idioma` y devuelven cada texto traducido si
su traducción está al día (si no, el original). Las de escritura aceptan `idioma`
para decir en qué idioma viene el texto: si es el original del evento (o no se
indica), se escribe el original como siempre; si es otro, los textos se guardan
como traducción manual, que la IA ya no toca. Lo que no es texto (fechas, aforo…)
se cambia en el original en cualquier caso.
"""

from __future__ import annotations

import uuid
from typing import Any, Final, Literal

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locale import LOCALES, Locale, buscar_locale, normalizar_locale
from app.modules.events.models import Event
from app.modules.mcp import schemas
from app.modules.mcp.contexto import ContextoMcp, ErrorDeHerramienta, sesion
from app.modules.mcp.scopes import Ambito
from app.modules.organizations.models import Organization
from app.modules.translations import cola, panel
from app.modules.translations.campos import TipoDeEntidad
from app.modules.translations.service import guardar_manual

#: Columnas de texto traducible que escriben las herramientas del MCP.
TEXTOS: Final[dict[TipoDeEntidad, tuple[str, ...]]] = {
    "event": ("title", "summary", "description", "location_name"),
    "session": ("title", "description", "room"),
    "sponsor": ("name", "contribution_description"),
}

TRADUCIR = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)


def idioma_pedido(valor: str | None) -> Locale | None:
    """El idioma de un parámetro `idioma` (`en`, `en-US`…), o `None` si no viene."""
    if valor is None or not valor.strip():
        return None
    locale = buscar_locale(valor)
    if locale is None:
        raise ErrorDeHerramienta(f"Idioma «{valor}» no admitido. Usa uno de: {', '.join(LOCALES)}.")
    return locale


def origen_de(evento: Event) -> Locale:
    """Idioma en que está escrito el original del evento."""
    return normalizar_locale(evento.source_locale)


def separar_textos(
    tipo: TipoDeEntidad, datos: dict[str, Any], idioma: Locale | None, evento: Event
) -> dict[str, str]:
    """Si se escribe en un idioma distinto del original, saca de `datos` los
    textos (que se guardarán como traducción) y deja el resto."""
    if idioma is None or idioma == origen_de(evento):
        return {}
    return {campo: datos.pop(campo) for campo in TEXTOS[tipo] if campo in datos}


def exigir_idioma_original(idioma: Locale | None, evento: Event) -> None:
    """Al crear algo, el texto tiene que estar en el idioma original del evento:
    no hay original del que colgar una traducción."""
    origen = origen_de(evento)
    if idioma is not None and idioma != origen:
        raise ErrorDeHerramienta(
            f"Este evento se escribe en {origen}: crea el contenido en ese idioma y "
            f"tradúcelo después con la herramienta de editar e `idioma={idioma}`."
        )


async def fila_del_evento(
    session: AsyncSession,
    modelo: Any,  # noqa: ANN401 - modelo SQLAlchemy de algo que cuelga de un evento
    evento: Event,
    identificador: str,
    nombre: str,
) -> Any:  # noqa: ANN401
    """Una fila de `modelo` del evento (la RLS ya la limita a la organización)."""
    try:
        fila_id = uuid.UUID(identificador)
    except ValueError as exc:
        raise ErrorDeHerramienta(f"El identificador de {nombre} no es válido.") from exc
    fila = await session.get(modelo, fila_id)
    if fila is None or fila.event_id != evento.id:
        raise ErrorDeHerramienta(f"No existe ese {nombre} en el evento.")
    return fila


async def guardar_traducciones(
    session: AsyncSession,
    contexto: ContextoMcp,
    tipo: TipoDeEntidad,
    fila: Any,  # noqa: ANN401 - fila de cualquier modelo traducible
    textos: dict[str, str],
    idioma: Locale,
) -> None:
    """Guarda `textos` como traducción manual de `fila` en `idioma`."""
    if not textos:
        return
    organizacion = await session.get(Organization, contexto.organization_id)
    if organizacion is None:  # pragma: no cover - la sesión del MCP la garantiza
        raise ErrorDeHerramienta("No existe la organización.")
    entidad = await panel.entidad_de(session, organizacion, tipo, fila)
    for campo, valor in textos.items():
        original = getattr(fila, campo)
        if not original:
            raise ErrorDeHerramienta(
                f"«{campo}» no tiene texto original que traducir: escríbelo primero sin `idioma`."
            )
        await guardar_manual(
            session,
            organization_id=contexto.organization_id,
            event_id=entidad.event_id,
            tipo=tipo,
            entity_id=fila.id,
            campo=campo,
            locale=idioma,
            valor=valor,
            original=original,
            origen_del_contenido=entidad.origen,
            idiomas_activos=entidad.activos,
            user_id=contexto.user_id,
        )


def registrar(mcp: MCPServer) -> None:
    from app.modules.mcp.herramientas_escritura import _auditar
    from app.modules.mcp.herramientas_lectura import _evento_permitido, preparar

    @mcp.tool(annotations=TRADUCIR)
    async def traducir_evento(
        event_id: str, idioma: str, accion: Literal["lanzar", "estado"] = "estado"
    ) -> schemas.EstadoDeTraduccion:
        """Traducción automática de un evento con la IA de la organización (su
        propia clave). `accion="estado"` dice cuántos textos del evento hay que
        traducir a `idioma` y cuántos están al día. `accion="lanzar"` además pone
        el evento en la cola: se traduce poco a poco en uno o dos minutos, dentro
        de los topes de coste. Las traducciones escritas a mano no se tocan."""
        contexto = await preparar()
        contexto.exigir_ambito(Ambito.EVENTOS_EDITAR if accion == "lanzar" else Ambito.EVENTOS_LEER)
        locale = idioma_pedido(idioma)
        if locale is None:
            raise ErrorDeHerramienta("Indica el `idioma` al que traducir.")
        async with sesion(contexto) as session:
            evento = await _evento_permitido(session, contexto, event_id)
            organizacion = await session.get(Organization, contexto.organization_id)
            if organizacion is None:  # pragma: no cover
                raise ErrorDeHerramienta("No existe la organización.")
            entidad = await panel.entidad_de(session, organizacion, "event", evento)
            if locale == entidad.origen:
                raise ErrorDeHerramienta(f"El evento ya está escrito en {locale}.")
            if locale not in entidad.activos:
                raise ErrorDeHerramienta(
                    f"La organización no publica en {locale}: actívalo antes en su ficha."
                )
            total, al_dia = (await panel.progreso_del_evento(session, entidad)).get(locale, (0, 0))
            clave_propia = await cola.clave_propia(session, contexto.organization_id)
        en_cola = False
        if accion == "lanzar":
            if not clave_propia:
                raise ErrorDeHerramienta(
                    "Para traducir automáticamente la organización necesita su propia clave "
                    "de IA (en Eventarium, Configuración de IA). Mientras, puedes escribir "
                    "las traducciones a mano con las herramientas de editar e `idioma`."
                )
            if al_dia < total:
                await cola.pedir(contexto.organization_id, evento.id, [locale])
                en_cola = True
            await _auditar(contexto, "traducir_evento", "event", event_id, {"idioma": locale})
        return schemas.EstadoDeTraduccion(
            evento_id=event_id,
            idioma_original=entidad.origen,
            idioma=locale,
            textos=total,
            al_dia=al_dia,
            en_cola=en_cola,
            traduccion_automatica=clave_propia,
        )
