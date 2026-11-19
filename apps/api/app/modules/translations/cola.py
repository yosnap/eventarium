"""Traducción automática con IA: qué se traduce, cuándo y con qué límites.

Unidad de trabajo: un **ámbito** (un evento con todo lo que cuelga de él, o lo
que es de la organización) a un idioma. Así una publicación son una o pocas
llamadas a la IA, no una por campo.

- **Cuándo.** Al guardar cualquier texto traducible se apunta una petición en
  `translation_requests` (listener de la sesión, tras el commit). Un barrido
  cada minuto procesa las que llevan un rato quietas. Al navegar, la web pide
  la traducción de lo que está viendo y se procesa al momento.
- **Sin duplicados.** Cada campo se reserva en `content_translations` con
  estado `en_curso` mediante un *upsert* condicionado: si otra tarea lo tiene
  reservado (y no está atascado), no se toca. Nunca se reservan las
  traducciones escritas a mano o revisadas.
- **Límites.** Solo con la clave de IA propia de la organización; la
  traducción gasta como mucho el 50 % del límite mensual de IA; los borradores
  no se traducen.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import event as sa_event
from sqlalchemy import func, inspect, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.core.locale import Locale, normalizar_locale
from app.core.tras_commit import encolar_tras_commit
from app.modules.ai_gateway import repository as ai_repository
from app.modules.ai_gateway import service as ai_service
from app.modules.ai_gateway.models import ESTADOS_QUE_GASTAN, AiUsageRecord
from app.modules.events.models import (
    Event,
    EventSession,
    EventVenue,
    SessionType,
    SpeakerPublicProfile,
)
from app.modules.nearby.models import EventNearbyPlace
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.payments.models import EventTicketType
from app.modules.policies.models import OrganizationPolicyVersion
from app.modules.registrations.models import EventRegistrationQuestion
from app.modules.sponsors.models import Sponsor, SponsorTier
from app.modules.translations import ia, panel
from app.modules.translations.campos import (
    CAMPOS,
    CARACTERES_MAXIMOS_IA,
    TIPOS_DE_ORGANIZACION,
    TipoDeEntidad,
    huella,
)
from app.modules.translations.models import ContentTranslation, TranslationRequest
from app.modules.translations.service import idiomas_de_contenido

logger = logging.getLogger(__name__)

#: Un campo `en_curso` más antiguo que esto se da por atascado y se puede reservar.
RESERVA_CADUCA = timedelta(minutes=15)
#: Tiempo de calma tras el último guardado antes de traducir.
DEBOUNCE = timedelta(seconds=60)
#: Peticiones que procesa cada barrido: un ritmo que el servidor y la IA aguantan.
PETICIONES_POR_BARRIDO = 20
#: Y como mucho tantas de una misma organización: ninguna acapara la cola.
PETICIONES_POR_ORGANIZACION = 2
#: Tipos que van en su propio lote, uno por entidad: los escribe otra persona
#: (la biografía, el propio ponente) o tienen efecto legal (las políticas), y no
#: deben compartir llamada con el resto para que un texto no altere a otro.
TIPOS_AISLADOS: frozenset[TipoDeEntidad] = frozenset({"member_profile", "policy_version"})
#: Parte del límite mensual de IA que puede gastar la traducción (decisión del dueño).
FRACCION_DEL_LIMITE = Decimal("0.5")
#: Estados de un evento cuyo contenido se traduce: los borradores no.
ESTADOS_TRADUCIBLES = ("published", "cancelled")

#: Modelo → tipo de entidad, para el encolado automático al guardar.
_TIPO_DE_MODELO: dict[type, TipoDeEntidad] = {
    Event: "event",
    EventSession: "session",
    SessionType: "session_type",
    EventVenue: "venue",
    EventTicketType: "ticket_type",
    EventRegistrationQuestion: "question",
    SponsorTier: "sponsor_tier",
    Sponsor: "sponsor",
    OrganizationMember: "member_profile",
    Organization: "organization",
    OrganizationPolicyVersion: "policy_version",
    EventNearbyPlace: "nearby_place",
}
#: Atributos que, si cambian, piden traducción (además de los de `CAMPOS`).
_ATRIBUTOS_EXTRA: dict[TipoDeEntidad, tuple[str, ...]] = {
    "event": ("tags", "status", "visibility", "source_locale"),
    "question": ("options",),
    "member_profile": ("profile_data",),
    "organization": ("content_locales", "source_locale"),
}


@dataclass(frozen=True)
class Ambito:
    organization_id: uuid.UUID
    event_id: uuid.UUID | None
    locale: Locale


def marca_en_cola(ambito: Ambito) -> str:
    """Clave de Redis que dice que hay una traducción al vuelo a punto de arrancar."""
    return f"traduccion-en-cola:{ambito.organization_id}:{ambito.event_id}:{ambito.locale}"


# ── Qué se traduce ──────────────────────────────────────────────────────────


async def _entidades(
    session: AsyncSession, organizacion: Organization, event_id: uuid.UUID | None
) -> list[panel.Entidad] | None:
    """Las entidades del ámbito, o `None` si no se traduce (evento en borrador)."""
    activos = await idiomas_de_contenido(session, organizacion)
    origen_org = normalizar_locale(organizacion.source_locale)

    def entidad(
        tipo: TipoDeEntidad, fila: Any, ev: uuid.UUID | None, origen: Locale
    ) -> panel.Entidad:
        return panel.Entidad(
            tipo=tipo,
            fila=fila,
            event_id=ev,
            origen=origen,
            origen_organizacion=origen_org,
            activos=activos,
        )

    if event_id is None:
        resultado = [entidad("organization", organizacion, None, origen_org)]
        de_organizacion: tuple[tuple[TipoDeEntidad, Any], ...] = (
            ("session_type", SessionType),
            ("sponsor_tier", SponsorTier),
        )
        for tipo, modelo in de_organizacion:
            filas = await session.scalars(
                select(modelo).where(modelo.organization_id == organizacion.id)
            )
            resultado += [entidad(tipo, fila, None, origen_org) for fila in filas]
        # Perfiles con página pública de ponente: los demás no se muestran.
        miembros = await session.scalars(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organizacion.id,
                OrganizationMember.id.in_(
                    select(SpeakerPublicProfile.source_organization_member_id).where(
                        SpeakerPublicProfile.organization_id == organizacion.id
                    )
                ),
            )
        )
        resultado += [entidad("member_profile", m, None, origen_org) for m in miembros]
        # Última versión de cada política general.
        politicas = await session.scalars(
            select(OrganizationPolicyVersion)
            .where(
                OrganizationPolicyVersion.organization_id == organizacion.id,
                OrganizationPolicyVersion.event_id.is_(None),
            )
            .distinct(OrganizationPolicyVersion.kind)
            .order_by(OrganizationPolicyVersion.kind, OrganizationPolicyVersion.version.desc())
        )
        resultado += [entidad("policy_version", p, None, origen_org) for p in politicas]
        return resultado

    evento = await session.get(Event, event_id)
    if evento is None or evento.status not in ESTADOS_TRADUCIBLES:
        return None
    origen = normalizar_locale(evento.source_locale)
    resultado = [entidad("event", evento, evento.id, origen)]
    hijos: tuple[tuple[TipoDeEntidad, Any], ...] = (
        ("session", EventSession),
        ("venue", EventVenue),
        ("ticket_type", EventTicketType),
        ("question", EventRegistrationQuestion),
        ("sponsor", Sponsor),
        ("nearby_place", EventNearbyPlace),
    )
    for tipo, modelo in hijos:
        filas = await session.scalars(
            select(modelo).where(
                modelo.organization_id == organizacion.id, modelo.event_id == evento.id
            )
        )
        resultado += [entidad(tipo, fila, evento.id, origen) for fila in filas]
    # Lo de la organización que se ve en la ficha: tipos de sesión y niveles usados.
    tipos = await session.scalars(
        select(SessionType).where(
            SessionType.id.in_(
                select(EventSession.session_type_id).where(EventSession.event_id == evento.id)
            )
        )
    )
    resultado += [entidad("session_type", t, None, origen_org) for t in tipos]
    niveles = await session.scalars(
        select(SponsorTier).where(
            SponsorTier.id.in_(select(Sponsor.tier_id).where(Sponsor.event_id == evento.id))
        )
    )
    resultado += [entidad("sponsor_tier", n, None, origen_org) for n in niveles]
    return resultado


# ── Límites ─────────────────────────────────────────────────────────────────


async def clave_propia(session: AsyncSession, organization_id: uuid.UUID) -> bool:
    """La organización tiene configurada su propia clave de IA. La traducción
    nunca usa la de la plataforma (decisión del dueño)."""
    config = await ai_service.resolver_config_efectiva(session, organization_id)
    return config.origen == "propia" and config.usable


async def _queda_presupuesto(session: AsyncSession, organization_id: uuid.UUID) -> bool:
    """La traducción no ha gastado ya su parte del límite mensual de IA."""
    config = await ai_service.resolver_config_efectiva(session, organization_id)
    if config.limite_efectivo_usd is None:
        return True
    inicio, fin = ai_repository.rango_del_periodo(ai_repository.periodo_actual())
    gastado = await session.scalar(
        select(func.coalesce(func.sum(AiUsageRecord.cost_usd), 0)).where(
            AiUsageRecord.organization_id == organization_id,
            AiUsageRecord.use_case == ia.USE_CASE,
            AiUsageRecord.status.in_(ESTADOS_QUE_GASTAN),
            AiUsageRecord.created_at >= inicio,
            AiUsageRecord.created_at < fin,
        )
    )
    return Decimal(gastado or 0) < config.limite_efectivo_usd * FRACCION_DEL_LIMITE


# ── Reserva y escritura ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Reservado:
    fila_id: uuid.UUID
    campo: panel.Campo
    firma: str
    origen: Locale


def _necesita(fila: ContentTranslation | None, original: str, ahora: datetime) -> bool:
    if fila is None:
        return True
    if fila.origin != "ia":
        return False  # Manual o revisada: la IA no la toca.
    if fila.status == "al_dia" and fila.source_hash == huella(original):
        return False
    if fila.status == "en_curso" and fila.updated_at > ahora - RESERVA_CADUCA:
        return False
    return not (fila.status == "error" and fila.retry_after and fila.retry_after > ahora)


async def _reservar(
    session: AsyncSession, ambito: Ambito, entidades: Sequence[panel.Entidad]
) -> list[_Reservado]:
    """Reserva los campos que necesitan traducción al idioma del ámbito."""
    ahora = datetime.now(UTC)
    campos: list[tuple[panel.Entidad, panel.Campo]] = []
    for entidad in entidades:
        if ambito.locale not in entidad.activos:
            return []
        for campo in await panel.campos_de(session, entidad):
            if entidad.origen_de(campo) != ambito.locale:
                campos.append((entidad, campo))
    existentes = await panel._filas(  # noqa: SLF001 - misma consulta en lote que el panel
        session, ambito.organization_id, [c for _, c in campos], [ambito.locale]
    )
    reservados: list[_Reservado] = []
    vistos: set[tuple[str, uuid.UUID, str]] = set()
    for entidad, campo in campos:
        clave = (campo.tipo, campo.entity_id, campo.campo)
        if clave in vistos:
            continue
        vistos.add(clave)
        if not _necesita(existentes.get((*clave, ambito.locale)), campo.original, ahora):
            continue
        if len(campo.original) > CARACTERES_MAXIMOS_IA:
            continue
        firma = huella(campo.original)
        event_id = None if campo.tipo in TIPOS_DE_ORGANIZACION else entidad.event_id
        valores = {
            "value": "",
            "origin": "ia",
            "status": "en_curso",
            "source_hash": firma,
            "updated_at": ahora,
            "updated_by": None,
        }
        sentencia = (
            insert(ContentTranslation)
            .values(
                id=uuid.uuid4(),
                organization_id=ambito.organization_id,
                event_id=event_id,
                entity_type=campo.tipo,
                entity_id=campo.entity_id,
                field=campo.campo,
                locale=ambito.locale,
                **valores,
            )
            .on_conflict_do_update(
                constraint="uq_content_translations_campo",
                # Sin tocar `value`: si alguien la marcara como revisada a mitad
                # de camino, nunca quedaría un texto vacío.
                set_={k: v for k, v in valores.items() if k != "value"},
                # Carrera con otra tarea o con el organizador: solo se reserva si
                # sigue siendo de la IA y nadie la tiene reservada.
                where=(ContentTranslation.origin == "ia")
                & or_(
                    ContentTranslation.status != "en_curso",
                    ContentTranslation.updated_at <= ahora - RESERVA_CADUCA,
                ),
            )
            .returning(ContentTranslation.id)
        )
        fila_id = (await session.execute(sentencia)).scalar_one_or_none()
        if fila_id is not None:
            reservados.append(_Reservado(fila_id, campo, firma, entidad.origen_de(campo)))
    return reservados


async def _escribir(
    organization_id: uuid.UUID,
    resultados: dict[uuid.UUID, tuple[str | None, str]],
    *,
    liberar: Sequence[uuid.UUID] = (),
) -> None:
    """Guarda las traducciones (o el error) de los campos reservados.

    `resultados` va por fila: (traducción o `None`, firma del original que se
    tradujo). Solo escribe sobre filas que siguen reservadas **por esta tarea**:
    si otra la reservó después (con otra firma), esta traducción ya es vieja."""
    ahora = datetime.now(UTC)
    async with SessionApp() as session, session.begin():
        await set_organization_context(session, organization_id)
        for fila_id, (valor, firma) in resultados.items():
            fila = await session.get(ContentTranslation, fila_id, with_for_update=True)
            if (
                fila is None
                or fila.status != "en_curso"
                or fila.origin != "ia"
                or fila.source_hash != firma
            ):
                continue
            if valor is not None:
                fila.value, fila.status, fila.error_count, fila.retry_after = (
                    valor,
                    "al_dia",
                    0,
                    None,
                )
            else:
                fila.error_count += 1
                fila.status = "error"
                fila.retry_after = ahora + timedelta(minutes=min(2**fila.error_count, 24 * 60))
            fila.updated_at = ahora
        if liberar:
            await session.execute(
                update(ContentTranslation)
                .where(
                    ContentTranslation.id.in_(list(liberar)),
                    ContentTranslation.status == "en_curso",
                )
                .values(status="pendiente", updated_at=ahora)
            )


async def pendientes(
    session: AsyncSession, organizacion: Organization, ambito: Ambito
) -> list[tuple[panel.Campo, Locale]]:
    """Los textos del ámbito que la IA traduciría ahora, con su idioma de origen
    (sin reservarlos). Para estimar el coste antes de pedir la traducción."""
    entidades = await _entidades(session, organizacion, ambito.event_id)
    if not entidades:
        return []
    ahora = datetime.now(UTC)
    campos = [
        (entidad, campo)
        for entidad in entidades
        if ambito.locale in entidad.activos
        for campo in await panel.campos_de(session, entidad)
        if entidad.origen_de(campo) != ambito.locale
    ]
    existentes = await panel._filas(  # noqa: SLF001
        session, ambito.organization_id, [c for _, c in campos], [ambito.locale]
    )
    vistos: set[tuple[str, uuid.UUID, str]] = set()
    resultado = []
    for entidad, campo in campos:
        clave = (campo.tipo, campo.entity_id, campo.campo)
        if clave in vistos:
            continue
        vistos.add(clave)
        if len(campo.original) <= CARACTERES_MAXIMOS_IA and _necesita(
            existentes.get((*clave, ambito.locale)), campo.original, ahora
        ):
            resultado.append((campo, entidad.origen_de(campo)))
    return resultado


async def coste_estimado(
    session: AsyncSession,
    organization_id: uuid.UUID,
    textos: Sequence[tuple[panel.Campo, Locale]],
    destino: Locale,
) -> Decimal | None:
    """Coste orientativo de traducir `textos` con el modelo de la organización,
    o `None` si no hay configuración usable."""
    config = await ai_service.resolver_config_efectiva(session, organization_id)
    if not config.usable or config.provider is None or config.default_model is None:
        return None
    from app.modules.ai_gateway import client as ai_client

    modelo = ai_client.modelo_de_litellm(config.provider, config.default_model)
    total = Decimal(0)
    for origen in {o for _, o in textos}:
        lista = [
            ia.Texto(f"t{i}", c.original, ia.es_de_una_linea(c.tipo, c.campo))
            for i, (c, o) in enumerate(textos)
            if o == origen
        ]
        for lote in ia.lotes(lista):
            caracteres = sum(len(t.original) for t in lote)
            total += ai_client.estimar_coste(
                model_litellm=modelo,
                messages=ia.mensajes(lote, origen, destino, []),
                # La salida ronda la entrada: unos 3-4 caracteres por token.
                max_tokens=caracteres // 3 + 50,
            )
    return total


# ── Procesado de un ámbito ──────────────────────────────────────────────────


async def procesar(ambito: Ambito) -> int:
    """Traduce lo pendiente de un ámbito. Devuelve cuántos campos ha traducido.

    No propaga errores: un fallo deja los campos en `error` (con espera) o los
    libera, y se sirve el original.
    """
    async with SessionApp() as session, session.begin():
        await set_organization_context(session, ambito.organization_id)
        organizacion = await session.get(Organization, ambito.organization_id)
        if organizacion is None or not await clave_propia(session, ambito.organization_id):
            return 0
        entidades = await _entidades(session, organizacion, ambito.event_id)
        if not entidades:
            return 0
        reservados = await _reservar(session, ambito, entidades)
        no_traducir = [organizacion.name] + [e.fila.name for e in entidades if e.tipo == "sponsor"]
    if not reservados:
        return 0

    traducidos = 0
    por_clave = {f"t{i}": r for i, r in enumerate(reservados)}
    pendientes = set(por_clave)
    sin_presupuesto = False
    # Grupos: un lote no mezcla idiomas de origen (un evento en inglés puede
    # tener etiquetas en el idioma de la organización), y los tipos aislados van
    # cada entidad en su propio lote.
    grupos: dict[tuple[str, uuid.UUID | None], list[str]] = {}
    for clave, r in por_clave.items():
        aislado = r.campo.entity_id if r.campo.tipo in TIPOS_AISLADOS else None
        grupos.setdefault((r.origen, aislado), []).append(clave)
    for (origen, _aislado), claves in sorted(grupos.items(), key=lambda g: str(g[0])):
        textos = [
            ia.Texto(
                clave,
                por_clave[clave].campo.original,
                ia.es_de_una_linea(por_clave[clave].campo.tipo, por_clave[clave].campo.campo),
            )
            for clave in claves
        ]
        for lote in ia.lotes(textos):
            async with SessionApp() as session, session.begin():
                await set_organization_context(session, ambito.organization_id)
                hay_presupuesto = await _queda_presupuesto(session, ambito.organization_id)
            if not hay_presupuesto:
                sin_presupuesto = True
                break
            try:
                salida = await ia.traducir(
                    ambito.organization_id,
                    lote,
                    normalizar_locale(origen),
                    ambito.locale,
                    no_traducir,
                )
            except Exception:
                logger.warning("La traducción de un lote ha fallado.", exc_info=True)
                salida = {texto.clave: None for texto in lote}
            await _escribir(
                ambito.organization_id,
                {por_clave[c].fila_id: (v, por_clave[c].firma) for c, v in salida.items()},
            )
            traducidos += sum(1 for v in salida.values() if v is not None)
            pendientes -= set(salida)
        if sin_presupuesto:
            break
    if pendientes:
        # Sin presupuesto: se liberan para otra ocasión, sin marcarlos como error.
        await _escribir(
            ambito.organization_id, {}, liberar=[por_clave[c].fila_id for c in pendientes]
        )
    if not sin_presupuesto:
        await _volver_a_pedir_si_queda_algo(ambito)
    return traducidos


async def _volver_a_pedir_si_queda_algo(ambito: Ambito) -> None:
    """Si mientras se traducía cambió algún original, o había campos reservados
    por otra tarea, se vuelve a apuntar el ámbito: el barrido lo recogerá. Lo que
    está en espera por error no cuenta, así que no hay bucle."""
    async with SessionApp() as session, session.begin():
        await set_organization_context(session, ambito.organization_id)
        organizacion = await session.get(Organization, ambito.organization_id)
        quedan = await pendientes(session, organizacion, ambito) if organizacion is not None else []
    if quedan:
        await pedir(ambito.organization_id, ambito.event_id, [ambito.locale])


# ── Peticiones: encolar y barrer ────────────────────────────────────────────


async def pedir(
    organization_id: uuid.UUID,
    event_id: uuid.UUID | None,
    locales: Sequence[Locale],
    *,
    ahora: datetime | None = None,
) -> None:
    """Apunta (o renueva) la petición de traducir un ámbito a unos idiomas."""
    if not locales:
        return
    momento = ahora or datetime.now(UTC)
    async with SessionMaintenance() as session, session.begin():
        for locale in locales:
            existente = await session.scalar(
                select(TranslationRequest).where(
                    TranslationRequest.organization_id == organization_id,
                    TranslationRequest.event_id.is_(None)
                    if event_id is None
                    else TranslationRequest.event_id == event_id,
                    TranslationRequest.locale == locale,
                )
            )
            if existente is None:
                session.add(
                    TranslationRequest(
                        organization_id=organization_id,
                        event_id=event_id,
                        locale=locale,
                        requested_at=momento,
                    )
                )
            else:
                existente.requested_at = momento


async def barrer(encolar: Callable[[Ambito], Awaitable[object]]) -> int:
    """Encola las peticiones que llevan un rato quietas y las borra.

    Como mucho `PETICIONES_POR_BARRIDO`, y no más de `PETICIONES_POR_ORGANIZACION`
    de una misma organización, para que ninguna acapare la cola. Cada fila se
    borra **después** de encolarla y en la misma transacción: si encolar falla
    (Redis caído), la petición sigue ahí para el siguiente barrido.
    """
    limite = datetime.now(UTC) - DEBOUNCE
    orden = (
        func.row_number()
        .over(
            partition_by=TranslationRequest.organization_id,
            order_by=TranslationRequest.requested_at,
        )
        .label("orden")
    )
    candidatas = (
        select(TranslationRequest.id, orden)
        .where(TranslationRequest.requested_at <= limite)
        .subquery()
    )
    encoladas = 0
    async with SessionMaintenance() as session, session.begin():
        filas = (
            await session.scalars(
                select(TranslationRequest)
                .where(
                    TranslationRequest.id.in_(
                        select(candidatas.c.id).where(
                            candidatas.c.orden <= PETICIONES_POR_ORGANIZACION
                        )
                    )
                )
                .order_by(TranslationRequest.requested_at)
                .limit(PETICIONES_POR_BARRIDO)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for fila in filas:
            try:
                await encolar(
                    Ambito(fila.organization_id, fila.event_id, normalizar_locale(fila.locale))
                )
            except Exception:
                logger.warning("No se ha podido encolar una traducción.", exc_info=True)
                continue
            await session.delete(fila)
            encoladas += 1
    return encoladas


# ── Encolado automático al guardar ──────────────────────────────────────────


def _ambito_de(obj: Any) -> tuple[uuid.UUID, uuid.UUID | None] | None:
    tipo = _TIPO_DE_MODELO.get(type(obj))
    if tipo is None:
        return None
    if tipo == "organization":
        return obj.id, None
    if tipo == "event":
        return obj.organization_id, obj.id
    if tipo in TIPOS_DE_ORGANIZACION:
        return obj.organization_id, None
    return obj.organization_id, getattr(obj, "event_id", None)


def _cambia_algo_traducible(obj: Any, nuevo: bool) -> bool:
    if nuevo:
        return True
    tipo = _TIPO_DE_MODELO[type(obj)]
    estado = inspect(obj)
    atributos = set(CAMPOS[tipo]) | set(_ATRIBUTOS_EXTRA.get(tipo, ()))
    return any(
        nombre in estado.attrs and estado.attrs[nombre].history.has_changes()
        for nombre in atributos
    )


_AMBITOS = "traducir_tras_commit"


def _al_hacer_flush(session: Session, _contexto: object) -> None:
    nuevos = {
        ambito
        for obj in list(session.new) + list(session.dirty)
        if type(obj) in _TIPO_DE_MODELO
        and (ambito := _ambito_de(obj)) is not None
        and _cambia_algo_traducible(obj, obj in session.new)
    }
    if not nuevos:
        return
    session.info.setdefault(_AMBITOS, set()).update(nuevos)
    accion = session.info.setdefault("traducir_accion", lambda: _pedir_tras_commit(session))
    # Si un rollback descartó la cola «tras commit», se vuelve a apuntar.
    if accion not in session.info.get("tras_commit", []):
        encolar_tras_commit(session, accion)  # type: ignore[arg-type]


def _al_deshacer(session: Session, _transaccion: object) -> None:
    """Lo que se deshace no se traduce."""
    session.info.pop(_AMBITOS, None)


async def _pedir_tras_commit(session: Any) -> None:
    ambitos: set[tuple[uuid.UUID, uuid.UUID | None]] = session.info.pop(_AMBITOS, set())
    for organization_id, event_id in ambitos:
        await pedir(organization_id, event_id, await _idiomas_a_traducir(organization_id, event_id))


async def _idiomas_a_traducir(
    organization_id: uuid.UUID, event_id: uuid.UUID | None
) -> list[Locale]:
    """Los idiomas a los que hay algo que traducir en el ámbito: los de la
    organización salvo aquel en que está escrito todo. Vacío si solo publica en
    uno, no tiene clave propia o el evento es un borrador."""
    async with SessionApp() as session, session.begin():
        await set_organization_context(session, organization_id)
        organizacion = await session.get(Organization, organization_id)
        if organizacion is None:
            return []
        activos = await idiomas_de_contenido(session, organizacion)
        if len(activos) < 2 or not await clave_propia(session, organization_id):
            return []
        origenes = {normalizar_locale(organizacion.source_locale)}
        if event_id is not None:
            evento = await session.get(Event, event_id)
            if evento is None or evento.status not in ESTADOS_TRADUCIBLES:
                return []
            origenes.add(normalizar_locale(evento.source_locale))
        # Un idioma que es el original de todo no tiene nada que traducir.
        return [locale for locale in activos if origenes - {locale}]


def instalar_encolado_automatico() -> None:
    """Engancha el listener a todas las sesiones (una vez, al importar la app)."""
    if not sa_event.contains(Session, "after_flush", _al_hacer_flush):
        sa_event.listen(Session, "after_flush", _al_hacer_flush)
        sa_event.listen(Session, "after_soft_rollback", _al_deshacer)
