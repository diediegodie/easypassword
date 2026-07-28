from __future__ import annotations

import os
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

if TYPE_CHECKING:
    from app.core.config import Settings


def is_postgres_ready():
    """Check if PostgreSQL is accessible for integration tests."""
    try:
        from urllib.parse import urlparse

        import psycopg2

        db_url = _normalize_service_url(
            os.getenv(
                "TEST_DATABASE_URL",
                os.getenv(
                    "DATABASE_URL",
                    "postgresql+asyncpg://easypassword_user:dev_password@localhost:5432/easypassword",
                ),
            )
        )
        parsed = urlparse(db_url.replace("+asyncpg", ""))
        connection = psycopg2.connect(
            dbname=parsed.path.lstrip("/"),
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port,
        )
        connection.close()
        return True
    except Exception:
        return False


_IN_DOCKER = os.path.exists("/.dockerenv")


def _normalize_service_url(url: str) -> str:
    try:
        parsed = make_url(url)
    except Exception:
        return url

    if parsed.drivername in {"postgresql", "postgres"}:
        parsed = parsed.set(drivername="postgresql+asyncpg")

    if _IN_DOCKER:
        return parsed.render_as_string(hide_password=False)

    if parsed.host in {"postgres", "redis"}:
        return parsed.set(host="localhost").render_as_string(hide_password=False)

    return parsed.render_as_string(hide_password=False)


_DATABASE_URL = (
    "postgresql+asyncpg://easypassword_user:dev_password@postgres:5432/easypassword"
    if _IN_DOCKER
    else "postgresql+asyncpg://easypassword_user:dev_password@localhost:5432/easypassword"
)
_REDIS_URL = "redis://redis:6379/0" if _IN_DOCKER else "redis://localhost:6379/0"

CURRENT_DATABASE_URL = _normalize_service_url(os.getenv("DATABASE_URL", _DATABASE_URL))
CURRENT_REDIS_URL = _normalize_service_url(os.getenv("REDIS_URL", _REDIS_URL))

os.environ["DATABASE_URL"] = CURRENT_DATABASE_URL
os.environ["REDIS_URL"] = CURRENT_REDIS_URL

TEST_DATABASE_URL = _normalize_service_url(
    os.getenv("TEST_DATABASE_URL", CURRENT_DATABASE_URL)
)
TEST_REDIS_URL = _normalize_service_url(os.getenv("TEST_REDIS_URL", CURRENT_REDIS_URL))

_TEST_ENV = {
    "APP_ENV": "development",
    "DEBUG": "false",
    "SECRET_KEY": "test-secret-key",
    "DATABASE_URL": TEST_DATABASE_URL,
    "REDIS_URL": TEST_REDIS_URL,
    "WEBAUTHN_RP_ID": "localhost",
    "WEBAUTHN_ORIGIN": "http://localhost:8000",
}

TRUNCATE_TEST_DATA_SQL = (
    "TRUNCATE TABLE sessions, vaults, devices, users RESTART IDENTITY CASCADE"
)

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


@pytest_asyncio.fixture()
async def app_client(async_engine: AsyncEngine) -> AsyncGenerator[TestClient, None]:
    from app.infra.database import get_db
    from main import app

    SessionLocal = async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with SessionLocal() as session:
            yield session

    original_db_session_factory = getattr(app.state, "db_session_factory", None)
    app.dependency_overrides[get_db] = override_get_db
    app.state.db_session_factory = SessionLocal
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()
        app.state.db_session_factory = original_db_session_factory


@pytest_asyncio.fixture(scope="function")
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
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


@pytest_asyncio.fixture(scope="function")
async def db_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
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


@pytest_asyncio.fixture(scope="session")
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
    try:
        yield
    finally:
        await engine.dispose()


class AsyncFakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    async def execute_command(self, *args, **kwargs):
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


@pytest_asyncio.fixture(autouse=True)
async def fake_redis(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Monkeypatch `app.infra.redis_client.redis_client` with an async in-memory
    fake when `RUN_INTEGRATION` is not set. In CI we set `RUN_INTEGRATION=1`.
    Use a real Redis client only for integration tests, and keep a fake client for
    other tests to avoid event loop closing issues.
    """
    run_real = os.getenv("RUN_INTEGRATION", "").lower() in ("1", "true", "yes")
    is_integration = request.node.get_closest_marker("integration") is not None

    if run_real and is_integration:
        redis_url = os.environ["REDIS_URL"]
        redis = Redis.from_url(redis_url)
        try:
            await redis.flushdb()
        except Exception:
            pass
        monkeypatch.setattr("app.infra.redis_client.redis_client", None)
        try:
            yield redis
        finally:
            try:
                await redis.close()
            except RuntimeError:
                pass
        return

    fake = AsyncFakeRedis()
    monkeypatch.setattr("app.infra.redis_client.redis_client", fake)
    try:
        yield fake
    finally:
        fake._store.clear()


@pytest_asyncio.fixture(autouse=True)
async def clean_database(
    configure_test_database: None,
    async_engine: AsyncEngine,
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
