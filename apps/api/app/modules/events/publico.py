"""Lectura pública de eventos, sin sesión: resolución por slug, listados y tema."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import set_organization_context
from app.core.storage import get_storage, public_url_versionada
from app.modules.events import repository
from app.modules.events.models import (
    Event,
)
from app.modules.media.models import Media
from app.modules.organizations import service as organizations_service
from app.modules.organizations.schemas import PublicOrganizationRef
from app.modules.payments import service as payments_service
from app.modules.theme_templates.accent_palette import fusionar_overrides
from app.modules.theme_templates.schemas import PublicTheme
from app.shared.errors import NotFoundError

_RESOLVER_PARA_INSCRIBIR = text(
    "SELECT id, organization_id FROM app_resolve_public_event(:org_slug, :slug)"
)
_RESOLVER_PARA_MOSTRAR = text(
    "SELECT id, organization_id FROM app_resolve_public_event_display(:org_slug, :slug)"
)


async def resolve_public_event_by_slug(
    session: AsyncSession,
    org_slug: str,
    slug: str,
    *,
    para_mostrar: bool = False,
) -> Event:
    """Resuelve un evento público, sin ningún contexto RLS previo.

    Con la URL `/{org}/{evento}` el par organización + slug es único; el slug
    solo no identifica un evento.

    Las dos funciones `SECURITY DEFINER` son de alcance mínimo: solo devuelven
    `(id, organization_id)`, y solo si el evento ya cumple las condiciones de
    «publicable» y su organización sigue activa. La comprobación va dentro de
    la función, no después, para que un evento no publicable no revele ni que
    existe.

    Fija el contexto RLS de `session` (organización **y** vacía `app.user_id`
    — solo para caminos sin autenticar). Solo debe llamarse desde routers
    públicos, nunca desde uno autenticado: sobrescribiría la organización
    activa y el usuario de la sesión en curso.

    `para_mostrar=True` admite también eventos cancelados (su ficha sigue
    visible con el aviso). Todo lo que inscribe, vende o cobra usa el valor
    por defecto, que solo resuelve eventos publicados: así un evento
    cancelado nunca vuelve a abrir la inscripción ni la compra.
    """
    consulta = _RESOLVER_PARA_MOSTRAR if para_mostrar else _RESOLVER_PARA_INSCRIBIR
    fila = (await session.execute(consulta, {"org_slug": org_slug, "slug": slug})).first()
    if fila is None:
        raise NotFoundError("El evento no existe.")

    await set_organization_context(session, fila[1])
    evento = await session.get(Event, fila[0])
    if evento is None:  # pragma: no cover - ya lo garantiza la función SECURITY DEFINER
        raise NotFoundError("El evento no existe.")

    return evento


async def _resolver_portadas(session: AsyncSession, eventos: list[Event]) -> dict[uuid.UUID, str]:
    """Portada de cada evento de la página con una sola consulta a `Media`.

    Sin una consulta por evento (una sola a `Media` por página). Vale
    cuando todos los eventos comparten el contexto RLS ya fijado.
    """
    ids_de_medios = {e.cover_media_id for e in eventos if e.cover_media_id is not None}
    medios: dict[uuid.UUID, Media] = {}
    if ids_de_medios:
        filas = await session.scalars(select(Media).where(Media.id.in_(ids_de_medios)))
        medios = {medio.id: medio for medio in filas}
    almacen = get_storage()
    portadas: dict[uuid.UUID, str] = {}
    for evento in eventos:
        if evento.cover_media_id is not None:
            medio = medios.get(evento.cover_media_id)
            if medio is not None:
                portadas[evento.id] = public_url_versionada(medio.object_key, medio.updated_at)
        elif evento.cover_object_key:
            portadas[evento.id] = almacen.public_url(evento.cover_object_key)
    return portadas


async def list_public_events_across_organizations(
    session: AsyncSession,
    *,
    category_slug: str | None = None,
    tags: tuple[str, ...] = (),
    limit: int | None = None,
    offset: int = 0,
) -> tuple[
    list[
        tuple[Event, int, payments_service.VentaPublica | None, str | None, PublicOrganizationRef]
    ],
    int,
]:
    """Eventos publicados de **toda la instalación**, sin organización activa.

    Fase 6 del plan de organización sin dominio: `GET /public/events` (el
    listado) seguía resolviendo por host, comportamiento roto en producción
    sin dominio propio (ver riesgos de `plan.md`). El frontend ya esperaba un
    listado de toda la instalación, sin filtro de organización
    (`upcoming-events.ts`/`events-list-page.ts` piden el mismo endpoint sin
    ningún parámetro).

    RLS exige el contexto de una organización por fila; no hay ningún host
    que lo fije de antemano para "todas a la vez". `app_list_public_event_organizations`
    (`SECURITY DEFINER` de alcance mínimo, mismo patrón que
    `app_resolve_public_event`) devuelve solo los `id` de organización con al
    menos un evento publicable — la resolución completa de cada una se hace
    después, fijando su contexto RLS una por una y reutilizando exactamente
    las mismas consultas que ya usa el listado de una sola organización
    (`public_events_with_confirmed_count_query`, `get_public_sales`):
    nada de SQL nuevo por duplicar, solo repetido por organización. El número
    de organizaciones de una instalación es pequeño (no es una consulta por
    evento, es una por organización), así que el coste es aceptable para un
    endpoint ya limitado por IP.

    Los filtros (categoría, etiquetas) van en la consulta de cada organización.
    Con `limit`, cada organización trae como mucho `offset + limit` filas
    (ordenadas) y el conjunto mezclado se corta después: la página global es la
    correcta sin traer todos los eventos. Devuelve también el total que
    cumple los filtros, para paginar.
    """
    organizaciones = (
        await session.execute(
            text("SELECT organization_id FROM app_list_public_event_organizations()")
        )
    ).all()

    resultado: list[
        tuple[Event, int, payments_service.VentaPublica | None, str | None, PublicOrganizationRef]
    ] = []
    total = 0
    for (organization_id,) in organizaciones:
        await set_organization_context(session, organization_id)
        organizacion = await organizations_service.public_ref(session, organization_id)
        consulta = repository.public_events_with_confirmed_count_query(
            organization_id, category_slug=category_slug, tags=tags
        )
        if limit is not None:
            # El total solo hace falta para paginar; sin `limit` es `len(resultado)`.
            total += int(
                await session.scalar(
                    select(func.count()).select_from(consulta.order_by(None).subquery())
                )
                or 0
            )
            consulta = consulta.limit(offset + limit)
        filas = (await session.execute(consulta)).all()
        ids_de_pago = [evento.id for evento, _ in filas if evento.registration_mode == "paid"]
        precios = await payments_service.get_public_sales(
            session, organization_id=organization_id, event_ids=ids_de_pago
        )
        # Las portadas se resuelven aquí, dentro del contexto RLS de esta
        # organización (`Media` tiene RLS), y en una sola consulta.
        portadas = await _resolver_portadas(session, [evento for evento, _ in filas])
        for evento, reservadas in filas:
            resultado.append(
                (evento, reservadas, precios.get(evento.id), portadas.get(evento.id), organizacion)
            )

    resultado.sort(key=lambda item: (item[0].starts_at, item[0].id))
    if limit is None:
        return resultado, len(resultado)
    return resultado[offset : offset + limit], total


async def tema_publico_del_evento(session: AsyncSession, evento: Event) -> PublicTheme | None:
    """La plantilla del evento, con la herencia ya resuelta.

    Cuatro niveles, y el orden importa: la del evento si la eligió, si no la de
    su organización, si no la aplicada a la plataforma («Usar en la
    plataforma»), y si tampoco la marcada por defecto en el catálogo. Se resuelve
    aquí y no en el cliente porque encadenar tres consultas desde el navegador
    para pintar una página pública sería absurdo, y porque el catálogo es una
    tabla de instalación que el visitante no tiene por qué conocer.

    Único punto de fusión de `theme_overrides` en el backend (fase 1 del plan
    «diseño del evento»): el panel de organizador calcula su propia vista
    previa en el cliente, no hay un segundo resolutor de tokens en el
    servidor. `fusionar_overrides` copia `tokens` antes de tocarlo — el dict
    de esta fila ya es nuevo en cada petición (deserializado por el driver a
    partir de `text(...)`, no el mismo objeto que el mapa de identidad del
    ORM que usa el catálogo de `organizations/router.py`), pero se copia
    igual, sin depender de esa garantía implícita.
    """
    fila = (
        await session.execute(
            text(
                "SELECT t.id, t.key, t.name, t.tokens "
                "FROM events e "
                "LEFT JOIN organization_branding b ON b.organization_id = e.organization_id "
                "LEFT JOIN platform_branding pb ON pb.singleton = 'default' "
                "LEFT JOIN theme_templates t ON t.id = COALESCE("
                "    e.theme_template_id, "
                "    b.theme_template_id, "
                "    pb.theme_template_id, "
                "    (SELECT id FROM theme_templates WHERE is_default IS TRUE LIMIT 1)"
                ") "
                "WHERE e.id = :id"
            ),
            {"id": evento.id},
        )
    ).first()

    if fila is None or fila[0] is None:
        return None

    tokens = fila[3]
    if evento.theme_overrides:
        tokens = fusionar_overrides(tokens, evento.theme_overrides)
    return PublicTheme(id=str(fila[0]), key=fila[1], name=fila[2], tokens=tokens)


# Los cancelados siguen visibles en la página de la organización, marcados como
# cancelados: no desaparecen de su historial.
_ESTADOS_EN_LA_PAGINA_DE_ORGANIZACION = ("published", "cancelled")


async def list_public_events_of_organization(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    upcoming: bool,
    limit: int,
    offset: int,
) -> tuple[list[tuple[Event, int, payments_service.VentaPublica | None, str | None]], int]:
    """Eventos publicados de **una** organización, próximos o pasados, paginados.

    Fija el contexto RLS de esa organización y no recorre las demás. Los
    próximos son los que aún no han terminado, del más cercano al más lejano;
    los pasados, del más reciente al más antiguo. Reutiliza la misma consulta
    que el listado de toda la instalación, con el filtro de publicación
    explícito. Devuelve las filas de la página y el total.
    """
    await set_organization_context(session, organization_id)
    ahora = func.now()
    if upcoming:
        condicion = Event.ends_at >= ahora
        orden = (Event.starts_at.asc(), Event.id.asc())
    else:
        condicion = Event.ends_at < ahora
        orden = (Event.starts_at.desc(), Event.id.desc())

    base = repository.public_events_with_confirmed_count_query(
        organization_id, _ESTADOS_EN_LA_PAGINA_DE_ORGANIZACION
    )
    total = await session.scalar(
        select(func.count()).select_from(
            repository.public_events_query(organization_id, _ESTADOS_EN_LA_PAGINA_DE_ORGANIZACION)
            .where(condicion)
            .subquery()
        )
    )
    filas = (
        await session.execute(
            base.where(condicion).order_by(None).order_by(*orden).limit(limit).offset(offset)
        )
    ).all()

    ids_de_pago = [evento.id for evento, _ in filas if evento.registration_mode == "paid"]
    precios = await payments_service.get_public_sales(
        session, organization_id=organization_id, event_ids=ids_de_pago
    )
    portadas = await _resolver_portadas(session, [evento for evento, _ in filas])
    resultado = [
        (evento, reservadas, precios.get(evento.id), portadas.get(evento.id))
        for evento, reservadas in filas
    ]
    return resultado, int(total or 0)
