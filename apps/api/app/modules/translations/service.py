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

import json
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import and_, any_, delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import set_organization_context
from app.core.locale import DEFAULT_LOCALE, LOCALES, Locale, normalizar_locale
from app.modules.events.models import Event, EventCategory
from app.modules.organizations.models import Organization
from app.modules.platform import repository as platform_repository
from app.modules.translations.campos import (
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


@dataclass
class Traductor:
    """Traducciones de una página en todos sus idiomas activos.

    `idioma` es el pedido; `origen`, el idioma en que está escrito el original.
    """

    idioma: Locale
    origen: Locale
    activos: tuple[Locale, ...]
    _filas: dict[_Clave, tuple[str, str]] = field(default_factory=dict)
    _pendientes: dict[Locale, set[tuple[str, uuid.UUID, str]]] = field(default_factory=dict)

    @property
    def destinos(self) -> tuple[Locale, ...]:
        """Idiomas activos distintos del de origen: los que necesitan traducción."""
        return tuple(locale for locale in self.activos if locale != self.origen)

    def _traduccion(
        self, tipo: TipoDeEntidad, entity_id: uuid.UUID, campo: str, original: str
    ) -> str | None:
        """Registra si `campo` está al día en cada destino y devuelve su valor en
        el idioma pedido, o `None` si hay que servir el original."""
        firma = huella(original)
        servido: str | None = None
        for locale in self.destinos:
            fila = self._filas.get((tipo, entity_id, campo, locale))
            if fila is not None and fila[1] == firma:
                if locale == self.idioma:
                    servido = fila[0]
            else:
                self._pendientes.setdefault(locale, set()).add((tipo, entity_id, campo))
        return servido

    def campo(
        self, tipo: TipoDeEntidad, entity_id: uuid.UUID, campo: str, original: str | None
    ) -> str | None:
        """`original` en el idioma pedido, con caída al original."""
        if not original:
            return original
        traducido = self._traduccion(tipo, entity_id, campo, original)
        return traducido if traducido is not None else original

    def opciones(
        self, entity_id: uuid.UUID, originales: Sequence[str] | None
    ) -> list[tuple[str, str]] | None:
        """Opciones de una pregunta como pares `(valor original, etiqueta)`.

        La traducción guarda un mapa `{valor_original: etiqueta}`. Una opción que
        falte en el mapa se muestra con su valor original.
        """
        if originales is None:
            return None
        lista = list(originales)
        if not lista:
            return []
        traducido = self._traduccion("question", entity_id, "options", json.dumps(lista))
        etiquetas: dict[str, str] = {}
        if traducido is not None:
            try:
                cargado = json.loads(traducido)
            except ValueError:
                cargado = {}
            if isinstance(cargado, dict):
                etiquetas = {str(k): str(v) for k, v in cargado.items()}
        return [(valor, etiquetas.get(valor) or valor) for valor in lista]

    def etiqueta(self, organization_id: uuid.UUID, valor: str) -> str:
        """Una etiqueta del evento tal como se muestra; el valor sigue siendo el
        identificador de filtros y URLs."""
        return self.campo("tag", organization_id, valor, valor) or valor

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
        """El idioma pedido si la página está entera en él; si no, el de origen."""
        return self.idioma if self.idioma in self.idiomas_al_dia else self.origen

    @property
    def campos_pendientes(self) -> int:
        """Campos que se muestran en el original porque falta su traducción al
        idioma pedido."""
        if self.idioma == self.origen or self.idioma not in self.activos:
            return 0
        return len(self._pendientes.get(self.idioma, set()))

    def metadatos(self) -> dict[str, object]:
        """Los campos de idioma que añaden las respuestas públicas."""
        return {
            "idioma_origen": self.origen,
            "idiomas_al_dia": self.idiomas_al_dia,
            "idioma_servido": self.idioma_servido,
            "campos_pendientes": self.campos_pendientes,
        }


async def _cargar_filas(
    session: AsyncSession,
    organization_id: uuid.UUID,
    locales: Iterable[Locale],
    *,
    event_ids: Sequence[uuid.UUID] = (),
    con_organizacion: bool = True,
) -> dict[_Clave, tuple[str, str]]:
    """Traducciones al día de los eventos indicados y, si se pide, de lo que es
    de la organización (perfiles, etiquetas, tipos de sesión, niveles…)."""
    locales = tuple(locales)
    if not locales:
        return {}
    ambitos = []
    if event_ids:
        ambitos.append(ContentTranslation.event_id.in_(event_ids))
    if con_organizacion:
        ambitos.append(ContentTranslation.event_id.is_(None))
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


async def traductor_de_evento(session: AsyncSession, evento: Event, idioma: Locale) -> Traductor:
    """Traductor de la ficha de un evento y de todo lo que cuelga de él."""
    organizacion = await session.get(Organization, evento.organization_id)
    activos = await idiomas_de_contenido(session, organizacion) if organizacion else ()
    origen = normalizar_locale(evento.source_locale)
    if origen not in activos:
        activos = (origen, *activos)
    traductor = Traductor(idioma=idioma, origen=origen, activos=activos)
    traductor._filas = await _cargar_filas(
        session, evento.organization_id, traductor.destinos, event_ids=[evento.id]
    )
    return traductor


async def traductor_de_organizacion(
    session: AsyncSession, organizacion: Organization, idioma: Locale
) -> Traductor:
    """Traductor de lo que no cuelga de un evento: la página de la organización,
    el perfil de un ponente o las políticas generales. El idioma de origen es el
    primero de los que publica la organización."""
    activos = await idiomas_de_contenido(session, organizacion)
    origen: Locale = activos[0] if activos else DEFAULT_LOCALE
    traductor = Traductor(idioma=idioma, origen=origen, activos=activos or (origen,))
    traductor._filas = await _cargar_filas(session, organizacion.id, traductor.destinos)
    return traductor


async def traductores_de_listado(
    session: AsyncSession, eventos: Sequence[Event], idioma: Locale
) -> dict[uuid.UUID, Traductor]:
    """Un traductor por evento de un listado de varias organizaciones.

    Agrupa por organización y fija el contexto de cada una antes de leer, así la
    lectura sigue bajo RLS. Al terminar deja el contexto vacío, como estaba en un
    listado público.
    """
    por_organizacion: dict[uuid.UUID, list[Event]] = {}
    for evento in eventos:
        por_organizacion.setdefault(evento.organization_id, []).append(evento)
    traductores: dict[uuid.UUID, Traductor] = {}
    try:
        for organization_id, propios in por_organizacion.items():
            await set_organization_context(session, organization_id)
            organizacion = await session.get(Organization, organization_id)
            activos = await idiomas_de_contenido(session, organizacion) if organizacion else ()
            filas = await _cargar_filas(
                session,
                organization_id,
                activos,
                event_ids=[evento.id for evento in propios],
            )
            for evento in propios:
                origen = normalizar_locale(evento.source_locale)
                traductor = Traductor(
                    idioma=idioma,
                    origen=origen,
                    activos=activos if origen in activos else (origen, *activos),
                )
                traductor._filas = filas
                traductores[evento.id] = traductor
    finally:
        await set_organization_context(session, None)
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
