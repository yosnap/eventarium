"""Construcción de `PublicEventSummary`, compartida por los listados públicos."""

from __future__ import annotations

from typing import Any

from app.core.locale import Locale
from app.modules.events.models import Event
from app.modules.events.schemas import PublicCategoryRef, PublicEventSummary
from app.modules.organizations.schemas import PublicOrganizationRef
from app.modules.payments import service as payments_service
from app.modules.translations.service import Traductor, nombre_de_categoria


def categoria_publica(evento: Event, idioma: Locale) -> PublicCategoryRef | None:
    """Solo se muestra una categoría activa: una desactivada deja de aparecer."""
    categoria = evento.category
    if categoria is None or not categoria.is_active:
        return None
    return PublicCategoryRef(slug=categoria.slug, name=nombre_de_categoria(categoria, idioma))


def etiquetas_mostradas(evento: Event, tr: Traductor) -> dict[str, str]:
    """Etiqueta original → texto que se muestra. El original sigue siendo el
    identificador de filtros y URLs; solo se incluyen las que cambian."""
    mostradas = {valor: tr.etiqueta(evento.organization_id, valor) for valor in evento.tags}
    return {valor: texto for valor, texto in mostradas.items() if texto != valor}


def resumen_publico(
    evento: Event,
    reservadas: int,
    venta: payments_service.VentaPublica | None,
    cover_url: str | None,
    organizacion: PublicOrganizationRef,
    tr: Traductor,
) -> PublicEventSummary:
    return PublicEventSummary(
        slug=evento.slug,
        organization=organizacion,
        category=categoria_publica(evento, tr.idioma),
        tags=list(evento.tags),
        tag_labels=etiquetas_mostradas(evento, tr),
        cancelled=evento.status == "cancelled",
        title=tr.campo("event", evento.id, "title", evento.title) or evento.title,
        summary=tr.campo("event", evento.id, "summary", evento.summary),
        cover_url=cover_url,
        timezone=evento.timezone,
        starts_at=evento.starts_at,
        ends_at=evento.ends_at,
        location_mode=evento.location_mode,  # type: ignore[arg-type]
        location_name=tr.campo("event", evento.id, "location_name", evento.location_name),
        city=evento.city,
        registration_mode=evento.registration_mode,  # type: ignore[arg-type]
        registration_opens_at=evento.registration_opens_at,
        capacity=evento.capacity,
        reserved_count=reservadas,
        **campos_de_venta(evento, venta),
        **tr.metadatos(),
    )


def campos_de_venta(evento: Event, venta: payments_service.VentaPublica | None) -> dict[str, Any]:
    """Precio «desde» y estado de la venta para el resumen y la ficha públicos.

    La apertura que se anuncia es la más tardía entre la del tipo de entrada y
    la de la inscripción del evento (`registration_opens_at`): antes de ambas
    no se puede comprar, así que anunciar la primera prometería una hora en la
    que el formulario sigue cerrado.
    """
    precio = venta.precio if venta else None
    abre = venta.abre if venta else None
    if abre is not None and evento.registration_opens_at is not None:
        abre = max(abre, evento.registration_opens_at)
    return {
        "price_from_cents": precio.tipo.price_cents if precio else None,
        "price_currency": precio.tipo.currency if precio else None,
        "price_multiple": precio.varios_precios if precio else False,
        "ticket_sales": venta.estado if venta else None,
        "ticket_sales_opens_at": abre,
    }
