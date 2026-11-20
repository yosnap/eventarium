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

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionMaintenance
from app.core.locale import DEFAULT_LOCALE, LOCALES, Locale
from app.core.redis_client import get_redis
from app.modules.ai_gateway import errores, plataforma
from app.modules.ai_gateway.errores import (
    CredencialIlegible,
    ErrorDeProveedor,
    LimiteDeGastoSuperado,
    ServicioDesactivado,
    SinConfiguracion,
)
from app.modules.events.models import EventCategory
from app.modules.platform import repository
from app.modules.platform.models import PlatformLegalPage
from app.modules.platform.service import ORIGENES_A_MANO, espanoles_efectivos, firma_legal
from app.modules.translations import ia

logger = logging.getLogger(__name__)

USE_CASE = "traduccion_plataforma"
#: Tras tantos errores seguidos, una página deja de reintentarse sola.
MAX_ERRORES = 5
#: Una reserva más antigua que esto se da por abandonada.
RESERVA_CADUCADA = timedelta(minutes=15)
#: Una sola tarea a la vez (candado de sesión de Postgres): dos guardados
#: seguidos no pagan dos veces la misma traducción.
_CANDADO = 734_027_119
#: Fallos del proveedor que no son de lo que se traduce (clave rechazada o
#: ilegible, caída, límite de peticiones, tiempo agotado): se para el pase sin
#: culpar al texto y se reintenta en el siguiente.
_CODIGOS_SIN_IA = frozenset({errores.PROVEEDOR_ERROR, errores.CLAVE_RECHAZADA})


def _sin_ia(exc: BaseException) -> bool:
    """La IA no está disponible ahora, sin culpa del texto."""
    if isinstance(exc, LimiteDeGastoSuperado | ServicioDesactivado | SinConfiguracion):
        return True
    if isinstance(exc, CredencialIlegible):
        return True
    return isinstance(exc, ErrorDeProveedor) and exc.error_code in _CODIGOS_SIN_IA


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
            firma = firma_legal(original)
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
        except Exception as exc:
            if _sin_ia(exc):
                # Sin IA o sin presupuesto: lo reservado vuelve a quedar pendiente.
                for pendiente in encargos[indice:]:
                    await _escribir(pendiente.fila_id, {"status": "pendiente"})
                break
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


def _clave_espera_categorias(locale: Locale) -> str:
    return f"traduccion-plataforma:categorias:{locale}"


async def _categorias_en_espera(locale: Locale) -> bool:
    """Tras un fallo de la traducción de categorías a `locale`, se espera cada
    vez más (como el legal) para no pagar en bucle un modelo que no responde
    bien. Sin Redis, no se espera: el tope sigue mandando."""
    try:
        return bool(await get_redis().exists(f"{_clave_espera_categorias(locale)}:espera"))
    except Exception:
        return False


async def _anotar_fallo_de_categorias(locale: Locale) -> None:
    clave = _clave_espera_categorias(locale)
    try:
        redis = get_redis()
        fallos = int(await redis.incr(f"{clave}:fallos"))
        await redis.expire(f"{clave}:fallos", int(timedelta(days=1).total_seconds()))
        espera = int(_espera(fallos).total_seconds())
        await redis.set(f"{clave}:espera", "1", ex=espera)
    except Exception:
        logger.warning("No se ha podido anotar la espera de la traducción de categorías.")


async def olvidar_esperas_de_categorias() -> None:
    """Al guardar una categoría se vuelve a intentar sin esperar."""
    try:
        redis = get_redis()
        for locale in LOCALES:
            clave = _clave_espera_categorias(locale)
            await redis.delete(f"{clave}:fallos", f"{clave}:espera")
    except Exception:
        logger.warning("No se ha podido quitar la espera de la traducción de categorías.")


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
        if not faltan or await _categorias_en_espera(locale):
            continue
        textos = [ia.Texto(str(c.id), c.name, True) for c in faltan]
        try:
            resultado = await ia.traducir_con(_completar, textos, DEFAULT_LOCALE, locale, [])
        except Exception as exc:
            if _sin_ia(exc):
                break
            logger.warning("Falla la traducción de los nombres de categoría.")
            await _anotar_fallo_de_categorias(locale)
            continue
        if not any(resultado.values()):
            # El modelo respondió, pero nada valía: también es un fallo.
            await _anotar_fallo_de_categorias(locale)
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
    """El legal y las categorías, en ese orden, sin dos tareas a la vez."""
    async with SessionMaintenance() as session:
        if not await session.scalar(select(func.pg_try_advisory_lock(_CANDADO))):
            return 0, 0
        try:
            return await traducir_legal(), await traducir_categorias()
        finally:
            await session.execute(select(func.pg_advisory_unlock(_CANDADO)))
