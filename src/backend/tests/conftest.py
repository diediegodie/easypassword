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

    with TestClient(app) as client:
        yield client
