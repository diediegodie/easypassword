from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.errors import AuthError
from app.modules.auth.models import Device, User
from app.modules.session.service import create_session, rotate_session

# Use settings from app.core.config which handles environment variables
TEST_DATABASE_URL = settings.DATABASE_URL


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL)
    async_session = sessionmaker(
        bind=engine,  # type: ignore
        expire_on_commit=False,
        class_=AsyncSession,
    )

    from app.infra.database import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:  # type: ignore
        yield session

    await engine.dispose()


@pytest.mark.anyio
async def test_session_flow(db_session: AsyncSession):
    # 1. Setup User and Device
    user = User(email=f"test_{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    device = Device(
        user_id=user.id, credential_id=str(uuid.uuid4()), public_key=b"public_key"
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)

    print(f"Created user {user.id} and device {device.id}")

    # 2. Create Session
    access_token, refresh_token = await create_session(db_session, user.id, device.id)
    assert access_token is not None
    assert refresh_token is not None
    print("Session created successfully")

    # 3. Rotate Session (Refresh)
    new_access_token, new_refresh_token = await rotate_session(
        db_session, refresh_token
    )
    assert new_access_token is not None
    assert new_refresh_token is not None
    assert new_refresh_token != refresh_token
    print("Session rotated successfully")

    # 4. Reuse Detection (Old Token)
    try:
        await rotate_session(db_session, refresh_token)
        pytest.fail("Reuse detection failed: old token allowed refresh")
    except AuthError as e:
        assert str(e) == "token reuse detected"
        print("Token reuse detection verified (properly blocked and revoked)")

    # 5. Verify Revocation after Reuse
    # The previous attempt should have revoked the session.
    try:
        await rotate_session(db_session, new_refresh_token)
        pytest.fail(
            "Revocation verification failed: session still active after reuse detection"
        )
    except AuthError as e:
        assert str(e) == "invalid refresh token"
        print("Session revocation verified after reuse")


if __name__ == "__main__":
    import asyncio

    async def run_manual_test():
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(settings.DATABASE_URL)
        async_session = sessionmaker(
            bind=engine,  # type: ignore
            expire_on_commit=False,
            class_=AsyncSession,
        )

        async with async_session() as session:  # type: ignore
            try:
                await test_session_flow(session)
                print("\nALL SESSION TESTS PASSED SUCCESSFULLY!")
            except Exception as e:
                print(f"\nTEST FAILED: {e}")
                import traceback

                traceback.print_exc()
            finally:
                await engine.dispose()

    asyncio.run(run_manual_test())
