from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command

pytestmark = pytest.mark.integration


def test_alembic_downgrade_and_upgrade_roundtrip() -> None:
    """Verify Alembic downgrade and upgrade work for the latest migration."""
    config_file = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(config_file))
    database_url = os.getenv("DATABASE_URL")
    if database_url is None:
        raise RuntimeError(
            "DATABASE_URL environment variable is required for integration tests"
        )
    config.set_main_option("sqlalchemy.url", database_url)

    # Ensure the migrations scripts can be downgraded and upgraded in place.
    command.downgrade(config, "-1")
    command.upgrade(config, "+1")
