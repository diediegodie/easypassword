from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from app.core.config import settings

Base = declarative_base()


def _database_url() -> str:
    url = make_url(settings.DATABASE_URL)
    if url.drivername in {"postgresql", "postgres"}:
        return str(url.set(drivername="postgresql+asyncpg"))
    return str(url)


engine: AsyncEngine = create_async_engine(
    _database_url(), echo=settings.DEBUG, future=True
)
async_session_factory = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
