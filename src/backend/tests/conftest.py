from __future__ import annotations

import os
import time
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


# Provide a lightweight in-process async fake Redis for local, Docker-free
# integration test runs. When `RUN_INTEGRATION` is set (CI integration job),
# the fixture does nothing and tests use the real Redis service.
class AsyncFakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    async def execute_command(self, *args, **kwargs):
        # Expecting: ("EVAL", script, numkeys, key, window_seconds)
        try:
            if args and args[0] == "EVAL":
                key = args[3]
                window_seconds = int(args[4])
                now = time.time()
                entry = self._store.get(key)
                if entry is None or entry["expiry"] <= now:
                    self._store[key] = {"value": 1, "expiry": now + window_seconds}
                    return 1
                entry["value"] += 1
                return entry["value"]
        except Exception:
            return None

    async def setex(self, key: str, ttl: int, value: bytes) -> None:
        now = time.time()
        self._store[key] = {"value": value, "expiry": now + int(ttl)}

    async def getdel(self, key: str):
        entry = self._store.get(key)
        now = time.time()
        if entry and entry["expiry"] > now:
            val = entry["value"]
            del self._store[key]
            return val
        return None

    async def get(self, key: str):
        entry = self._store.get(key)
        now = time.time()
        if entry and entry["expiry"] > now:
            return entry["value"]
        return None

    async def delete(self, key: str) -> None:
        if key in self._store:
            del self._store[key]

    async def flushdb(self) -> None:
        self._store.clear()


@pytest.fixture()
def fake_redis(monkeypatch: pytest.MonkeyPatch):
    """Monkeypatch `app.infra.redis_client.redis_client` with an async in-memory
    fake when `RUN_INTEGRATION` is not set. In CI we set `RUN_INTEGRATION=1` so
    the real Redis service is used.
    """
    run_real = os.getenv("RUN_INTEGRATION", "").lower() in ("1", "true", "yes")
    if run_real:
        yield
        return

    fake = AsyncFakeRedis()
    monkeypatch.setattr("app.infra.redis_client.redis_client", fake)
    try:
        yield fake
    finally:
        # synchronous cleanup: clear the in-memory store
        fake._store.clear()
