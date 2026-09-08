"""Entorno de Alembic.

Las migraciones se ejecutan **siempre** con `DATABASE_MIGRATIONS_URL`, es decir con
el rol `app_maintainer`. Con el rol de la API fallarían: no tiene permiso de
creación en el esquema, y eso es deliberado.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import get_settings
from app.core.database import Base

# La importación de los modelos registra las tablas en `Base.metadata`. Sin
# ella, `alembic revision --autogenerate` no vería estas tablas y generaría
# una migración que las borra — `events`/`registrations` faltaban aquí (la
# fase 2 del PRD nunca las añadió); se completan ahora de paso.
from app.modules.events import models as event_models  # noqa: F401
from app.modules.organizations import models as organization_models  # noqa: F401
from app.modules.registrations import models as registration_models  # noqa: F401
from app.modules.roles import models as role_models  # noqa: F401
from app.modules.users import models as user_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_migrations_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
