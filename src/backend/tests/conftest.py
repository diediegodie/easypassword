from __future__ import annotations

import os
import time
from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

if TYPE_CHECKING:
    from app.core.config import Settings


def is_postgres_ready():
    """Check if PostgreSQL is accessible for integration tests."""
    try:
        from sqlalchemy import create_engine, text

        db_url = os.getenv(
            "TEST_DATABASE_URL",
            os.getenv(
                "DATABASE_URL",
                "postgresql+asyncpg://postgres:postgres@localhost:5432/test_db",
            ),
        )
        sync_url = db_url.replace("+asyncpg", "")
        engine = create_engine(sync_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


_IN_DOCKER = os.path.exists("/.dockerenv")

_DATABASE_URL = (
    "postgresql+asyncpg://easypassword_user:dev_password@postgres:5432/easypassword"
    if _IN_DOCKER
    else "postgresql+asyncpg://easypassword_user:dev_password@localhost:5432/easypassword"
)
_REDIS_URL = "redis://redis:6379/0" if _IN_DOCKER else "redis://localhost:6379/0"

_TEST_ENV = {
    "APP_ENV": "development",
    "DEBUG": "false",
    "SECRET_KEY": "test-secret-key",
    "DATABASE_URL": _DATABASE_URL,
    "REDIS_URL": _REDIS_URL,
    "WEBAUTHN_RP_ID": "localhost",
    "WEBAUTHN_ORIGIN": "http://localhost:8000",
}

TEST_DATABASE_URL = _TEST_ENV["DATABASE_URL"]
TRUNCATE_TEST_DATA_SQL = (
    "TRUNCATE TABLE sessions, vaults, devices, users RESTART IDENTITY CASCADE"
)

for key, value in _TEST_ENV.items():
    os.environ[key] = value


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
async def app_client(db_session: AsyncSession) -> AsyncGenerator[TestClient, None]:
    from app.infra.database import get_db
    from main import app

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def async_engine() -> AsyncGenerator:
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
        poolclass=NullPool,
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(async_engine: object) -> AsyncGenerator[AsyncSession, None]:
    SessionLocal = async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with SessionLocal() as session:
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()


# Use session-scoped loop to avoid "Event loop is closed" errors when sharing resources
# like redis_client across async tests in CI/Integration mode.
@pytest.fixture(scope="session")
def event_loop():
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def configure_test_database() -> AsyncGenerator[None, None]:
    run_integration = os.getenv("RUN_INTEGRATION") == "1"
    if not run_integration:
        yield
        return

    from app.infra.database import Base

    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
        poolclass=NullPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


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


@pytest.fixture(autouse=True)
async def fake_redis(monkeypatch: pytest.MonkeyPatch):
    """Monkeypatch `app.infra.redis_client.redis_client` with an async in-memory
    fake when `RUN_INTEGRATION` is not set. In CI we set `RUN_INTEGRATION=1`.
    Even in CI we monkeypatch a fresh real client per test to avoid loop closure issues.
    """
    run_real = os.getenv("RUN_INTEGRATION", "").lower() in ("1", "true", "yes")
    if run_real:
        from redis.asyncio import Redis

        from app.core.config import settings

        real_fake = Redis.from_url(settings.REDIS_URL, decode_responses=False)
        monkeypatch.setattr("app.infra.redis_client.redis_client", real_fake)
        try:
            yield real_fake
        finally:
            try:
                await real_fake.close()
            except RuntimeError:
                # pytest may finalize this fixture after loop shutdown
                # in some integration paths; don't fail test teardown.
                pass
        return

    fake = AsyncFakeRedis()
    monkeypatch.setattr("app.infra.redis_client.redis_client", fake)
    try:
        yield fake
    finally:
        # synchronous cleanup: clear the in-memory store
        fake._store.clear()


@pytest.fixture(autouse=True)
async def clean_database(
    configure_test_database: None,
    async_engine: object,
) -> AsyncGenerator[None, None]:
    """Start each test from a clean database state."""
    run_integration = os.getenv("RUN_INTEGRATION") == "1"
    if not run_integration:
        yield
        return

    async with async_engine.begin() as conn:
        await conn.execute(text(TRUNCATE_TEST_DATA_SQL))

    yield

    async with async_engine.begin() as conn:
        await conn.execute(text(TRUNCATE_TEST_DATA_SQL))


def pytest_sessionstart(session):
    """Check service readiness when RUN_INTEGRATION=1."""
    run_integration = os.getenv("RUN_INTEGRATION") == "1"
    is_ci = os.getenv("CI") == "true"

    if run_integration or is_ci:
        print("\nChecking services for integration tests...")
        if not is_postgres_ready():
            pytest.exit(
                "\nPostgreSQL not available.\n"
                "To run integration tests:\n"
                "  docker-compose up -d\n"
                "  RUN_INTEGRATION=1 pytest\n"
                "Or run only unit tests:\n"
                "  pytest tests/unit/\n",
                returncode=1,
            )
        print("PostgreSQL OK")


def pytest_collection_modifyitems(config, items):
    """Skip integration tests and DB-backed tests if RUN_INTEGRATION is not set."""
    run_integration = os.getenv("RUN_INTEGRATION") == "1"
    DB_FIXTURES = {
        "db_session",
        "async_engine",
        "app_client",
        "async_db_session",
    }

    for item in items:
        uses_db = any(fixture in item.fixturenames for fixture in DB_FIXTURES)
        is_integration = "integration" in str(item.parent) or item.get_closest_marker(
            "integration"
        )

        if (is_integration or uses_db) and not run_integration:
            item.add_marker(
                pytest.mark.skip(
                    reason=(
                        "Integration test or requires database. Run with: "
                        "RUN_INTEGRATION=1 pytest"
                    )
                )
            )
