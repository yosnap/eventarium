"""Tipos de sesión por organización: paleta, tipos base y resolución.

Cada organización nace con los tipos base (`TIPOS_BASE`) que puede renombrar,
desactivar o ampliar. `base_key` empareja el texto heredado de
`event_sessions.session_type` y los alias del MCP aunque el nombre cambie.
"""

from __future__ import annotations

import uuid
from typing import Any, NamedTuple

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.events.models import EventSession, SessionType
from app.shared.errors import ConflictError, NotFoundError, ValidationDomainError

#: Colores permitidos (claves que el frontend traduce a tokens con contraste AA
#: en tema claro y oscuro). Un color libre no garantizaría que se lea.
PALETA = ("azul", "violeta", "verde", "ambar", "rosa", "cian", "rojo", "gris")

#: Clave base para lo que no encaja en ninguna otra.
BASE_POR_DEFECTO = "other"


class TipoBase(NamedTuple):
    base_key: str
    name: str
    color: str
    is_break: bool


TIPOS_BASE: tuple[TipoBase, ...] = (
    TipoBase("talk", "Charla", "azul", False),
    TipoBase("workshop", "Taller", "violeta", False),
    TipoBase("break", "Descanso", "gris", True),
    TipoBase("service", "Servicio", "ambar", True),
    TipoBase("other", "Otro", "cian", False),
)

CLAVES_BASE = frozenset(tipo.base_key for tipo in TIPOS_BASE)


async def crear_tipos_base(session: AsyncSession, organization_id: uuid.UUID) -> None:
    """Los tipos con los que nace una organización (las dos altas lo llaman)."""
    for orden, tipo in enumerate(TIPOS_BASE):
        session.add(
            SessionType(
                organization_id=organization_id,
                name=tipo.name,
                color=tipo.color,
                is_break=tipo.is_break,
                base_key=tipo.base_key,
                display_order=orden,
            )
        )
    await session.flush()


async def tipo_por_clave_base(
    session: AsyncSession, organization_id: uuid.UUID, clave: str
) -> SessionType | None:
    """El tipo de la organización para una clave heredada (`talk`, `break`…);
    una clave desconocida cae en «Otro». `None` si la organización no tiene
    tipos (no debería: las dos altas los crean)."""
    buscada = clave if clave in CLAVES_BASE else BASE_POR_DEFECTO
    tipo: SessionType | None = await session.scalar(
        select(SessionType).where(
            SessionType.organization_id == organization_id,
            SessionType.base_key == buscada,
        )
    )
    return tipo


# --- Catálogo de la organización (panel) ---------------------------------------


def _limpiar_nombre(nombre: str) -> str:
    """Sin espacios en los extremos ni dobles: «Mesa  redonda » es «Mesa redonda»."""
    return " ".join(nombre.split())


async def listar(
    session: AsyncSession, organization_id: uuid.UUID, *, solo_activos: bool = False
) -> list[tuple[SessionType, int]]:
    """Tipos de la organización por orden, con cuántas sesiones usan cada uno
    (una sola consulta agrupada, no una por tipo)."""
    usos = (
        select(EventSession.session_type_id, func.count().label("n"))
        .where(EventSession.organization_id == organization_id)
        .group_by(EventSession.session_type_id)
        .subquery()
    )
    consulta = (
        select(SessionType, func.coalesce(usos.c.n, 0))
        .outerjoin(usos, usos.c.session_type_id == SessionType.id)
        .where(SessionType.organization_id == organization_id)
        .order_by(SessionType.display_order, SessionType.name)
    )
    if solo_activos:
        consulta = consulta.where(SessionType.is_active.is_(True))
    return [(tipo, int(n)) for tipo, n in (await session.execute(consulta)).all()]


async def obtener(
    session: AsyncSession, organization_id: uuid.UUID, tipo_id: uuid.UUID
) -> SessionType:
    tipo: SessionType | None = await session.scalar(
        select(SessionType).where(
            SessionType.id == tipo_id, SessionType.organization_id == organization_id
        )
    )
    if tipo is None:
        raise NotFoundError("Ese tipo de sesión no existe.")
    return tipo


