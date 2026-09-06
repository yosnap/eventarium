"""Motores, sesiones y base declarativa.

Dos motores deliberadamente separados:

- `engine_app` usa el rol `app_user`, que **no** puede saltarse RLS. Es el único que
  usan los routers a través de `get_db`.
- `engine_maintenance` usa `app_maintainer` (con `BYPASSRLS`). Solo lo usan Alembic,
  el CLI, el seed y el módulo `admin`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData, func, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import get_settings

# Nombres deterministas para que Alembic genere migraciones estables.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarativa común."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _ahora() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    """Marcas temporales de creación y modificación.

    Los valores se calculan en la aplicación (`default`) además de tener
    `server_default`. No es redundancia decorativa: si dependieran solo del servidor,
    SQLAlchemy añadiría `RETURNING` a cada `INSERT` para recuperarlos, y un `INSERT
    … RETURNING` exige también superar la política `SELECT` de RLS. Al dar de alta a
    una persona, su fila de `users` todavía no tiene membresía y por tanto aún no es
    visible, así que ese `RETURNING` fallaría. El `server_default` se mantiene como
    red de seguridad para las inserciones hechas fuera del ORM.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=_ahora, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=_ahora,
        onupdate=_ahora,
        nullable=False,
    )


_settings = get_settings()

engine_app: AsyncEngine = create_async_engine(
    _settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=10,
)
engine_maintenance: AsyncEngine = create_async_engine(
    _settings.database_migrations_url,
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=2,
)

SessionApp = async_sessionmaker(engine_app, expire_on_commit=False)
SessionMaintenance = async_sessionmaker(engine_maintenance, expire_on_commit=False)


async def set_organization_context(
    session: AsyncSession,
    organization_id: uuid.UUID | None,
    user_id: uuid.UUID | None = None,
) -> None:
    """Fija el contexto de RLS **dentro** de la transacción abierta.

    `SET LOCAL` solo tiene efecto dentro de una transacción; fuera de ella la
    instrucción se descarta silenciosamente y las políticas verían un contexto vacío.
    Un valor vacío es intencionado: las políticas lo traducen a «ninguna fila»
    (fail-closed) en lugar de a un error.
    """
    await session.execute(
        text("SELECT set_config('app.organization_id', :valor, true)"),
        {"valor": str(organization_id) if organization_id else ""},
    )
    await session.execute(
        text("SELECT set_config('app.user_id', :valor, true)"),
        {"valor": str(user_id) if user_id else ""},
    )


@asynccontextmanager
async def maintenance_session() -> AsyncIterator[AsyncSession]:
    """Sesión con el rol de mantenimiento. Solo para CLI, seed, Alembic y `admin`."""
    async with SessionMaintenance() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
