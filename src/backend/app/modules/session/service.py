from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AuthError, ReauthenticationRequiredError
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from app.modules.session.models import Session as SessionModel


async def create_session(
    db: AsyncSession, user_id: UUID, device_id: UUID
) -> tuple[str, str]:
    refresh_token = generate_refresh_token()
    now = datetime.now(timezone.utc)
    session = SessionModel(
        user_id=user_id,
        device_id=device_id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        previous_token_hash=None,
        issued_at=now,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        last_activity_at=now,
    )
    db.add(session)
    await db.commit()

    access_token = create_access_token(
        {
            "sub": str(user_id),
            "device_id": str(device_id),
            "session_id": str(session.id),
        }
    )
    return access_token, refresh_token


async def rotate_session(db: AsyncSession, refresh_token: str) -> tuple[str, str]:
    token_hash = hash_refresh_token(refresh_token)
    result = await db.execute(
        sa.select(SessionModel).where(
            sa.or_(
                SessionModel.refresh_token_hash == token_hash,
                SessionModel.previous_token_hash == token_hash,
            )
        )
    )
    session = result.scalar_one_or_none()

    if session is None or session.revoked_at is not None:
        raise AuthError("invalid refresh token")

    now = datetime.now(timezone.utc)
    if session.expires_at <= now:
        session.revoked_at = now
        await db.commit()
        raise AuthError("session expired")

    if (
        session.previous_token_hash is not None
        and session.previous_token_hash == token_hash
    ):
        session.revoked_at = now
        await db.commit()
        raise AuthError("token reuse detected")

    session_last_activity = session.last_activity_at
    if session_last_activity is None:
        session.revoked_at = now
        await db.commit()
        raise ReauthenticationRequiredError()

    inactivity = now - session_last_activity
    if inactivity.total_seconds() > settings.INACTIVITY_TIMEOUT_SECONDS:
        session.revoked_at = now
        await db.commit()
        raise ReauthenticationRequiredError()

    new_refresh_token = generate_refresh_token()
    session.previous_token_hash = session.refresh_token_hash
    session.refresh_token_hash = hash_refresh_token(new_refresh_token)
    session.last_activity_at = now
    await db.commit()

    access_token = create_access_token(
        {
            "sub": str(session.user_id),
            "device_id": str(session.device_id),
            "session_id": str(session.id),
        }
    )
    return access_token, new_refresh_token


async def validate_session_activity(db: AsyncSession, token: str) -> None:
    payload = decode_access_token(token)
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise AuthError("invalid or expired token")

    try:
        session_uuid = UUID(session_id)
    except ValueError as exc:
        raise AuthError("invalid or expired token") from exc

    now = datetime.now(timezone.utc)
    result = await db.execute(
        sa.select(SessionModel).where(SessionModel.id == session_uuid)
    )
    session = result.scalar_one_or_none()

    if session is None or session.revoked_at is not None:
        raise AuthError("invalid or expired token")

    if session.expires_at <= now:
        session.revoked_at = now
        await db.commit()
        raise AuthError("invalid or expired token")

    session_last_activity = session.last_activity_at
    if session_last_activity is None:
        session.revoked_at = now
        await db.commit()
        raise ReauthenticationRequiredError()

    inactivity = now - session_last_activity
    if inactivity.total_seconds() > settings.INACTIVITY_TIMEOUT_SECONDS:
        session.revoked_at = now
        await db.commit()
        raise ReauthenticationRequiredError()

    session.last_activity_at = now
    await db.commit()


async def revoke_session(db: AsyncSession, refresh_token: str) -> None:
    token_hash = hash_refresh_token(refresh_token)
    result = await db.execute(
        sa.select(SessionModel).where(
            sa.or_(
                SessionModel.refresh_token_hash == token_hash,
                SessionModel.previous_token_hash == token_hash,
            )
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        return

    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()


async def get_current_user_and_device(
    token: str, db: AsyncSession
) -> tuple[UUID, UUID]:
    del db
    try:
        payload = decode_access_token(token)
        user_id = UUID(str(payload["sub"]))
        device_id = UUID(str(payload["device_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthError("invalid or expired token") from exc

    return user_id, device_id


async def get_current_active_user_and_device(
    token: str,
    db: AsyncSession,
) -> tuple[UUID, UUID]:
    await validate_session_activity(db, token)
    return await get_current_user_and_device(token, db)
