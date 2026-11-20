"""Servicios del evento: alta, edición, portada y transiciones de estado.

Valida lo que el esquema Pydantic no puede: unicidad de slug en base de datos,
que la venta sea posible al publicar, y las transiciones de estado válidas
(`archived` es terminal). La agenda vive en `agenda`, las sedes en `sedes` y
la lectura pública en `publico`.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.mensajes import marcar
from app.core.permissions import Permission
from app.core.storage import public_url_versionada
from app.modules.events import categories, repository
from app.modules.events.geocoding import geocodificar_para_guardar
from app.modules.events.models import (
    Event,
)
from app.modules.media import service as media_service
from app.modules.organizations.models import Organization
from app.modules.payments import repository as payments_repository
from app.modules.payments import service as payments_service
from app.modules.registrations import modo_y_aforo
from app.modules.registrations import repository as registrations_repository
from app.modules.registrations import service as registrations_service
from app.modules.theme_templates.models import ThemeTemplate
from app.shared.errors import ConflictError, NotFoundError, ValidationDomainError

_INTENTOS_DE_SUGERENCIA = 50


async def _slug_repetido(session: AsyncSession, organization_id: uuid.UUID, slug: str) -> Exception:
    """Conflicto de slug con el primer libre de la forma `slug-2`, `slug-3`… como sugerencia."""
    candidato = ""
    for numero in range(2, _INTENTOS_DE_SUGERENCIA + 2):
        sufijo = f"-{numero}"
        candidato = f"{slug[: 160 - len(sufijo)]}{sufijo}"
        if await repository.get_event_by_slug(session, organization_id, candidato) is None:
            break
    else:
        # Todos los cercanos están ocupados: un sufijo aleatorio evita seguir consultando.
        sufijo = f"-{secrets.token_hex(3)}"
        candidato = f"{slug[: 160 - len(sufijo)]}{sufijo}"
    return ConflictError(
        "Ya existe un evento con el identificador «{slug}» en tu organización.",
        params={"slug": slug},
        extra={"suggested_slug": candidato},
    )


async def _asegurar_slug_disponible(
    session: AsyncSession, organization_id: uuid.UUID, slug: str
) -> None:
    existente = await repository.get_event_by_slug(session, organization_id, slug)
    if existente is not None:
        raise await _slug_repetido(session, organization_id, slug)


async def _asegurar_venta_posible(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    status: str,
    registration_mode: str,
    event_id: uuid.UUID | None = None,
) -> None:
    """Bloquea la **venta**, no la configuración (decisión #13 del plan de
    la fase 6 del PRD): crear y editar un evento `paid` sigue permitido en
    borrador, mientras el organizador completa el KYC de Stripe, que puede
    tardar días. Lo único que exige `charges_enabled = true` es que el
    resultante sea `published` **y** `paid` a la vez.

    Invocada desde `create_event` **y** `update_event`: `create_event` no
    validaba nada de estado y aceptaba un
    evento ya `published`/`paid` de alta, así que la guarda no puede vivir
    solo en la edición.

    `event_id` solo llega desde `update_event` (`create_event` no tiene
    todavía una fila de evento sobre la que colgar tipos de entrada). Con él,
    exige al menos un tipo de entrada activo cuya venta no haya terminado,
    aunque empiece más tarde: anunciar un evento antes de abrir la venta es lo
    habitual, y la ficha pública dice cuándo abre (`ticket_sales`).
    """
    if status != "published" or registration_mode != "paid":
        return

    settings = get_settings()
    if not settings.payments_enabled:
        raise ConflictError(
            "No se puede publicar un evento de pago: esta instalación no tiene Stripe configurado."
        )

    cuenta = await payments_repository.get_cuenta_activa(session, organization_id)
    if cuenta is None or not cuenta.charges_enabled:
        raise ConflictError(
            "No se puede publicar un evento de pago hasta conectar una cuenta de Stripe "
            "y completar su verificación."
        )

    if event_id is not None:
        ahora = datetime.now(UTC)
        tipos = await payments_repository.get_ticket_types(session, organization_id, event_id)
        if not any(payments_service.tipo_puede_venderse_aun(tipo, ahora) for tipo in tipos):
            raise ConflictError(
                "No se puede publicar un evento de pago sin ningún tipo de entrada a la venta "
                "ni pendiente de abrir."
            )


async def _sincronizar_geocodificacion_evento(
    evento: Event, *, location_mode: str, address: str | None, direccion_anterior: str | None
) -> None:
    """Geocodifica `Event.location_address` con el mismo mecanismo que
    `EventVenue.address` (decisión #4 del encargo: un único mecanismo de
    dirección+geocodificación para ambos). Solo llama a Nominatim cuando la
    dirección cambió (o nunca se geocodificó) respecto al valor guardado — la
    comparación vive aquí, `geocode_address` es una función pura sin acceso a
    base de datos."""
    if location_mode == "online" or not address:
        evento.latitude = None
        evento.longitude = None
        evento.geocoded_at = None
        return
    if address == direccion_anterior and evento.geocoded_at is not None:
        return
    resultado = await geocodificar_para_guardar(address)
    if resultado is None:
        evento.latitude = None
        evento.longitude = None
        evento.geocoded_at = None
        return
    evento.latitude, evento.longitude, evento.geocoded_at = resultado


def _validar_idioma_de_origen(organizacion: Organization, idioma: str) -> None:
    if idioma not in (organizacion.content_locales or []):
        raise ValidationDomainError("La organización no publica en ese idioma.")


async def create_event(
    session: AsyncSession, *, organization_id: uuid.UUID, datos: dict[str, Any]
) -> Event:
    await _asegurar_slug_disponible(session, organization_id, datos["slug"])
    if "category_id" in datos:
        datos = {
            **datos,
            "category_id": await categories.resolver_categoria_del_evento(
                session, datos["category_id"]
            ),
        }

    # 48 h en los de pago: con el plazo de reembolso de 24 h, a tiempo de
    # cancelar con devolución desde el propio recordatorio.
    if datos.get("reminder_hours_before") is None:
        datos = {
            **datos,
            "reminder_hours_before": 48 if datos.get("registration_mode") == "paid" else 24,
        }
    organizacion = await session.get(Organization, organization_id)
    if datos.get("source_locale") is None:
        # El evento se escribe, por defecto, en el idioma de su organización.
        datos = {
            **datos,
            "source_locale": organizacion.source_locale if organizacion else "es-ES",
        }
    elif organizacion is not None:
        _validar_idioma_de_origen(organizacion, datos["source_locale"])
    evento = Event(organization_id=organization_id, **datos)
    try:
        # Punto de guardado: tras un `IntegrityError` la transacción sigue
        # utilizable y se puede calcular la sugerencia de slug.
        async with session.begin_nested():
            session.add(evento)
            await session.flush()
    except IntegrityError as exc:
        # La comprobación de arriba ya cubre el caso normal; esto es la carrera
        # entre dos altas simultáneas con el mismo slug dentro de la organización.
        raise await _slug_repetido(session, organization_id, datos["slug"]) from exc

    # `event_id=evento.id` tras el `flush` (no antes de crearlo, como hacía
    # esta llamada originalmente): sin él, un alta directa con
    # `status=published`/`registration_mode=paid` se saltaba la exigencia de
    # al menos un tipo de entrada vigente, porque
    # `_asegurar_venta_posible` solo la comprueba cuando recibe `event_id`. Si
    # esto falla, el `session.begin()` de `get_db` deshace también el
    # `flush` de arriba: nunca queda un evento a medio crear.
    await _asegurar_venta_posible(
        session,
        organization_id,
        status=evento.status,
        registration_mode=evento.registration_mode,
        event_id=evento.id,
    )
    await _sincronizar_geocodificacion_evento(
        evento,
        location_mode=evento.location_mode,
        address=evento.location_address,
        direccion_anterior=None,
    )
    await session.flush()
    await session.refresh(evento, ["category"])
    return evento


def _validar_transicion_de_estado(actual: str, nuevo: str) -> None:
    if actual == "archived" and nuevo != "archived":
        raise ValidationDomainError("Un evento archivado no puede volver a editarse.")
    if nuevo == "cancelled":  # pragma: no cover - el schema de entrada ya lo impide
        raise ValidationDomainError("Para cancelar un evento usa la acción «Cancelar evento».")


async def _resolver_plantilla_del_evento(
    session: AsyncSession, valor: str | None
) -> uuid.UUID | None:
    """Traduce la plantilla que llega del panel al id que va a la columna.

    Cadena vacía o `None` significan **heredar** (la columna queda `NULL`), que
    es como se deshace una elección. Cualquier otra cosa tiene que ser el id de
    una plantilla del catálogo: si no es un id o no existe, se rechaza con un
    mensaje legible en vez de dejar que reviente la base de datos.
    """
    if not valor:
        return None
    try:
        plantilla_id = uuid.UUID(valor)
    except (ValueError, AttributeError) as exc:
        raise ValidationDomainError("La plantilla indicada no es válida.") from exc

    existe = await session.scalar(select(ThemeTemplate.id).where(ThemeTemplate.id == plantilla_id))
    if existe is None:
        raise ValidationDomainError("La plantilla indicada no existe.")
    return plantilla_id


def _al_minuto(momento: datetime) -> datetime:
    return momento.replace(second=0, microsecond=0)


#: Código del 409 que el formulario del evento reconoce para preguntar si mover
#: las sesiones con el evento (distinto de otros 409, que no se preguntan).
CODIGO_SESIONES_FUERA_DE_RANGO = "sesiones_fuera_de_rango"
_TITULOS_EN_EL_AVISO = 5
#: Aviso de sesiones que quedarían fuera, según se muevan con el evento (`True`)
#: o no, y según sean una, varias o más de las que se listan.
_AVISOS_DE_SESIONES_FUERA: dict[bool, dict[str, str]] = {
    True: {
        "una": marcar(
            "Aun moviéndolas con el evento, 1 sesión quedaría fuera de sus nuevas fechas: "
            "{lista}. Ajústalas en la agenda o amplía el evento."
        ),
        "plural": marcar(
            "Aun moviéndolas con el evento, {total} sesiones quedarían fuera de sus nuevas "
            "fechas: {lista}. Ajústalas en la agenda o amplía el evento."
        ),
        "plural_y_mas": marcar(
            "Aun moviéndolas con el evento, {total} sesiones quedarían fuera de sus nuevas "
            "fechas: {lista} y {restantes} más. Ajústalas en la agenda o amplía el evento."
        ),
    },
    False: {
        "una": marcar(
            "Con las fechas nuevas, 1 sesión de la agenda quedaría fuera del evento: {lista}."
        ),
        "plural": marcar(
            "Con las fechas nuevas, {total} sesiones de la agenda quedarían fuera del evento: "
            "{lista}."
        ),
        "plural_y_mas": marcar(
            "Con las fechas nuevas, {total} sesiones de la agenda quedarían fuera del evento: "
            "{lista} y {restantes} más."
        ),
    },
}


async def _ajustar_sesiones_al_rango(
    session: AsyncSession,
    evento: Event,
    inicio: datetime,
    fin: datetime,
    *,
    mover: bool,
) -> None:
    """Con las fechas nuevas, ninguna sesión puede quedar fuera del evento.

    Con `mover`, todas se desplazan lo mismo que el inicio (aplazar una semana
    mueve la agenda entera). Si aun así alguna queda fuera (el evento se
    acortó) o no se pidió mover, 409 con cuántas y cuáles: no se guarda nada,
    porque la excepción revierte también lo que se haya movido.
    """
    sesiones = (
        (await session.execute(repository.sessions_query(evento.organization_id, evento.id)))
        .scalars()
        .all()
    )
    # Solo cuentan las que hoy caen dentro: una sesión que ya estaba fuera
    # (anterior a esta regla) no bloquea cambiar las fechas del evento.
    dentro_antes = {
        sesion.id
        for sesion in sesiones
        if evento.starts_at <= sesion.starts_at and sesion.ends_at <= evento.ends_at
    }
    if mover:
        desplazamiento = inicio - evento.starts_at
        for sesion in sesiones:
            sesion.starts_at += desplazamiento
            sesion.ends_at += desplazamiento
    fuera = [
        sesion
        for sesion in sesiones
        if sesion.id in dentro_antes and (sesion.starts_at < inicio or sesion.ends_at > fin)
    ]
    if not fuera:
        return
    titulos = [sesion.title for sesion in fuera[:_TITULOS_EN_EL_AVISO]]
    restantes = len(fuera) - len(titulos)
    plural = "plural_y_mas" if restantes else ("plural" if len(fuera) > 1 else "una")
    raise ConflictError(
        _AVISOS_DE_SESIONES_FUERA[mover][plural],  # mensaje marcado
        params={
            "total": len(fuera),
            "lista": ", ".join(f"«{titulo}»" for titulo in titulos),
            "restantes": restantes,
        },
        extra={
            "code": CODIGO_SESIONES_FUERA_DE_RANGO,
            "sesiones_fuera": len(fuera),
            "titulos": titulos,
            "movidas": mover,
        },
    )


async def update_event(
    session: AsyncSession, *, organization_id: uuid.UUID, event_id: uuid.UUID, datos: dict[str, Any]
) -> Event:
    # No es un campo del evento: el `setattr` genérico de más abajo no debe verlo.
    mover_sesiones = bool(datos.pop("mover_sesiones", False))
    evento = await repository.get_event(session, organization_id, event_id)
    if evento is None:
        raise NotFoundError("El evento no existe.")
    if evento.status == "cancelled":
        raise ValidationDomainError("Un evento cancelado no puede volver a editarse.")
    if "source_locale" in datos:
        if datos["source_locale"] is None:
            datos.pop("source_locale")
        else:
            organizacion = await session.get(Organization, organization_id)
            if organizacion is not None:
                _validar_idioma_de_origen(organizacion, datos["source_locale"])

    nuevo_slug = datos.get("slug")
    if nuevo_slug is not None and nuevo_slug != evento.slug:
        await _asegurar_slug_disponible(session, organization_id, nuevo_slug)

    nuevo_estado = datos.get("status")
    if nuevo_estado is not None and nuevo_estado != evento.status:
        _validar_transicion_de_estado(evento.status, nuevo_estado)

    # `contingency_fund_percent` es el único campo de contabilidad editable
    # desde `EventUpdate` (plan.md Decisión #6) y solo mientras el
    # presupuesto no esté aprobado: una vez aprobado, `contingency_fund_cents`
    # ya está dotado sobre el porcentaje congelado en ese momento — cambiar el
    # porcentaje después desincronizaría el fondo ya dotado del que se
    # recalcularía en la siguiente aprobación, sin que nadie lo audite (esa
    # auditoría vive en `accounting.aprobar_presupuesto`/`reabrir_presupuesto`,
    # no aquí).
    if "contingency_fund_percent" in datos and evento.budget_approved_at is not None:
        raise ConflictError(
            "El fondo de contingencia ya está aprobado; reabre el presupuesto "
            "antes de cambiar el porcentaje."
        )

    # Evaluado sobre el evento **resultante**, no el actual: un `PATCH` que
    # cambia `status` y `registration_mode` a la vez debe quedar bloqueado
    # igual que si cada campo se editara por separado. Solo al **entrar** en
    # publicado y de pago: un evento que ya vendía se puede seguir editando
    # (una errata, el aforo) aunque su venta haya terminado.
    if not (evento.status == "published" and evento.registration_mode == "paid"):
        await _asegurar_venta_posible(
            session,
            organization_id,
            status=datos.get("status", evento.status),
            registration_mode=datos.get("registration_mode", evento.registration_mode),
            event_id=evento.id,
        )

    inicio = datos.get("starts_at", evento.starts_at)
    fin = datos.get("ends_at", evento.ends_at)
    if fin <= inicio:
        raise ValidationDomainError("La fecha de fin debe ser posterior a la de inicio.")
    # Al minuto: el formulario envía las fechas sin segundos, y unos segundos
    # guardados por la API o el MCP no son un cambio de fechas.
    if _al_minuto(inicio) != _al_minuto(evento.starts_at) or _al_minuto(fin) != _al_minuto(
        evento.ends_at
    ):
        await _ajustar_sesiones_al_rango(session, evento, inicio, fin, mover=mover_sesiones)

    # Se comparan contra el valor actual, no por presencia de la clave: el
    # formulario del panel los envía siempre, y reenviar el mismo valor no es
    # un cambio que haya que validar. Con cambio real se toma el mismo
    # bloqueo de aforo que las altas, verificaciones y aprobaciones, para que
    # ninguna se cuele entre el recuento y la escritura.
    if "registration_mode" in datos and datos["registration_mode"] is None:
        raise ValidationDomainError("Indica el modo de inscripción.")
    modo_cambia = (
        "registration_mode" in datos and datos["registration_mode"] != evento.registration_mode
    )
    aforo_cambia = "capacity" in datos and datos["capacity"] != evento.capacity
    # Al pasar a pago, el recordatorio por defecto (24 h) llegaría justo al
    # cerrarse el plazo de reembolso: se adelanta a 48 h si no se ha tocado.
    if (
        modo_cambia
        and datos["registration_mode"] == "paid"
        and "reminder_hours_before" not in datos
        and evento.reminder_hours_before == 24
    ):
        datos = {**datos, "reminder_hours_before": 48}
    if modo_cambia or aforo_cambia:
        await registrations_repository.lock_event_for_capacity(session, organization_id, evento.id)
        if modo_cambia:
            await modo_y_aforo.asegurar_cambio_de_modo_posible(
                session, evento, datos["registration_mode"]
            )
        if aforo_cambia and datos["capacity"] is not None:
            await modo_y_aforo.asegurar_aforo_posible(session, evento, datos["capacity"])

    direccion_anterior = evento.location_address

    # La plantilla del evento llega como cadena (o vacía, para volver a heredar)
    # y la columna es UUID: se traduce antes del `setattr` genérico, que si no
    # intentaría guardar texto en una columna de otro tipo.
    #
    # La validación ocurre **aquí y no en el `flush`**: un identificador que no
    # existe o mal formado saltaría como `IntegrityError`, y el `except` de
    # abajo lo reportaría como «ya existe un evento con ese identificador», que
    # no tiene nada que ver con lo que ha pasado.
    if "theme_template_id" in datos:
        evento.theme_template_id = await _resolver_plantilla_del_evento(
            session, datos.pop("theme_template_id")
        )

    categoria_cambiada = "category_id" in datos
    if categoria_cambiada:
        # `null` quita; ausencia no cambia (por eso solo se mira si viene). La
        # categoría que el evento ya tiene siempre es válida, esté o no activa.
        datos["category_id"] = await categories.resolver_categoria_del_evento(
            session, datos["category_id"], actual=evento.category_id
        )

    for campo, valor in datos.items():
        setattr(evento, campo, valor)

    await _sincronizar_geocodificacion_evento(
        evento,
        location_mode=evento.location_mode,
        address=evento.location_address,
        direccion_anterior=direccion_anterior,
    )

    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "Ya existe un evento con el identificador «{slug}».", params={"slug": nuevo_slug}
        ) from exc
    # Solo un evento publicado tiene a quién avisar: en borrador o archivado
    # la lista de espera no debe recibir ofertas de plaza.
    if aforo_cambia and evento.status == "published":
        await registrations_service.promover_lista_de_espera_hasta_llenar(session, evento)
    if categoria_cambiada:
        await session.refresh(evento, ["category"])
    return evento


async def set_cover_from_url(
    session: AsyncSession,
    *,
    evento: Event,
    url: str,
    uploaded_by_user_id: uuid.UUID,
    permisos: set[Permission],
) -> str:
    """Descarga una imagen por URL y la asigna como portada del evento —
    misma validación (SSRF, tamaño, formato) que cualquier importación a la
    biblioteca de medios, porque es `media_service.subir_desde_url` quien la
    hace. Es la vía que usa el MCP, que no puede mandar un fichero; el
    endpoint del panel la ofrece como alternativa al multipart y al
    `media_id` ya subido. Devuelve la URL pública de la nueva portada."""
    media = await media_service.subir_desde_url(
        session,
        organization_id=evento.organization_id,
        kind="events",
        uploaded_by_user_id=uploaded_by_user_id,
        permisos=permisos,
        url=url,
    )
    evento.cover_media_id = media.id
    evento.cover_object_key = None
    await session.flush()
    return public_url_versionada(media.object_key, media.updated_at)
