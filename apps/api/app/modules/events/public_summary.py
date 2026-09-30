"""Construcción de `PublicEventSummary`, compartida por los listados públicos."""

from __future__ import annotations

from app.modules.events.models import Event
from app.modules.events.schemas import PublicCategoryRef, PublicEventSummary
from app.modules.organizations.schemas import PublicOrganizationRef
from app.modules.payments import service as payments_service


def categoria_publica(evento: Event) -> PublicCategoryRef | None:
    """Solo se muestra una categoría activa: una desactivada deja de aparecer."""
    categoria = evento.category
    if categoria is None or not categoria.is_active:
        return None
    return PublicCategoryRef(slug=categoria.slug, name=categoria.name)


def resumen_publico(
    evento: Event,
    reservadas: int,
    precio: payments_service.PrecioPublico | None,
    cover_url: str | None,
    organizacion: PublicOrganizationRef,
) -> PublicEventSummary:
    return PublicEventSummary(
        slug=evento.slug,
        organization=organizacion,
        category=categoria_publica(evento),
        tags=list(evento.tags),
        cancelled=evento.status == "cancelled",
        title=evento.title,
        summary=evento.summary,
        cover_url=cover_url,
        timezone=evento.timezone,
        starts_at=evento.starts_at,
        ends_at=evento.ends_at,
        location_mode=evento.location_mode,  # type: ignore[arg-type]
        location_name=evento.location_name,
        city=evento.city,
        registration_mode=evento.registration_mode,  # type: ignore[arg-type]
        registration_opens_at=evento.registration_opens_at,
        capacity=evento.capacity,
        reserved_count=reservadas,
        price_from_cents=precio.tipo.price_cents if precio else None,
        price_currency=precio.tipo.currency if precio else None,
        price_multiple=precio.varios_precios if precio else False,
    )
