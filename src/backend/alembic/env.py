""""This file is used by Alembic to run database migrations.
It is not intended to be used directly by the application code."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context


def _load_application_context() -> tuple[Any, Any]:
    base_dir = Path(__file__).resolve().parents[1]
    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))

    from app.core.config import settings
    from app.infra.database import Base
    from app.modules.auth.models import Device, User
    from app.modules.session.models import Session
    from app.modules.vault.models import Vault

    _ = (User, Device, Vault, Session)
    return settings, Base


settings, _base = _load_application_context()

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = _base.metadata


def _database_url() -> str:
    return settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)


def run_migrations_offline() -> None:
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=_database_url(),
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
