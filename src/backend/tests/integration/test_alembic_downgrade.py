from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config

from alembic import command

pytestmark = pytest.mark.integration


async def _drop_all_tables(database_url: str) -> None:
    """
    Dropping every table guarantees a truly clean slate so the roundtrip
    exercise starts from an empty database.
    """
    pg_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    conn = await asyncpg.connect(pg_url)
    try:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        for row in rows:
            await conn.execute(f'DROP TABLE IF EXISTS "{row["tablename"]}" CASCADE')
    finally:
        await conn.close()


def test_alembic_downgrade_and_upgrade_roundtrip() -> None:
    """Verify Alembic downgrade and upgrade work for the latest migration."""
    config_file = Path(__file__).resolve().parents[3] / "backend" / "alembic.ini"
    config = Config(str(config_file))
    config.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parents[3] / "backend" / "alembic"),
    )
    database_url = os.getenv("DATABASE_URL")
    if database_url is None:
        raise RuntimeError(
            "DATABASE_URL environment variable is required for integration tests"
        )
    config.set_main_option("sqlalchemy.url", database_url)

    asyncio.run(_drop_all_tables(database_url))

    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
