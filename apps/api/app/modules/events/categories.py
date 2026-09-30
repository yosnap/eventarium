"""Categorías (catálogo de instalación) y etiquetas de los eventos."""

from __future__ import annotations

import re
import uuid
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.events.models import EventCategory
from app.shared.errors import ValidationDomainError

MAX_ETIQUETAS = 5
MAX_ETIQUETAS_EN_UN_FILTRO = 3
LONGITUD_MIN_ETIQUETA = 2
LONGITUD_MAX_ETIQUETA = 30
# Letras (con tildes y ñ/ü), números, espacios y guiones; empieza y acaba por
# letra o número. Sin signos, sin emoji, sin `#`.
_ETIQUETA = re.compile(r"^[a-z0-9áéíóúüñ]+(?:[ -][a-z0-9áéíóúüñ]+)*$")


def normalizar_etiquetas(etiquetas: list[str]) -> list[str]:
    """Etiquetas en minúsculas, sin blancos de más ni repetidas, o `ValueError`.

    Se conserva el orden de la primera aparición. La comprobación del máximo se
    hace **después** de quitar repetidas: repetir una no cuenta dos veces.
    """
    limpias: list[str] = []
    for original in etiquetas:
        etiqueta = re.sub(r"\s+", " ", original.strip().lower())
        if not (LONGITUD_MIN_ETIQUETA <= len(etiqueta) <= LONGITUD_MAX_ETIQUETA):
            raise ValueError(
                f"Cada etiqueta debe tener entre {LONGITUD_MIN_ETIQUETA} y "
                f"{LONGITUD_MAX_ETIQUETA} caracteres («{original.strip()}»)."
            )
        if not _ETIQUETA.fullmatch(etiqueta):
            raise ValueError(
                "Las etiquetas solo admiten letras, números, espacios y guiones "
                f"(«{original.strip()}»)."
            )
        if etiqueta not in limpias:
            limpias.append(etiqueta)
    if len(limpias) > MAX_ETIQUETAS:
        raise ValueError(f"Un evento admite como máximo {MAX_ETIQUETAS} etiquetas.")
    return limpias


async def list_categories(
    session: AsyncSession, *, solo_activas: bool = False
) -> list[EventCategory]:
    consulta = select(EventCategory).order_by(EventCategory.display_order, EventCategory.name)
    if solo_activas:
        consulta = consulta.where(EventCategory.is_active.is_(True))
    return list(await session.scalars(consulta))


async def get_category(session: AsyncSession, category_id: uuid.UUID) -> EventCategory | None:
    return await session.get(EventCategory, category_id)


async def get_category_by_slug(session: AsyncSession, slug: str) -> EventCategory | None:
    return cast(
        "EventCategory | None",
        await session.scalar(select(EventCategory).where(EventCategory.slug == slug)),
    )


async def resolver_categoria_del_evento(
    session: AsyncSession, valor: str | None, *, actual: uuid.UUID | None = None
) -> uuid.UUID | None:
    """Traduce la categoría que llega del panel al id que va a la columna.

    `None` (o cadena vacía) **quita** la categoría. Solo se asignan categorías
    activas, con una excepción: la que el evento ya tiene (`actual`) siempre es
    válida, para que guardar otros cambios de un evento cuya categoría se
    desactivó no lo obligue a cambiarla ni se la borre en silencio.
    """
    if not valor:
        return None
    try:
        category_id = uuid.UUID(valor)
    except (ValueError, AttributeError) as exc:
        raise ValidationDomainError("La categoría indicada no es válida.") from exc
    if actual is not None and category_id == actual:
        return category_id
    categoria = await get_category(session, category_id)
    if categoria is None:
        raise ValidationDomainError("La categoría indicada no existe.")
    if not categoria.is_active:
        raise ValidationDomainError("La categoría indicada está desactivada.")
    return category_id
