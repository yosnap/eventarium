"""Traducciones en el panel: qué campos tiene cada entidad, quién puede editarlos
y en qué estado está cada traducción.

Cada entidad se carga bajo RLS (el contexto lo fija la autenticación del panel) y
se exige el mismo permiso que para editar su original. Si no aparece, 404.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.locale import Locale, normalizar_locale
from app.core.permissions import Permission
from app.modules.events.models import Event, EventSession, EventVenue, SessionType
from app.modules.nearby.models import EventNearbyPlace
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.payments.models import EventTicketType
from app.modules.policies.models import OrganizationPolicyVersion
from app.modules.registrations.models import EventRegistrationQuestion
from app.modules.sponsors.models import Sponsor, SponsorTier
from app.modules.translations.campos import (
    CAMPOS,
    TIPOS_DE_ORGANIZACION,
    TipoDeEntidad,
    huella,
)
from app.modules.translations.models import ContentTranslation
from app.modules.translations.service import (
    TIPOS_CON_ORIGEN_DE_ORGANIZACION,
    campo_de_opcion,
    idiomas_de_contenido,
)
from app.shared.errors import NotFoundError, PermissionDeniedError

#: Modelo de cada tipo con fila propia. `tag` no tiene: su entidad es la organización.
MODELOS: dict[TipoDeEntidad, Any] = {
    "event": Event,
    "session": EventSession,
    "session_type": SessionType,
    "venue": EventVenue,
    "ticket_type": EventTicketType,
    "question": EventRegistrationQuestion,
    "sponsor_tier": SponsorTier,
    "sponsor": Sponsor,
    "member_profile": OrganizationMember,
    "organization": Organization,
    "policy_version": OrganizationPolicyVersion,
    "nearby_place": EventNearbyPlace,
}

#: Permiso de lectura y de escritura de cada tipo: los mismos que su original.
PERMISOS: dict[TipoDeEntidad, tuple[Permission, Permission]] = {
    "event": (Permission.EVENTS_READ, Permission.EVENTS_WRITE),
    "session": (Permission.EVENTS_READ, Permission.EVENTS_WRITE),
    "session_type": (Permission.EVENTS_READ, Permission.EVENTS_WRITE),
    "venue": (Permission.EVENTS_READ, Permission.EVENTS_WRITE),
    "ticket_type": (Permission.EVENTS_READ, Permission.PAYMENTS_WRITE),
    "question": (Permission.REGISTRATIONS_READ, Permission.REGISTRATIONS_WRITE),
    "sponsor_tier": (Permission.SPONSORS_READ, Permission.SPONSORS_WRITE),
    "sponsor": (Permission.SPONSORS_READ, Permission.SPONSORS_WRITE),
    "member_profile": (Permission.MEMBERS_READ, Permission.MEMBERS_WRITE),
    "organization": (Permission.ORGANIZATIONS_READ, Permission.ORGANIZATIONS_WRITE),
    "policy_version": (Permission.ORGANIZATIONS_READ, Permission.ORGANIZATIONS_WRITE),
    "nearby_place": (Permission.EVENTS_READ, Permission.EVENTS_WRITE),
    "tag": (Permission.EVENTS_READ, Permission.EVENTS_WRITE),
}

#: Tipos que se pueden abrir en el panel: la etiqueta se edita desde su evento.
TIPOS_EDITABLES = tuple(MODELOS)


@dataclass(frozen=True)
class Campo:
    """Un texto traducible: su entidad, su campo y el original actual."""

    tipo: TipoDeEntidad
    entity_id: uuid.UUID
    campo: str
    original: str


@dataclass(frozen=True)
class Entidad:
    """Una entidad abierta en el panel, ya comprobada bajo RLS."""

    tipo: TipoDeEntidad
    fila: Any
    event_id: uuid.UUID | None
    origen: Locale
    origen_organizacion: Locale
    activos: tuple[Locale, ...]

    def origen_de(self, campo: Campo) -> Locale:
        """Idioma del original de `campo`: las etiquetas de un evento son de la
        organización."""
        if campo.tipo in TIPOS_CON_ORIGEN_DE_ORGANIZACION:
            return self.origen_organizacion
        return self.origen


def _comprobar_permiso(
    tipo: TipoDeEntidad,
    fila: Any,
    usuario: CurrentUser,
    permisos: set[Permission],
    *,
    escribir: bool,
) -> None:
    lectura, escritura = PERMISOS[tipo]
    necesario = escritura if escribir else lectura
    if necesario in permisos:
        return
    # La ficha propia la puede traducir su titular, como puede editarla.
    if tipo == "member_profile" and fila.user_id == usuario.id:
        return
    raise PermissionDeniedError("No tienes permiso para traducir este contenido.")


async def abrir(
    session: AsyncSession,
    usuario: CurrentUser,
    permisos: set[Permission],
    tipo: TipoDeEntidad,
    entity_id: uuid.UUID,
    *,
    escribir: bool,
) -> Entidad:
    """Carga la entidad bajo RLS y comprueba el permiso. 404 si no existe o es
    de otra organización."""
    if tipo not in MODELOS:
        raise NotFoundError("No existe.")
    fila = await session.get(MODELOS[tipo], entity_id)
    organization_id = (
        fila.id if isinstance(fila, Organization) else getattr(fila, "organization_id", None)
    )
    if fila is None or organization_id != usuario.organization_id:
        raise NotFoundError("No existe.")
    _comprobar_permiso(tipo, fila, usuario, permisos, escribir=escribir)
    organizacion = await session.get(Organization, usuario.organization_id)
    if organizacion is None:  # pragma: no cover - la sesión del panel la garantiza
        raise NotFoundError("No existe.")
    return await entidad_de(session, organizacion, tipo, fila)


async def entidad_de(
    session: AsyncSession,
    organizacion: Organization,
    tipo: TipoDeEntidad,
    fila: Any,  # noqa: ANN401 - fila de cualquier modelo traducible
) -> Entidad:
    """`fila`, ya cargada bajo RLS y con el permiso comprobado, con sus idiomas."""
    event_id: uuid.UUID | None
    if tipo == "event":
        event_id = fila.id
    elif tipo in TIPOS_DE_ORGANIZACION:
        event_id = None
    else:
        event_id = fila.event_id
    if tipo in TIPOS_CON_ORIGEN_DE_ORGANIZACION or event_id is None:
        origen = normalizar_locale(organizacion.source_locale)
    else:
        evento = fila if tipo == "event" else await session.get(Event, event_id)
        origen = normalizar_locale(evento.source_locale if evento else None)
    activos = await idiomas_de_contenido(session, organizacion)
    return Entidad(
        tipo=tipo,
        fila=fila,
        event_id=event_id,
        origen=origen,
        origen_organizacion=normalizar_locale(organizacion.source_locale),
        activos=activos,
    )


async def campos_de(session: AsyncSession, entidad: Entidad) -> list[Campo]:
    """Los textos traducibles de la entidad que tienen original. El evento
    incluye sus etiquetas (traducciones de la organización)."""
    fila = entidad.fila
    tipo = entidad.tipo
    campos: list[Campo] = []

    def anadir(t: TipoDeEntidad, entity_id: uuid.UUID, campo: str, valor: object) -> None:
        if isinstance(valor, str) and valor.strip():
            campos.append(Campo(t, entity_id, campo, valor))

    if tipo == "member_profile":
        for clave in sorted(CAMPOS["member_profile"]):
            anadir(tipo, fila.id, clave, (fila.profile_data or {}).get(clave))
    elif tipo == "organization":
        anadir(tipo, fila.id, "description", fila.description)
        # Las etiquetas son de la organización: aquí se traducen a todos sus
        # idiomas, también al de un evento escrito en otro idioma.
        etiquetas = await session.scalars(
            select(func.unnest(Event.tags)).where(Event.organization_id == fila.id).distinct()
        )
        for etiqueta in sorted(etiquetas.all()):
            anadir("tag", fila.id, etiqueta, etiqueta)
    elif tipo == "question":
        anadir(tipo, fila.id, "label", fila.label)
        for opcion in fila.options or []:
            anadir(tipo, fila.id, campo_de_opcion(opcion), opcion)
    else:
        for clave in sorted(CAMPOS[tipo]):
            anadir(tipo, fila.id, clave, getattr(fila, clave, None))
        if tipo == "event":
            for etiqueta in fila.tags or []:
                anadir("tag", fila.organization_id, etiqueta, etiqueta)
    return campos


def _estado_de(fila: ContentTranslation | None, original: str) -> str:
    """`al_dia` si la traducción vale para el original actual; `desactualizada`
    si se hizo sobre otro; `pendiente` si no hay ninguna utilizable (tampoco
    las que la IA tiene en curso o con error)."""
    if fila is None or fila.status not in ("al_dia", "desactualizada"):
        return "pendiente"
    if fila.status == "al_dia" and fila.source_hash == huella(original):
        return "al_dia"
    return "desactualizada"


async def _filas(
    session: AsyncSession,
    organization_id: uuid.UUID,
    campos: Sequence[Campo],
    locales: Sequence[Locale],
) -> dict[tuple[str, uuid.UUID, str, str], ContentTranslation]:
    """Las traducciones de unos campos en unos idiomas, en una sola consulta."""
    if not campos or not locales:
        return {}
    filas = await session.scalars(
        select(ContentTranslation).where(
            ContentTranslation.organization_id == organization_id,
            ContentTranslation.locale.in_(list(locales)),
            ContentTranslation.entity_id.in_({campo.entity_id for campo in campos}),
        )
    )
    return {(f.entity_type, f.entity_id, f.field, f.locale): f for f in filas}


def _organizacion_de(entidad: Entidad) -> uuid.UUID:
    fila = entidad.fila
    return fila.id if isinstance(fila, Organization) else fila.organization_id


async def estado(
    session: AsyncSession, entidad: Entidad, campos: Sequence[Campo], locale: Locale
) -> list[dict[str, Any]]:
    """Cada campo con su traducción en `locale`, su origen y si está al día."""
    por_clave = await _filas(session, _organizacion_de(entidad), campos, [locale])
    resultado = []
    for campo in campos:
        fila = por_clave.get((campo.tipo, campo.entity_id, campo.campo, locale))
        resultado.append(
            {
                "entity_type": campo.tipo,
                "entity_id": str(campo.entity_id),
                "field": campo.campo,
                "original": campo.original,
                "value": fila.value if fila else None,
                "origin": fila.origin if fila else None,
                "status": _estado_de(fila, campo.original),
            }
        )
    return resultado


#: Lo que cuelga de un evento y se traduce con él.
HIJOS_DEL_EVENTO: tuple[tuple[TipoDeEntidad, Any], ...] = (
    ("session", EventSession),
    ("venue", EventVenue),
    ("ticket_type", EventTicketType),
    ("question", EventRegistrationQuestion),
    ("sponsor", Sponsor),
    ("nearby_place", EventNearbyPlace),
)


async def progreso_del_evento(
    session: AsyncSession, evento: Entidad
) -> dict[Locale, tuple[int, int]]:
    """Por cada idioma de destino, cuántos textos del evento (y de lo que cuelga
    de él) hay que traducir y cuántos están al día."""
    entidades = [evento]
    for tipo, modelo in HIJOS_DEL_EVENTO:
        filas: Any = await session.scalars(
            select(modelo).where(
                modelo.organization_id == evento.fila.organization_id,
                modelo.event_id == evento.fila.id,
            )
        )
        entidades += [
            Entidad(
                tipo=tipo,
                fila=fila,
                event_id=evento.fila.id,
                origen=evento.origen,
                origen_organizacion=evento.origen_organizacion,
                activos=evento.activos,
            )
            for fila in filas
        ]
    destinos = [locale for locale in evento.activos if locale != evento.origen]
    return await progreso(session, entidades, destinos)


async def progreso(
    session: AsyncSession, entidades: Sequence[Entidad], locales: Sequence[Locale]
) -> dict[Locale, tuple[int, int]]:
    """Por idioma, cuántos textos hay que traducir y cuántos están al día, con
    una sola consulta de traducciones para todas las entidades."""
    if not entidades:
        return {}
    campos_por_entidad = [(e, await campos_de(session, e)) for e in entidades]
    todos = [campo for _, campos in campos_por_entidad for campo in campos]
    filas = await _filas(session, _organizacion_de(entidades[0]), todos, locales)
    resultado: dict[Locale, tuple[int, int]] = {}
    for locale in locales:
        total = al_dia = 0
        for entidad, campos in campos_por_entidad:
            for campo in campos:
                if entidad.origen_de(campo) == locale:
                    continue
                total += 1
                fila = filas.get((campo.tipo, campo.entity_id, campo.campo, locale))
                al_dia += _estado_de(fila, campo.original) == "al_dia"
        resultado[locale] = (total, al_dia)
    return resultado