async def _guardar(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        if "uq_session_types_organization_id_nombre" in str(exc.orig):
            raise ConflictError("Ya hay un tipo de sesión con ese nombre.") from exc
        raise


async def crear(
    session: AsyncSession, organization_id: uuid.UUID, datos: dict[str, Any]
) -> SessionType:
    ultimo = await session.scalar(
        select(func.max(SessionType.display_order)).where(
            SessionType.organization_id == organization_id
        )
    )
    tipo = SessionType(
        organization_id=organization_id,
        name=_limpiar_nombre(datos["name"]),
        description=(datos.get("description") or "").strip() or None,
        color=datos.get("color", "azul"),
        is_break=bool(datos.get("is_break", False)),
        display_order=(ultimo or 0) + 1,
    )
    session.add(tipo)
    await _guardar(session)
    return tipo


async def actualizar(
    session: AsyncSession, organization_id: uuid.UUID, tipo_id: uuid.UUID, datos: dict[str, Any]
) -> SessionType:
    if datos.get("is_active") is False:
        await _bloquear_catalogo(session, organization_id)
    tipo = await obtener(session, organization_id, tipo_id)
    if "name" in datos and datos["name"] is not None:
        tipo.name = _limpiar_nombre(datos["name"])
    if "description" in datos:
        tipo.description = (datos["description"] or "").strip() or None
    for campo in ("color", "is_break", "is_active"):
        if datos.get(campo) is not None:
            setattr(tipo, campo, datos[campo])
    # Antes de consultar nada más: el autoflush de esa consulta sacaría el
    # nombre repetido como un error sin traducir (500 en vez de 409).
    await _guardar(session)
    if not tipo.is_active and not await _queda_otro_activo(session, organization_id, tipo.id):
        raise ConflictError("Tiene que quedar al menos un tipo de sesión activo.")
    return tipo


async def _bloquear_catalogo(session: AsyncSession, organization_id: uuid.UUID) -> None:
    """Bloquea los tipos de la organización: dos desactivaciones o borrados a la
    vez no pueden dejarla sin ningún tipo activo."""
    await session.execute(
        select(SessionType.id)
        .where(SessionType.organization_id == organization_id)
        .order_by(SessionType.id)
        .with_for_update()
    )


async def _queda_otro_activo(
    session: AsyncSession, organization_id: uuid.UUID, excepto: uuid.UUID
) -> bool:
    otro = await session.scalar(
        select(SessionType.id)
        .where(
            SessionType.organization_id == organization_id,
            SessionType.is_active.is_(True),
            SessionType.id != excepto,
        )
        .limit(1)
    )
    return otro is not None


async def borrar(session: AsyncSession, organization_id: uuid.UUID, tipo_id: uuid.UUID) -> None:
    """Solo si ninguna sesión lo usa; si no, se desactiva (las sesiones lo conservan)."""
    await _bloquear_catalogo(session, organization_id)
    tipo = await obtener(session, organization_id, tipo_id)
    en_uso = await session.scalar(
        select(func.count()).where(
            EventSession.organization_id == organization_id,
            EventSession.session_type_id == tipo.id,
        )
    )
    if en_uso:
        raise ConflictError(
            "Lo usan {en_uso} sesión(es): desactívalo para que no se ofrezca en las nuevas; "
            "las que ya lo tienen lo conservan.",
            params={"en_uso": en_uso},
        )
    if tipo.is_active and not await _queda_otro_activo(session, organization_id, tipo.id):
        raise ConflictError("Tiene que quedar al menos un tipo de sesión activo.")
    await session.delete(tipo)
    try:
        await session.flush()
    except IntegrityError as exc:
        # Alguien le asignó una sesión entre el recuento y el borrado.
        raise ConflictError(
            "Acaban de asignar este tipo a una sesión: desactívalo en vez de borrarlo."
        ) from exc


async def reordenar(
    session: AsyncSession, organization_id: uuid.UUID, ids: list[uuid.UUID]
) -> None:
    """Recibe todos los tipos en el orden nuevo. Bloquea las filas para que dos
    reordenaciones no se mezclen, y si entretanto se creó o borró alguno, 409."""
    tipos = list(
        await session.scalars(
            select(SessionType)
            .where(SessionType.organization_id == organization_id)
            .with_for_update()
        )
    )
    if {tipo.id for tipo in tipos} != set(ids) or len(ids) != len(set(ids)):
        raise ConflictError(
            "Los tipos de sesión han cambiado: recarga la lista y vuelve a ordenar."
        )
    por_id = {tipo.id: tipo for tipo in tipos}
    for orden, tipo_id in enumerate(ids):
        por_id[tipo_id].display_order = orden
    await session.flush()


async def resolver_para_sesion(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    tipo_id: uuid.UUID | None,
    clave: str | None,
    actual: uuid.UUID | None = None,
    _reparando: bool = False,
) -> SessionType:
    """El tipo de una sesión: por id (de la organización y activo, salvo que sea
    el que ya tenía, como la categoría de un evento), por clave heredada o, sin
    ninguno, el primer tipo activo que no es una pausa."""
    if tipo_id is not None:
        tipo = await obtener(session, organization_id, tipo_id)
        if not tipo.is_active and tipo.id != actual:
            raise ValidationDomainError(
                "El tipo «{tipo}» está desactivado: actívalo o elige otro.",
                params={"tipo": tipo.name},
            )
        return tipo
    if clave is not None:
        encontrado = await tipo_por_clave_base(session, organization_id, clave)
        # Por clave (clientes antiguos, MCP) un tipo desactivado no se asigna:
        # se sigue al tipo por defecto, salvo que sea el que ya tenía la sesión.
        if encontrado is not None and (encontrado.is_active or encontrado.id == actual):
            return encontrado
    por_defecto = await _primero_activo(session, organization_id)
    if por_defecto is None and not _reparando and not await _tiene_tipos(session, organization_id):
        # Una organización que nació sin tipos (alta durante un despliegue, a
        # mano, restaurada de una copia antigua) los recibe al necesitarlos. En
        # un punto de guardado: si otra petición los crea a la vez, se usan esos.
        try:
            async with session.begin_nested():
                await crear_tipos_base(session, organization_id)
        except IntegrityError:
            pass
        # Un solo reintento: si los tipos siguen sin existir, no es la carrera.
        return await resolver_para_sesion(
            session, organization_id, tipo_id=tipo_id, clave=clave, actual=actual, _reparando=True
        )
    if por_defecto is None:
        raise ValidationDomainError(
            "La organización no tiene tipos de sesión activos: crea o activa alguno."
        )
    return por_defecto


async def _primero_activo(session: AsyncSession, organization_id: uuid.UUID) -> SessionType | None:
    tipo: SessionType | None = await session.scalar(
        select(SessionType)
        .where(SessionType.organization_id == organization_id, SessionType.is_active.is_(True))
        .order_by(SessionType.is_break, SessionType.display_order)
        .limit(1)
    )
    return tipo


async def _tiene_tipos(session: AsyncSession, organization_id: uuid.UUID) -> bool:
    return (
        await session.scalar(
            select(SessionType.id).where(SessionType.organization_id == organization_id).limit(1)
        )
    ) is not None


async def por_texto(session: AsyncSession, organization_id: uuid.UUID, texto: str) -> SessionType:
    """Un tipo activo de la organización por su id, su nombre (sin distinguir
    mayúsculas) o su clave base (`talk`, `workshop`…), para el MCP."""
    buscado = texto.strip()
    plegado = buscado.casefold()
    candidatos = [tipo for tipo, _ in await listar(session, organization_id, solo_activos=True)]
    # Por prioridad, no por orden de la lista: un tipo propio llamado «Talk»
    # gana a la clave base `talk` de «Charla».
    for coincide in (
        lambda tipo: str(tipo.id) == plegado,
        lambda tipo: tipo.name.casefold() == plegado,
        lambda tipo: tipo.base_key == plegado,
    ):
        for tipo in candidatos:
            if coincide(tipo):
                return tipo
    disponibles = ", ".join(f"«{tipo.name}»" for tipo in candidatos) or "ninguno"
    raise ValidationDomainError(
        "No hay ningún tipo de sesión activo «{buscado}». Disponibles: {disponibles}.",
        params={"buscado": buscado, "disponibles": disponibles},
    )


def referencia(tipo: SessionType) -> dict[str, Any]:
    """Lo que pintan el panel y las páginas públicas (`SessionTypeRef`)."""
    return {
        "id": str(tipo.id),
        "name": tipo.name,
        "color": tipo.color,
        "is_break": tipo.is_break,
    }


def clave_heredada(tipo: SessionType) -> str:
    """El texto de `event_sessions.session_type` mientras dure la transición."""
    return tipo.base_key or BASE_POR_DEFECTO
