from __future__ import annotations

import os
from collections.abc import Generator
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from app.core.config import Settings

_TEST_ENV = {
    "APP_ENV": "development",
    "DEBUG": "false",
    "SECRET_KEY": "test-secret-key",
    "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/easypassword_test",
    "REDIS_URL": "redis://localhost:6379/0",
    "WEBAUTHN_RP_ID": "localhost",
    "WEBAUTHN_ORIGIN": "http://localhost:8000",
}

for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)


@pytest.fixture()
def test_settings(monkeypatch: pytest.MonkeyPatch) -> "Settings":
    from app.core.config import Settings

    for key, value in _TEST_ENV.items():
        monkeypatch.setenv(key, value)

    if TYPE_CHECKING:
        return Settings.model_construct(
            SECRET_KEY="",
            DATABASE_URL="",
            WEBAUTHN_RP_ID="",
            WEBAUTHN_ORIGIN="",
        )
    return Settings()


@pytest.fixture()
def app_client() -> Generator[TestClient, None, None]:
    from main import app

    client = TestClient(app)
    yield client


def pytest_collection_modifyitems(config, items):
    """Skip integration tests by default when running locally.

    Enable by setting environment variable `RUN_INTEGRATION=1` or when
    running in GitHub Actions (`GITHUB_ACTIONS` is set).
    """
    run_integration = (
        os.getenv("RUN_INTEGRATION", "").lower() in ("1", "true", "yes")
        or os.getenv("GITHUB_ACTIONS", "").lower() == "true"
    )

    if not run_integration:
        skip_integration = pytest.mark.skip(
            reason=(
                "Integration tests disabled locally; set RUN_INTEGRATION=1 to enable"
            )
        )
        for item in items:
            try:
                if "integration" in item.keywords or "tests/integration" in str(
                    item.fspath
                ):
                    item.add_marker(skip_integration)
            except Exception:
                # If any introspection fails, don't modify the item (safe fallback).
                continue
