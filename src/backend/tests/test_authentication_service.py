"""Unit tests for WebAuthn authentication service."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError
from app.infra.redis_client import get_challenge
from app.modules.auth.models import Device, User
from app.modules.auth.service import (
    generate_authentication_options_for_user,
    verify_authentication_credential,
)


@pytest.mark.asyncio
async def test_authentication_initiation_requires_active_device(
    db_session: AsyncSession,
) -> None:
    """Test that authentication initiation fails when no active device exists."""
    user = User(email="login@example.com", account_status="active")
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(AuthError, match="no active device"):
        await generate_authentication_options_for_user(db=db_session, email=user.email)


@pytest.mark.asyncio
async def test_authentication_initiation_rejects_inactive_device(
    db_session: AsyncSession,
) -> None:
    """Test that authentication initiation rejects an inactive device."""
    user = User(email="inactive@example.com", account_status="active")
    db_session.add(user)
    await db_session.flush()

    device = Device(
        user_id=user.id,
        credential_id="inactive-cred",
        public_key=b"inactive-key",
        sign_count=0,
        device_name="Inactive Device",
        device_metadata={},
        is_active=False,
    )
    db_session.add(device)
    await db_session.commit()

    with pytest.raises(AuthError, match="no active device"):
        await generate_authentication_options_for_user(db=db_session, email=user.email)


@pytest.mark.asyncio
async def test_authentication_initiation_stores_challenge_in_redis(
    db_session: AsyncSession,
) -> None:
    """Test that login initiation stores an authentication challenge in Redis."""
    user = User(email="redis-auth@example.com", account_status="active")
    db_session.add(user)
    await db_session.flush()

    device = Device(
        user_id=user.id,
        credential_id="redis-cred",
        public_key=b"redis-key",
        sign_count=0,
        device_name="Device",
        device_metadata={},
        is_active=True,
    )
    db_session.add(device)
    await db_session.commit()

    authentication_id, public_key = await generate_authentication_options_for_user(
        db=db_session,
        email=user.email,
    )

    assert authentication_id
    assert isinstance(public_key, dict)
    assert "challenge" in public_key

    challenge_data = await get_challenge(authentication_id)
    assert challenge_data is not None
    payload = json.loads(challenge_data.decode())
    assert payload["purpose"] == "authentication"
    assert payload["user_id"] == str(user.id)
    assert payload["device_id"] == str(device.id)
    assert payload["credential_id"] == device.credential_id


@pytest.mark.asyncio
async def test_authentication_completion_success_updates_device_state(
    db_session: AsyncSession,
) -> None:
    """Test that authentication completion updates device login state."""
    user = User(email="login-success@example.com", account_status="active")
    db_session.add(user)
    await db_session.flush()

    device = Device(
        user_id=user.id,
        credential_id="success-cred",
        public_key=b"success-key",
        sign_count=1,
        device_name="Device",
        device_metadata={},
        is_active=True,
    )
    db_session.add(device)
    await db_session.commit()

    authentication_id, _ = await generate_authentication_options_for_user(
        db=db_session, email=user.email
    )

    mock_credential = {
        "id": "credential-id",
        "response": {
            "clientDataJSON": "data",
            "authenticatorData": "auth-data",
            "signature": "signature",
        },
    }

    with patch(
        "app.modules.auth.service.verify_authentication_response"
    ) as mock_verify:
        mock_verified = MagicMock()
        mock_verified.new_sign_count = 5
        mock_verify.return_value = mock_verified

        returned_user_id, returned_device_id = await verify_authentication_credential(
            db=db_session,
            authentication_id=authentication_id,
            credential=mock_credential,
        )

    assert returned_user_id == user.id
    assert returned_device_id == device.id

    from sqlalchemy import select

    result = await db_session.execute(select(Device).where(Device.id == device.id))
    refreshed_device = result.scalar_one_or_none()
    assert refreshed_device is not None
    assert refreshed_device.sign_count == 5
    assert refreshed_device.last_login_at is not None


@pytest.mark.asyncio
async def test_authentication_challenge_replay_protection(
    db_session: AsyncSession,
) -> None:
    """Test that authentication challenge replay is rejected."""
    user = User(email="replay@example.com", account_status="active")
    db_session.add(user)
    await db_session.flush()

    device = Device(
        user_id=user.id,
        credential_id="replay-cred",
        public_key=b"replay-key",
        sign_count=0,
        device_name="Device",
        device_metadata={},
        is_active=True,
    )
    db_session.add(device)
    await db_session.commit()

    authentication_id, _ = await generate_authentication_options_for_user(
        db=db_session, email=user.email
    )

    mock_credential = {"id": "cred", "response": {}}

    with patch(
        "app.modules.auth.service.verify_authentication_response"
    ) as mock_verify:
        mock_verified = MagicMock()
        mock_verified.new_sign_count = 1
        mock_verify.return_value = mock_verified

        await verify_authentication_credential(
            db=db_session,
            authentication_id=authentication_id,
            credential=mock_credential,
        )

    with pytest.raises(AuthError, match="challenge expired or invalid"):
        await verify_authentication_credential(
            db=db_session,
            authentication_id=authentication_id,
            credential=mock_credential,
        )


@pytest.mark.asyncio
async def test_authentication_rejects_purpose_mismatch(
    db_session: AsyncSession,
) -> None:
    """Test that authentication verification rejects a wrong-purpose challenge."""
    authentication_id = str(uuid.uuid4())
    challenge_payload = {
        "purpose": "registration",
        "user_id": str(uuid.uuid4()),
        "device_id": str(uuid.uuid4()),
        "credential_id": "wrong-purpose",
        "challenge": "test-challenge",
        "rp_id": "localhost",
        "origin": "http://localhost:8000",
    }
    from app.infra.redis_client import set_challenge

    await set_challenge(authentication_id, json.dumps(challenge_payload).encode())

    with pytest.raises(AuthError, match="challenge purpose mismatch"):
        await verify_authentication_credential(
            db=db_session,
            authentication_id=authentication_id,
            credential={"id": "cred", "response": {}},
        )


@pytest.mark.asyncio
async def test_authentication_rejects_invalid_assertion(
    db_session: AsyncSession,
) -> None:
    """Test that authentication verification rejects invalid assertions."""
    user = User(email="invalid@example.com", account_status="active")
    db_session.add(user)
    await db_session.flush()

    device = Device(
        user_id=user.id,
        credential_id="invalid-cred",
        public_key=b"invalid-key",
        sign_count=0,
        device_name="Device",
        device_metadata={},
        is_active=True,
    )
    db_session.add(device)
    await db_session.commit()

    authentication_id, _ = await generate_authentication_options_for_user(
        db=db_session, email=user.email
    )

    with patch(
        "app.modules.auth.service.verify_authentication_response"
    ) as mock_verify:
        mock_verify.side_effect = ValueError("invalid signature")

        with pytest.raises(AuthError, match="credential verification failed"):
            await verify_authentication_credential(
                db=db_session,
                authentication_id=authentication_id,
                credential={"id": "cred", "response": {}},
            )
