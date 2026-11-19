"""Lectura y escritura de las traducciones del contenido del organizador.

La lectura pasa por un `Traductor`: se carga una vez por página, con una sola
consulta, y cada campo que se pinta pasa por él. Devuelve el texto en el idioma
pedido si su traducción está al día, o el original si no, y de paso anota qué
campos faltan en cada idioma. Con eso la respuesta dice qué idioma ha servido y
en qué idiomas está la página al día (lo que la web usa para indexarla).

Una traducción solo se sirve si está `al_dia` **y** su huella coincide con el
original actual: si alguien cambia el original por un camino que no la marca
como desactualizada, la traducción vieja tampoco se muestra.

Todas las consultas corren bajo RLS: quien llama ya ha fijado el contexto de la
organización (la resolución pública del evento lo hace).
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, any_, delete, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.database import set_organization_context
from app.core.locale import DEFAULT_LOCALE, LOCALES, Locale, normalizar_locale
from app.modules.events.models import Event, EventCategory
from app.modules.organizations.models import Organization
from app.modules.platform import repository as platform_repository
from app.modules.translations.campos import (
    PREFIJO_OPCION,
    TIPOS_DE_ORGANIZACION,
    TipoDeEntidad,
    campo_valido,
    huella,
)
from app.modules.translations.models import ContentTranslation
from app.shared.errors import ValidationDomainError

_Clave = tuple[str, uuid.UUID, str, str]


async def idiomas_de_contenido(
    session: AsyncSession, organizacion: Organization
) -> tuple[Locale, ...]:
    """Idiomas en que publica la organización y que la plataforma tiene activos,
    en el orden del catálogo."""
    plataforma = await platform_repository.get_platform_branding(session)
    activos_plataforma = set(plataforma.enabled_locales or [DEFAULT_LOCALE])
    propios = set(organizacion.content_locales or [DEFAULT_LOCALE])
    return tuple(locale for locale in LOCALES if locale in propios and locale in activos_plataforma)


#: Tipos cuyo original está escrito en el idioma de la organización y no en el
#: del evento: lo que es de toda la organización y sus textos legales.
TIPOS_CON_ORIGEN_DE_ORGANIZACION: frozenset[TipoDeEntidad] = TIPOS_DE_ORGANIZACION | {
    "policy_version"
}

#: Qué cargar de lo que no cuelga de un evento: tipo → ids concretos, o `None`
#: para todas las filas de ese tipo.
DeOrganizacion = Mapping[TipoDeEntidad, Collection[uuid.UUID] | None]


@dataclass
class Traductor:
    """Traducciones de una página en todos sus idiomas activos.

    `idioma` es el pedido. `origen` es el idioma original de la página (el del
    evento, o el de la organización en sus propias páginas); lo que es de la
    organización usa `origen_organizacion`.
    """

    idioma: Locale
    origen: Locale
    activos: tuple[Locale, ...]
    origen_organizacion: Locale | None = None
    _filas: dict[_Clave, tuple[str, str]] = field(default_factory=dict)
    _pendientes: dict[Locale, set[tuple[str, uuid.UUID, str]]] = field(default_factory=dict)
    _principal_visto: bool = False
    _principal_pendiente: bool = False
    _tipos_servidos: set[str] = field(default_factory=set)

    def origen_de(self, tipo: TipoDeEntidad) -> Locale:
        """Idioma en que está escrito el original de `tipo`."""
        if tipo in TIPOS_CON_ORIGEN_DE_ORGANIZACION and self.origen_organizacion:
            return self.origen_organizacion
        return self.origen

    @property
    def destinos(self) -> tuple[Locale, ...]:
        """Idiomas activos que necesitan traducción en algún tipo."""
        origenes = {self.origen, self.origen_organizacion or self.origen}
        return tuple(locale for locale in self.activos if len(origenes - {locale}) > 0)

    def _traduccion(
        self,
        tipo: TipoDeEntidad,
        entity_id: uuid.UUID,
        campo: str,
        original: str,
        *,
        contar: bool,
        principal: bool,
    ) -> str | None:
        """Registra si `campo` está al día en cada idioma y devuelve su valor en
        el pedido, o `None` si hay que servir el original."""
        origen = self.origen_de(tipo)
        firma = huella(original)
        servido: str | None = None
        falta_en_el_pedido = False
        for locale in self.activos:
            if locale == origen:
                continue
            fila = self._filas.get((tipo, entity_id, campo, locale))
            al_dia = fila is not None and fila[1] == firma
            if al_dia and locale == self.idioma:
                servido = fila[0]  # type: ignore[index]
            if not al_dia:
                falta_en_el_pedido = falta_en_el_pedido or locale == self.idioma
                if contar:
                    self._pendientes.setdefault(locale, set()).add((tipo, entity_id, campo))
        if principal:
            self._principal_visto = True
            self._principal_pendiente = self._principal_pendiente or falta_en_el_pedido
        if servido is not None:
            self._tipos_servidos.add(tipo)
        return servido

    def campo(
        self,
        tipo: TipoDeEntidad,
        entity_id: uuid.UUID,
        campo: str,
        original: str | None,
        *,
        principal: bool = False,
        contar: bool = True,
    ) -> str | None:
        """`original` en el idioma pedido, con caída al original.

        `principal` marca el contenido principal de la página (título,
        descripción): el aviso de «idioma original» solo depende de él.
        `contar=False` traduce sin que el campo cuente para saber si la página
        está al día (el historial, que es de otras páginas).
        """
        if not original:
            return original
        traducido = self._traduccion(
            tipo, entity_id, campo, original, contar=contar, principal=principal
        )
        return traducido if traducido is not None else original

    def opciones(
        self, entity_id: uuid.UUID, originales: Sequence[str] | None
    ) -> list[tuple[str, str]] | None:
        """Opciones de una pregunta como pares `(valor original, etiqueta)`.

        Cada opción se traduce aparte (campo `option:<valor>`): añadir o
        reordenar opciones no invalida las traducciones de las demás.
        """
        if originales is None:
            return None
        return [
            (valor, self.campo("question", entity_id, campo_de_opcion(valor), valor) or valor)
            for valor in originales
        ]

    def etiqueta(self, organization_id: uuid.UUID, valor: str) -> str:
        """Una etiqueta del evento tal como se muestra; el valor sigue siendo el
        identificador de filtros y URLs."""
        return self.campo("tag", organization_id, valor, valor) or valor

    def sirvio(self, tipo: TipoDeEntidad) -> bool:
        """Se ha servido al menos un campo de `tipo` traducido."""
        return tipo in self._tipos_servidos

    @property
    def idiomas_al_dia(self) -> list[Locale]:
        """Idiomas en que todo lo que muestra la página está al día (el de origen
        siempre lo está)."""
        return [
            locale
            for locale in self.activos
            if locale == self.origen or not self._pendientes.get(locale)
        ]

    @property
    def idioma_servido(self) -> Locale:
        """El idioma pedido si el contenido principal de la página está en él; si
        la página no marca contenido principal, si está entera en él. Si no, el
        de origen."""
        if self.idioma == self.origen or self.idioma not in self.activos:
            return self.origen
        if self._principal_visto:
            return self.origen if self._principal_pendiente else self.idioma
        return self.idioma if self.idioma in self.idiomas_al_dia else self.origen

    @property
    def campos_pendientes(self) -> int:
        """Campos que se muestran en el original porque falta su traducción al
        idioma pedido."""
        if self.idioma == self.origen or self.idioma not in self.activos:
            return 0
        return len(self._pendientes.get(self.idioma, set()))

    def metadatos(self) -> dict[str, Any]:
        """Los campos de idioma que añaden las respuestas públicas
        (`ContentLocaleInfo`)."""
        return {
            "source_locale": self.origen,
            "up_to_date_locales": self.idiomas_al_dia,
            "served_locale": self.idioma_servido,
            "pending_fields": self.campos_pendientes,
        }


def campo_de_opcion(valor: str) -> str:
    """Campo de la traducción de una opción de pregunta."""
    return f"{PREFIJO_OPCION}{valor}"


async def _cargar_filas(
    session: AsyncSession,
    organization_id: uuid.UUID,
    locales: Iterable[Locale],
    *,
    event_ids: Collection[uuid.UUID] = (),
    de_organizacion: DeOrganizacion | None = None,
) -> dict[_Clave, tuple[str, str]]:
    """Traducciones al día de los eventos indicados y de lo que se pida de la
    organización. Nunca carga más tipos de los que la página va a mostrar."""
    locales = tuple(locales)
    if not locales:
        return {}
    ambitos: list[ColumnElement[bool]] = []
    if event_ids:
        ambitos.append(ContentTranslation.event_id.in_(list(event_ids)))
    for tipo, ids in (de_organizacion or {}).items():
        condiciones = [
            ContentTranslation.event_id.is_(None),
            ContentTranslation.entity_type == tipo,
        ]
        if ids is not None:
            if not ids:
                continue
            condiciones.append(ContentTranslation.entity_id.in_(list(ids)))
        ambitos.append(and_(*condiciones))
    if not ambitos:
        return {}
    filas = await session.execute(
        select(
            ContentTranslation.entity_type,
            ContentTranslation.entity_id,
            ContentTranslation.field,
            ContentTranslation.locale,
            ContentTranslation.value,
            ContentTranslation.source_hash,
        ).where(
            ContentTranslation.organization_id == organization_id,
            ContentTranslation.locale.in_(locales),
            ContentTranslation.status == "al_dia",
            or_(*ambitos),
        )
    )
    return {(t, e, f, loc): (valor, firma) for t, e, f, loc, valor, firma in filas}


async def _traductor(
    session: AsyncSession,
    organizacion: Organization | None,
    idioma: Locale,
    origen: Locale,
) -> Traductor:
    activos = await idiomas_de_contenido(session, organizacion) if organizacion else ()
    origen_org = normalizar_locale(organizacion.source_locale) if organizacion else DEFAULT_LOCALE
    for necesario in (origen_org, origen):
        if necesario not in activos:
            activos = (necesario, *activos)
    return Traductor(idioma=idioma, origen=origen, activos=activos, origen_organizacion=origen_org)


async def traductor_de_evento(
    session: AsyncSession,
    evento: Event,
    idioma: Locale,
    *,
    de_organizacion: DeOrganizacion | None = None,
    otros_eventos: Collection[uuid.UUID] = (),
) -> Traductor:
    """Traductor de una página de un evento y de lo que cuelga de él.

    `de_organizacion` dice qué tipos de la organización muestra la página;
    `otros_eventos`, de qué otros eventos de la misma organización enseña algo
    (el historial).
    """
    organizacion = await session.get(Organization, evento.organization_id)
    traductor = await _traductor(
        session, organizacion, idioma, normalizar_locale(evento.source_locale)
    )
    traductor._filas = await _cargar_filas(
        session,
        evento.organization_id,
        traductor.destinos,
        event_ids={evento.id, *otros_eventos},
        de_organizacion=de_organizacion,
    )
    return traductor


async def traductor_de_organizacion(
    session: AsyncSession,
    organizacion: Organization,
    idioma: Locale,
    *,
    de_organizacion: DeOrganizacion,
    event_ids: Collection[uuid.UUID] = (),
) -> Traductor:
    """Traductor de las páginas de la organización: su perfil o el de un
    ponente. El idioma de origen es el de la organización."""
    traductor = await _traductor(
        session, organizacion, idioma, normalizar_locale(organizacion.source_locale)
    )
    traductor._filas = await _cargar_filas(
        session,
        organizacion.id,
        traductor.destinos,
        event_ids=event_ids,
        de_organizacion=de_organizacion,
    )
    return traductor


_LEER_CONTEXTO = text(
    "SELECT current_setting('app.organization_id', true), current_setting('app.user_id', true)"
)


def _uuid_o_none(valor: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(valor) if valor else None
    except ValueError:
        return None


async def traductores_de_listado(
    session: AsyncSession, eventos: Sequence[Event], idioma: Locale
) -> dict[uuid.UUID, Traductor]:
    """Un traductor por evento de un listado, de una o varias organizaciones.

    Agrupa por organización y fija el contexto de cada una antes de leer, así la
    lectura sigue bajo RLS. Al terminar restaura el contexto que había
    (organización y usuario).
    """
    organizacion_previa, usuario_previo = (await session.execute(_LEER_CONTEXTO)).one()
    por_organizacion: dict[uuid.UUID, list[Event]] = {}
    for evento in eventos:
        por_organizacion.setdefault(evento.organization_id, []).append(evento)
    traductores: dict[uuid.UUID, Traductor] = {}
    try:
        for organization_id, propios in por_organizacion.items():
            await set_organization_context(session, organization_id)
            organizacion = await session.get(Organization, organization_id)
            base = await _traductor(session, organizacion, idioma, DEFAULT_LOCALE)
            filas = await _cargar_filas(
                session,
                organization_id,
                base.activos,
                event_ids=[evento.id for evento in propios],
                de_organizacion={"tag": None},
            )
            for evento in propios:
                origen = normalizar_locale(evento.source_locale)
                traductor = Traductor(
                    idioma=idioma,
                    origen=origen,
                    activos=base.activos if origen in base.activos else (origen, *base.activos),
                    origen_organizacion=base.origen_organizacion,
                )
                traductor._filas = filas
                traductores[evento.id] = traductor
    finally:
        await set_organization_context(
            session, _uuid_o_none(organizacion_previa), _uuid_o_none(usuario_previo)
        )
    return traductores


def nombre_de_categoria(categoria: EventCategory, idioma: Locale) -> str:
    """Nombre de una categoría en `idioma`, con caída al original."""
    return (categoria.name_i18n or {}).get(idioma) or categoria.name


def _event_id_de(tipo: TipoDeEntidad, event_id: uuid.UUID | None) -> uuid.UUID | None:
    if tipo in TIPOS_DE_ORGANIZACION:
        return None
    if tipo != "policy_version" and event_id is None:
        raise ValidationDomainError("Esta traducción tiene que pertenecer a un evento.")
    return event_id


async def guardar_manual(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID | None,
    tipo: TipoDeEntidad,
    entity_id: uuid.UUID,
    campo: str,
    locale: Locale,
    valor: str,
    original: str,
    origen_del_contenido: Locale,
    idiomas_activos: Sequence[Locale],
    user_id: uuid.UUID | None,
) -> ContentTranslation:
    """Guarda la traducción escrita a mano por el organizador.

    Quien llama ya ha cargado la entidad bajo RLS con el mismo permiso que pide
    editar su original, y le pasa el original actual. La IA no vuelve a tocar
    una traducción manual: si cambia el original, pasa a `desactualizada`.
    """
    if not campo_valido(tipo, campo):
        raise ValidationDomainError("Ese campo no se puede traducir.")
    if locale == origen_del_contenido:
        raise ValidationDomainError("El idioma original no se traduce.")
    if locale not in idiomas_activos:
        raise ValidationDomainError("La organización no publica en ese idioma.")
    valor = valor.strip()
    if not valor:
        raise ValidationDomainError("La traducción no puede estar vacía.")
    ahora = datetime.now(UTC)
    valores = {
        "value": valor,
        "origin": "manual",
        "status": "al_dia",
        "source_hash": huella(original),
        "error_count": 0,
        "retry_after": None,
        "updated_by": user_id,
        "updated_at": ahora,
    }
    sentencia = (
        insert(ContentTranslation)
        .values(
            id=uuid.uuid4(),
            organization_id=organization_id,
            event_id=_event_id_de(tipo, event_id),
            entity_type=tipo,
            entity_id=entity_id,
            field=campo,
            locale=locale,
            **valores,
        )
        .on_conflict_do_update(constraint="uq_content_translations_campo", set_=valores)
        .returning(ContentTranslation)
    )
    fila = (await session.execute(sentencia)).scalar_one()
    return fila


async def marcar_revisada(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    tipo: TipoDeEntidad,
    entity_id: uuid.UUID,
    campo: str,
    locale: Locale,
    original: str,
    user_id: uuid.UUID | None,
) -> ContentTranslation:
    """El organizador da por buena una traducción tal como está: queda fijada
    (la IA ya no la toca) y al día con el original actual."""
    fila = await session.scalar(
        select(ContentTranslation).where(
            ContentTranslation.organization_id == organization_id,
            ContentTranslation.entity_type == tipo,
            ContentTranslation.entity_id == entity_id,
            ContentTranslation.field == campo,
            ContentTranslation.locale == locale,
        )
    )
    if fila is None:
        raise ValidationDomainError("No hay ninguna traducción que revisar.")
    fila.origin = "revisada"
    fila.status = "al_dia"
    fila.source_hash = huella(original)
    fila.updated_by = user_id
    fila.updated_at = datetime.now(UTC)
    return fila


async def borrar_campos(
    session: AsyncSession,
    organization_id: uuid.UUID,
    tipo: TipoDeEntidad,
    entity_id: uuid.UUID,
    campos: Collection[str],
) -> None:
    """Borra las traducciones de unos campos de una entidad, en todos los
    idiomas: cuando el original se vacía, su traducción no se conserva."""
    await session.execute(
        delete(ContentTranslation).where(
            ContentTranslation.organization_id == organization_id,
            ContentTranslation.entity_type == tipo,
            ContentTranslation.entity_id == entity_id,
            ContentTranslation.field.in_(list(campos)),
        )
    )


async def borrar_etiquetas_sin_uso(session: AsyncSession) -> int:
    """Borra las traducciones de etiquetas que ya no lleva ningún evento de su
    organización. Lo llama el barrido diario con la sesión de mantenimiento: las
    demás traducciones se borran con su fila (trigger de la migración `0074`)."""
    en_uso = (
        select(Event.id)
        .where(
            Event.organization_id == ContentTranslation.organization_id,
            ContentTranslation.field == any_(Event.tags),
        )
        .exists()
    )
    resultado = await session.execute(
        delete(ContentTranslation).where(and_(ContentTranslation.entity_type == "tag", ~en_uso))
    )
    return int(resultado.rowcount or 0)  # type: ignore[attr-defined]
