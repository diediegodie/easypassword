from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AuthError, ReauthenticationRequiredError
from app.modules.auth.models import Device, User
from app.modules.session.models import Session as SessionModel
from app.modules.session.service import (
    create_session,
    rotate_session,
    validate_session_activity,
)


@pytest.mark.anyio
async def test_session_valid_at_59_seconds_access_allowed(
    db_session: AsyncSession,
) -> None:
    user = User(email="session-valid@example.com")
    db_session.add(user)
    await db_session.flush()
    device = Device(user_id=user.id, credential_id="valid-cred", public_key=b"key")
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)

    access_token, refresh_token = await create_session(db_session, user.id, device.id)
    assert access_token
    assert refresh_token

    session = (await db_session.execute(select(SessionModel))).scalar_one()
    session.last_activity_at = datetime.now(timezone.utc) - timedelta(seconds=59)
    await db_session.commit()

    old_activity = session.last_activity_at
    await validate_session_activity(db_session, access_token)

    refreshed = (await db_session.execute(select(SessionModel))).scalar_one()
    assert refreshed.last_activity_at > old_activity


@pytest.mark.anyio
async def test_session_expired_at_61_seconds_access_denied(
    db_session: AsyncSession,
) -> None:
    user = User(email="session-expired@example.com")
    db_session.add(user)
    await db_session.flush()
    device = Device(user_id=user.id, credential_id="expired-cred", public_key=b"key")
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)

    access_token, refresh_token = await create_session(db_session, user.id, device.id)
    assert access_token
    assert refresh_token

    session = (await db_session.execute(select(SessionModel))).scalar_one()
    session.last_activity_at = datetime.now(timezone.utc) - timedelta(seconds=61)
    await db_session.commit()

    with pytest.raises(ReauthenticationRequiredError) as exc_info:
        await validate_session_activity(db_session, access_token)

    assert exc_info.value.code == "ReauthenticationRequired"


@pytest.mark.anyio
async def test_refresh_token_after_inactivity_rejected_until_webauthn_login(
    db_session: AsyncSession,
) -> None:
    user = User(email="refresh-inactivity@example.com")
    db_session.add(user)
    await db_session.flush()
    device = Device(user_id=user.id, credential_id="refresh-cred", public_key=b"key")
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)

    access_token, refresh_token = await create_session(db_session, user.id, device.id)
    assert access_token
    assert refresh_token

    session = (await db_session.execute(select(SessionModel))).scalar_one()
    session.last_activity_at = datetime.now(timezone.utc) - timedelta(seconds=61)
    await db_session.commit()

    with pytest.raises(ReauthenticationRequiredError):
        await rotate_session(db_session, refresh_token)

    result = await db_session.execute(select(SessionModel))
    session_after = result.scalar_one()
    assert session_after.revoked_at is not None
