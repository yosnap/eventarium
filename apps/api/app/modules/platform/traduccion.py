"""Traducción del contenido de la plataforma con su propia IA: las páginas
legales y los nombres de las categorías de eventos.

La paga la plataforma (`ai_gateway.plataforma`, con su tope). El contenido de
las organizaciones nunca pasa por aquí.

**Legal.** Cada versión traducida guarda la huella del español **efectivo**
(lo editado o, si no, la plantilla con el nombre y el dominio de la
instalación). Solo se sirve si esa huella coincide con el español actual; si
no, se sirve el español con aviso. La IA solo escribe filas suyas (`origin =
'ia'`): una versión escrita a mano o revisada no se toca nunca. Cada página se
reserva antes de llamar a la IA (`status = 'en_curso'`, con el mismo upsert
condicionado que el contenido de las organizaciones) y el resultado solo se
guarda si la fila sigue reservada, así que una traducción vieja no pisa una
corrección manual hecha mientras tanto.

**Categorías.** La IA rellena los idiomas que falten en `name_i18n` y marca
los suyos en `name_i18n_origin`; lo escrito a mano no se toca.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionMaintenance
from app.core.locale import DEFAULT_LOCALE, LOCALES, Locale
from app.modules.ai_gateway import plataforma
from app.modules.ai_gateway.errores import (
    LimiteDeGastoSuperado,
    ServicioDesactivado,
    SinConfiguracion,
)
from app.modules.events.models import EventCategory
from app.modules.platform import repository
from app.modules.platform.models import PlatformLegalPage
from app.modules.platform.service import ORIGENES_A_MANO, espanoles_efectivos
from app.modules.translations import ia
from app.modules.translations.campos import huella

logger = logging.getLogger(__name__)

USE_CASE = "traduccion_plataforma"
#: Tras tantos errores seguidos, una página deja de reintentarse sola.
MAX_ERRORES = 5
#: Una reserva más antigua que esto se da por abandonada.
RESERVA_CADUCADA = timedelta(minutes=15)
#: Errores que no son de la página: se para el pase y se reintenta más tarde.
_SIN_IA = (LimiteDeGastoSuperado, ServicioDesactivado, SinConfiguracion)


def _espera(errores: int) -> timedelta:
    return min(timedelta(minutes=2**errores), timedelta(hours=24))


async def idiomas_de_destino(session: AsyncSession) -> list[Locale]:
    """Idiomas activos de la plataforma, salvo el español original."""
    branding = await repository.get_platform_branding(session)
    activos = set(branding.enabled_locales or [])
    return [locale for locale in LOCALES if locale != DEFAULT_LOCALE and locale in activos]


async def _reservar(
    session: AsyncSession, clave: str, locale: Locale, ahora: datetime
) -> uuid.UUID | None:
    """Reserva la versión `locale` de la página `clave` para la IA, o `None` si
    está escrita a mano, ya reservada o en espera tras un error."""
    sentencia = (
        insert(PlatformLegalPage)
        .values(
            id=uuid.uuid4(),
            kind=clave,
            locale=locale,
            origin="ia",
            status="en_curso",
            updated_at=ahora,
        )
        .on_conflict_do_update(
            constraint="uq_platform_legal_pages_kind_locale",
            set_={"origin": "ia", "status": "en_curso", "updated_at": ahora},
            where=(
                or_(
                    PlatformLegalPage.origin.is_(None),
                    PlatformLegalPage.origin.notin_(ORIGENES_A_MANO),
                )
                & or_(
                    PlatformLegalPage.status.is_(None),
                    PlatformLegalPage.status != "en_curso",
                    PlatformLegalPage.updated_at < ahora - RESERVA_CADUCADA,
                )
                & or_(
                    PlatformLegalPage.retry_after.is_(None),
                    PlatformLegalPage.retry_after <= ahora,
                )
            ),
        )
        .returning(PlatformLegalPage.id)
    )
    return (await session.execute(sentencia)).scalar_one_or_none()


@dataclass(frozen=True)
class _Encargo:
    fila_id: uuid.UUID
    clave: str
    locale: Locale
    original: str
    firma: str


async def _encargos_legales(ahora: datetime) -> list[_Encargo]:
    """Reserva las versiones que hay que (re)traducir y las devuelve."""
    encargos: list[_Encargo] = []
    async with SessionMaintenance() as session, session.begin():
        if not await plataforma.disponible(session):
            return []
        destinos = await idiomas_de_destino(session)
        if not destinos:
            return []
        for clave, original in (await espanoles_efectivos(session)).items():
            firma = huella(original)
            for locale in destinos:
                fila = await repository.get_platform_legal_page(session, clave, locale)
                if fila is not None and (
                    fila.origin in ORIGENES_A_MANO
                    or (fila.status == "al_dia" and fila.source_hash == firma)
                    or fila.error_count >= MAX_ERRORES
                ):
                    continue
                fila_id = await _reservar(session, clave, locale, ahora)
                if fila_id is not None:
                    encargos.append(_Encargo(fila_id, clave, locale, original, firma))
    return encargos


async def _completar(**argumentos: Any) -> Any:  # noqa: ANN401
    return await plataforma.completar(use_case=USE_CASE, **argumentos)


async def _escribir(fila_id: uuid.UUID, valores: dict[str, Any]) -> None:
    """Guarda el resultado solo si la fila sigue reservada por la IA."""
    async with SessionMaintenance() as session, session.begin():
        await session.execute(
            update(PlatformLegalPage)
            .where(
                PlatformLegalPage.id == fila_id,
                PlatformLegalPage.origin == "ia",
                PlatformLegalPage.status == "en_curso",
            )
            .values(**valores)
        )


async def _fallo(fila_id: uuid.UUID, ahora: datetime) -> None:
    async with SessionMaintenance() as session, session.begin():
        fila = await session.get(PlatformLegalPage, fila_id)
        if fila is None or fila.origin != "ia" or fila.status != "en_curso":
            return
        fila.error_count += 1
        fila.status = "error"
        fila.retry_after = ahora + _espera(fila.error_count)


async def traducir_legal(ahora: datetime | None = None) -> int:
    """Traduce las páginas legales que lo necesiten. Devuelve cuántas tradujo."""
    momento = ahora or datetime.now(UTC)
    encargos = await _encargos_legales(momento)
    traducidas = 0
    for indice, encargo in enumerate(encargos):
        try:
            resultado = await ia.traducir_con(
                _completar,
                [ia.Texto("t0", encargo.original, False)],
                DEFAULT_LOCALE,
                encargo.locale,
                [],
            )
        except _SIN_IA:
            # Sin IA o sin presupuesto: lo reservado vuelve a quedar pendiente.
            for pendiente in encargos[indice:]:
                await _escribir(pendiente.fila_id, {"status": "pendiente"})
            break
        except Exception:
            logger.warning("Falla la traducción de la página legal %s.", encargo.clave)
            await _fallo(encargo.fila_id, momento)
            continue
        traducido = resultado.get("t0")
        if not traducido:
            await _fallo(encargo.fila_id, momento)
            continue
        await _escribir(
            encargo.fila_id,
            {
                "content": traducido,
                "status": "al_dia",
                "source_hash": encargo.firma,
                "error_count": 0,
                "retry_after": None,
            },
        )
        traducidas += 1
    return traducidas


async def traducir_categorias() -> int:
    """Rellena con IA los nombres de categoría que falten. Devuelve cuántos."""
    async with SessionMaintenance() as session:
        if not await plataforma.disponible(session):
            return 0
        destinos = await idiomas_de_destino(session)
        categorias = list(await session.scalars(select(EventCategory)))
    rellenados = 0
    for locale in destinos:
        faltan = [c for c in categorias if not (c.name_i18n or {}).get(locale)]
        if not faltan:
            continue
        textos = [ia.Texto(str(c.id), c.name, True) for c in faltan]
        try:
            resultado = await ia.traducir_con(_completar, textos, DEFAULT_LOCALE, locale, [])
        except _SIN_IA:
            break
        except Exception:
            logger.warning("Falla la traducción de los nombres de categoría.")
            continue
        async with SessionMaintenance() as session, session.begin():
            for categoria in faltan:
                traducido = resultado.get(str(categoria.id))
                fila = await session.get(EventCategory, categoria.id, with_for_update=True)
                # Si mientras tanto alguien lo escribió a mano o renombró, no se toca.
                if not traducido or fila is None or fila.name != categoria.name:
                    continue
                if (fila.name_i18n or {}).get(locale):
                    continue
                fila.name_i18n = {**(fila.name_i18n or {}), locale: traducido}
                fila.name_i18n_origin = {**(fila.name_i18n_origin or {}), locale: "ia"}
                rellenados += 1
    return rellenados


async def traducir_contenido() -> tuple[int, int]:
    """El legal y las categorías, en ese orden."""
    return await traducir_legal(), await traducir_categorias()
