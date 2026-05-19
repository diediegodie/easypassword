"""Unit and integration tests for WebAuthn credential registration."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, ConflictError
from app.infra.redis_client import get_challenge, set_challenge
from app.modules.auth.models import Device, User
from app.modules.auth.service import (
    generate_registration_options_for_user,
    verify_registration_credential,
)


@pytest.mark.asyncio
async def test_registration_initiation_creates_user(db_session: AsyncSession) -> None:
    """Test that registration initiation creates a new user if not found."""
    email = "new@example.com"

    registration_id, public_key = await generate_registration_options_for_user(
        db=db_session,
        email=email,
        device_name="Test Device",
        device_metadata={"platform": "test"},
    )

    # Verify user was created
    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.email == email.lower()
    assert user.account_status == "active"

    # Verify registration_id and public_key are returned
    assert registration_id
    assert isinstance(public_key, dict)
    assert "challenge" in public_key
    assert "rp" in public_key
    assert "user" in public_key


@pytest.mark.asyncio
async def test_registration_initiation_normalizes_email(
    db_session: AsyncSession,
) -> None:
    """Test that email is normalized to lowercase."""
    email_mixed = "NewUser@Example.Com"
    email_lower = email_mixed.lower()

    registration_id, _ = await generate_registration_options_for_user(
        db=db_session,
        email=email_mixed,
    )

    # Verify email was normalized
    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.email == email_lower))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.email == email_lower


@pytest.mark.asyncio
async def test_registration_initiation_rejects_existing_active_device(
    db_session: AsyncSession,
) -> None:
    """Test that initiation rejects if user already has an active device."""
    # Create user with active device
    user = User(email="existing@example.com", account_status="active")
    db_session.add(user)
    await db_session.flush()

    device = Device(
        user_id=user.id,
        credential_id="existing-cred",
        public_key=b"test-key",
        sign_count=0,
        device_name="Existing Device",
        device_metadata={},
        is_active=True,
    )
    db_session.add(device)
    await db_session.commit()

    # Attempt to initiate registration for same user
    with pytest.raises(ConflictError):
        await generate_registration_options_for_user(
            db=db_session,
            email="existing@example.com",
        )


@pytest.mark.asyncio
async def test_registration_challenge_stored_in_redis(db_session: AsyncSession) -> None:
    """Test that challenge is properly stored in Redis with TTL."""
    email = "redis-test@example.com"

    registration_id, _ = await generate_registration_options_for_user(
        db=db_session,
        email=email,
        device_name="Redis Test",
    )

    # Retrieve challenge from Redis
    challenge_data = await get_challenge(registration_id)
    assert challenge_data is not None

    # Verify challenge structure
    challenge_payload = json.loads(challenge_data.decode())
    assert challenge_payload["purpose"] == "registration"
    assert challenge_payload["email"] == email.lower()
    assert challenge_payload["device_name"] == "Redis Test"
    assert "challenge" in challenge_payload
    assert "rp_id" in challenge_payload


@pytest.mark.asyncio
async def test_registration_completion_with_mock_credential(
    db_session: AsyncSession,
) -> None:
    """Test registration completion with mocked WebAuthn credential verification."""
    # First, initiate registration
    email = "completion-test@example.com"
    registration_id, _ = await generate_registration_options_for_user(
        db=db_session,
        email=email,
        device_name="Test Device",
    )

    # Get user_id
    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    assert user is not None
    user_id = user.id

    # Mock credential payload
    mock_credential = {
        "id": "cred-id-123",
        "response": {
            "clientDataJSON": "mock-client-data",
            "attestationObject": "mock-attestation",
        },
    }

    # Mock the verify_registration_response function
    with patch("app.modules.auth.service.verify_registration_response") as mock_verify:
        # Configure mock to return a successful verification result
        mock_verified = MagicMock()
        mock_verified.credential_id = "verified-cred-id"
        mock_verified.credential_public_key = b"verified-public-key"
        mock_verified.sign_count = 0
        mock_verify.return_value = mock_verified

        user_id_result, device_id = await verify_registration_credential(
            db=db_session,
            registration_id=registration_id,
            credential=mock_credential,
        )

        assert user_id_result == user_id
        assert device_id is not None

    # Verify device was persisted
    result = await db_session.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    assert device is not None
    assert device.credential_id == "verified-cred-id"
    assert device.public_key == b"verified-public-key"
    assert device.device_name == "Test Device"
    assert device.is_active is True


@pytest.mark.asyncio
async def test_registration_challenge_one_time_use(db_session: AsyncSession) -> None:
    """Test that challenge can only be used once (replay protection)."""
    email = "replay-test@example.com"
    registration_id, _ = await generate_registration_options_for_user(
        db=db_session,
        email=email,
    )

    # Get challenge first time - should succeed
    challenge_data_1 = await get_challenge(registration_id)
    assert challenge_data_1 is not None

    # Try to get challenge second time - should fail (already deleted)
    challenge_data_2 = await get_challenge(registration_id)
    assert challenge_data_2 is None


@pytest.mark.asyncio
async def test_registration_rejects_expired_challenge(db_session: AsyncSession) -> None:
    """Test that verification rejects expired or missing challenge."""
    registration_id = "non-existent-registration-id"
    mock_credential = {"id": "cred", "response": {}}

    with pytest.raises(AuthError, match="challenge expired or invalid"):
        await verify_registration_credential(
            db=db_session,
            registration_id=registration_id,
            credential=mock_credential,
        )


@pytest.mark.asyncio
async def test_registration_rejects_challenge_purpose_mismatch(
    db_session: AsyncSession,
) -> None:
    """Test that verification rejects challenges with wrong purpose."""
    # Create a challenge with wrong purpose
    registration_id = str(uuid.uuid4())
    challenge_payload = {
        "purpose": "authentication",  # Wrong purpose
        "challenge": "test-challenge",
        "rp_id": "localhost",
    }
    await set_challenge(registration_id, json.dumps(challenge_payload).encode())

    mock_credential = {"id": "cred", "response": {}}

    with pytest.raises(AuthError, match="challenge purpose mismatch"):
        await verify_registration_credential(
            db=db_session,
            registration_id=registration_id,
            credential=mock_credential,
        )


@pytest.mark.asyncio
async def test_registration_enforces_single_device_in_transaction(
    db_session: AsyncSession,
) -> None:
    """Test that single-device policy is enforced even with concurrent registrations."""
    # Create user and register first device
    user = User(email="race@example.com", account_status="active")
    db_session.add(user)
    await db_session.flush()

    device1 = Device(
        user_id=user.id,
        credential_id="cred-1",
        public_key=b"key-1",
        sign_count=0,
        device_name="Device 1",
        device_metadata={},
        is_active=True,
    )
    db_session.add(device1)
    await db_session.commit()

    # Initiate second registration (should fail due to existing device)
    with pytest.raises(ConflictError, match="already has an active device"):
        await generate_registration_options_for_user(
            db=db_session,
            email="race@example.com",
        )


@pytest.mark.asyncio
async def test_registration_persists_device_metadata(db_session: AsyncSession) -> None:
    """Test that device_metadata is properly persisted."""
    email = "metadata-test@example.com"
    device_metadata = {
        "platform": "iOS",
        "os_version": "16.7",
        "browser": "Safari",
        "device_type": "phone",
    }

    registration_id, _ = await generate_registration_options_for_user(
        db=db_session,
        email=email,
        device_name="iPhone",
        device_metadata=device_metadata,
    )

    # Mock and complete registration
    from sqlalchemy import select

    mock_credential = {"id": "cred", "response": {}}

    with patch("app.modules.auth.service.verify_registration_response") as mock_verify:
        mock_verified = MagicMock()
        mock_verified.credential_id = "verified-cred"
        mock_verified.credential_public_key = b"verified-key"
        mock_verified.sign_count = 0
        mock_verify.return_value = mock_verified

        _, device_id = await verify_registration_credential(
            db=db_session,
            registration_id=registration_id,
            credential=mock_credential,
        )

    # Verify metadata was persisted
    result = await db_session.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    assert device is not None
    assert device.device_metadata == device_metadata


@pytest.mark.asyncio
async def test_registration_rejects_duplicate_credential_id(
    db_session: AsyncSession,
) -> None:
    """Test that duplicate credential IDs are rejected."""
    # Create user with existing credential
    user1 = User(email="user1@example.com", account_status="active")
    db_session.add(user1)
    await db_session.flush()

    device = Device(
        user_id=user1.id,
        credential_id="duplicate-cred-id",
        public_key=b"key-1",
        sign_count=0,
        device_name="Device 1",
        device_metadata={},
        is_active=True,
    )
    db_session.add(device)
    await db_session.commit()

    # Create second user and try to register with same credential_id
    user2 = User(email="user2@example.com", account_status="active")
    db_session.add(user2)
    await db_session.flush()

    registration_id = str(uuid.uuid4())
    challenge_payload = {
        "purpose": "registration",
        "user_id": str(user2.id),
        "email": "user2@example.com",
        "challenge": "test-challenge",
        "rp_id": "localhost",
        "origin": "http://localhost:8000",
        "device_name": "Device 2",
        "device_metadata": {},
    }
    await set_challenge(registration_id, json.dumps(challenge_payload).encode())

    mock_credential = {"id": "cred", "response": {}}

    with patch("app.modules.auth.service.verify_registration_response") as mock_verify:
        mock_verified = MagicMock()
        mock_verified.credential_id = "duplicate-cred-id"  # Same as existing
        mock_verified.credential_public_key = b"key-2"
        mock_verified.sign_count = 0
        mock_verify.return_value = mock_verified

        with pytest.raises(ConflictError, match="credential_id already registered"):
            await verify_registration_credential(
                db=db_session,
                registration_id=registration_id,
                credential=mock_credential,
            )
