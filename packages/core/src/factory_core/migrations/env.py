"""Alembic environment.

The connection string comes from application settings rather than ``alembic.ini`` so that
migrations and the running application can never disagree about which database they mean,
and so no credential is stored in a committed file.

``TEST_DATABASE_URL`` takes precedence when set. That is what lets the integration suite
migrate a throwaway database without touching a developer's real one.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from factory_core.config import DatabaseSettings
from factory_core.persistence.base import Base

# Importing the models module registers every table on Base.metadata. Without it,
# autogenerate would see an empty schema and cheerfully write a migration dropping
# every table.
import factory_core.persistence.models  # noqa: F401  isort:skip

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the URL to migrate.

    Reuses ``DatabaseSettings`` so the psycopg-driver normalisation and validation apply
    here exactly as they do at application startup.
    """
    override = os.environ.get("TEST_DATABASE_URL")
    if override:
        return DatabaseSettings(url=override).url.get_secret_value()  # type: ignore[arg-type]
    return DatabaseSettings().url.get_secret_value()  # type: ignore[call-arg]


def _configure(connection: Connection) -> None:
    """Configure the migration context for a live connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Detect column type changes; without this a varchar(80) → varchar(120) edit is
        # silently ignored by autogenerate.
        compare_type=True,
        compare_server_default=True,
        # Constraint names come from the naming convention in persistence/base.py.
        render_as_batch=False,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting.

    Used to review what a migration will do against production before running it.
    """
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Apply migrations against a live database."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()

    engine = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # Server-side prepared statements do not survive transaction-mode connection
        # pooling, which Neon uses. See persistence/engine.py.
        connect_args={"prepare_threshold": None},
    )

    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
