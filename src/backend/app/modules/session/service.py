from __future__ import annotations

import logging
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
from app.infra.redis_client import (
    clear_device_reauthentication_required,
    is_device_reauthentication_required,
    set_device_reauthentication_required,
)
from app.modules.auth.models import Device
from app.modules.session.models import Session as SessionModel

logger = logging.getLogger("easypassword.security")


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

    await clear_device_reauthentication_required(str(device_id))

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
        sa.select(SessionModel, Device)
        .join(Device, SessionModel.device_id == Device.id)
        .where(
            sa.or_(
                SessionModel.refresh_token_hash == token_hash,
                SessionModel.previous_token_hash == token_hash,
            )
        )
    )
    row = result.one_or_none()

    if row is None:
        logger.warning(
            "refresh_token_invalid",
            extra={"token_hash": token_hash},
        )
        raise AuthError("invalid refresh token")

    session, device = row
    now = datetime.now(timezone.utc)
    if (
        session.previous_token_hash is not None
        and session.previous_token_hash == token_hash
    ):
        session.revoked_at = now
        await db.commit()
        logger.warning(
            "refresh_token_reuse_detected",
            extra={
                "session_id": str(session.id),
                "device_id": str(session.device_id),
                "user_id": str(session.user_id),
            },
        )
        raise AuthError("token reuse detected")

    if session.revoked_at is not None:
        logger.warning(
            "refresh_token_revoked_session",
            extra={
                "session_id": str(session.id),
                "device_id": str(session.device_id),
                "user_id": str(session.user_id),
            },
        )
        raise AuthError("invalid refresh token")

    if session.expires_at <= now:
        session.revoked_at = now
        await db.commit()
        logger.info(
            "refresh_token_expired",
            extra={
                "session_id": str(session.id),
                "device_id": str(session.device_id),
                "user_id": str(session.user_id),
            },
        )
        raise AuthError("session expired")

    if not device.is_active:
        logger.warning(
            "refresh_token_rejected_inactive_device",
            extra={
                "session_id": str(session.id),
                "device_id": str(session.device_id),
                "user_id": str(session.user_id),
            },
        )
        raise AuthError("inactive or expired token")

    session_last_activity = session.last_activity_at
    if session_last_activity is None:
        session.revoked_at = now
        await db.commit()
        await set_device_reauthentication_required(str(session.device_id))
        raise ReauthenticationRequiredError()

    inactivity = now - session_last_activity
    if inactivity.total_seconds() > settings.INACTIVITY_TIMEOUT_SECONDS:
        session.revoked_at = now
        await db.commit()
        await set_device_reauthentication_required(str(session.device_id))
        raise ReauthenticationRequiredError()

    if await is_device_reauthentication_required(str(session.device_id)):
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


async def validate_session_activity(db: AsyncSession, token: str) -> dict[str, object]:
    payload = decode_access_token(token)
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise AuthError("invalid or expired token")

    try:
        session_uuid = UUID(session_id)
    except ValueError as exc:
        raise AuthError("invalid or expired token") from exc

    now = datetime.now(timezone.utc)
    # NOTE: `validate_session_activity` updates `last_activity_at` and therefore
    # should use a row lock to avoid concurrency issues where multiple requests
    # race and silently overwrite each other's activity updates.
    result = await db.execute(
        sa.select(SessionModel, Device)
        .join(Device, SessionModel.device_id == Device.id)
        .where(SessionModel.id == session_uuid)
        .with_for_update()
    )
    row = result.one_or_none()

    if row is None:
        raise AuthError("invalid or expired token")

    session, device = row
    if session.revoked_at is not None:
        logger.warning(
            "access_token_rejected_revoked_session",
            extra={
                "session_id": str(session.id),
                "device_id": str(session.device_id),
                "user_id": str(session.user_id),
            },
        )
        raise AuthError("invalid or expired token")

    if not device.is_active:
        logger.warning(
            "access_token_rejected_inactive_device",
            extra={
                "session_id": str(session.id),
                "device_id": str(session.device_id),
                "user_id": str(session.user_id),
            },
        )
        raise AuthError("inactive or expired token")

    if session.expires_at <= now:
        session.revoked_at = now
        await db.commit()
        raise AuthError("invalid or expired token")

    session_last_activity = session.last_activity_at
    if session_last_activity is None:
        await set_device_reauthentication_required(str(session.device_id))
        logger.info(
            "session_reauthentication_required",
            extra={
                "session_id": str(session.id),
                "device_id": str(session.device_id),
                "user_id": str(session.user_id),
            },
        )
        raise ReauthenticationRequiredError()

    inactivity = now - session_last_activity
    if inactivity.total_seconds() > settings.INACTIVITY_TIMEOUT_SECONDS:
        await set_device_reauthentication_required(str(session.device_id))
        logger.info(
            "session_reauthentication_required",
            extra={
                "session_id": str(session.id),
                "device_id": str(session.device_id),
                "user_id": str(session.user_id),
                "inactivity_seconds": inactivity.total_seconds(),
            },
        )
        raise ReauthenticationRequiredError()

    if await is_device_reauthentication_required(str(session.device_id)):
        raise ReauthenticationRequiredError()

    session.last_activity_at = now
    await db.commit()
    return payload


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
    logger.info(
        "session_revoked",
        extra={
            "session_id": str(session.id),
            "device_id": str(session.device_id),
            "user_id": str(session.user_id),
        },
    )


async def get_current_user_and_device(
    token_or_payload: str | dict[str, object], db: AsyncSession
) -> tuple[UUID, UUID]:
    del db
    if isinstance(token_or_payload, str):
        payload = decode_access_token(token_or_payload)
    else:
        payload = token_or_payload

    try:
        user_id = UUID(str(payload["sub"]))
        device_id = UUID(str(payload["device_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthError("invalid or expired token") from exc

    return user_id, device_id


async def get_current_active_user_and_device(
    token: str,
    db: AsyncSession,
) -> tuple[UUID, UUID]:
    payload = await validate_session_activity(db, token)
    return await get_current_user_and_device(payload, db)
