"""WebAuthn registration service."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import generate_registration_options, verify_registration_response
from webauthn.helpers import base64url_to_bytes, options_to_json
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import settings
from app.core.errors import AuthError, ConflictError
from app.infra.redis_client import get_challenge, set_challenge
from app.modules.auth.models import Device, User


async def generate_registration_options_for_user(
    db: AsyncSession,
    email: str,
    device_name: str | None = None,
    device_metadata: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Generate WebAuthn registration options for a new device.

    Args:
        db: Database session
        email: User email (will be normalized to lowercase)
        device_name: Optional friendly name for the device
        device_metadata: Optional metadata about the device (platform, browser, etc.)

    Returns:
        Tuple of (registration_id, registration_options_dict)

    Raises:
        ConflictError: If user already has an active device (single-device policy)
        ValidationError: If input validation fails
    """
    # Normalize email
    email = email.lower().strip()

    # Get or create user
    result = await db.execute(sa.select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(email=email, account_status="active")
        db.add(user)
        await db.flush()
    else:
        # Check if user already has an active device
        result = await db.execute(
            sa.select(Device).where(
                sa.and_(Device.user_id == user.id, Device.is_active.is_(True))
            )
        )
        if result.scalar_one_or_none() is not None:
            raise ConflictError(
                "User already has an active device (single-device policy)"
            )

    # Generate registration options using webauthn library
    registration_options = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=str(user.id).encode(),
        user_name=email,
        user_display_name=email,
        attestation=AttestationConveyancePreference.DIRECT,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )

    registration_options_dict = json.loads(options_to_json(registration_options))

    # Generate a unique registration_id for this session
    registration_id = str(uuid.uuid4())

    # Prepare challenge payload to store in Redis
    challenge_payload = {
        "purpose": "registration",
        "user_id": str(user.id),
        "email": email,
        "registration_id": registration_id,
        "challenge": registration_options_dict["challenge"],
        "rp_id": settings.WEBAUTHN_RP_ID,
        "origin": settings.WEBAUTHN_ORIGIN,
        "device_name": device_name,
        "device_metadata": device_metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Store challenge in Redis with TTL
    await set_challenge(registration_id, json.dumps(challenge_payload).encode())

    await db.commit()
    return registration_id, registration_options_dict


async def verify_registration_credential(
    db: AsyncSession,
    registration_id: str,
    credential: dict,
) -> tuple[uuid.UUID, uuid.UUID]:
    """
    Verify WebAuthn registration credential and persist the device.

    Args:
        db: Database session
        registration_id: The registration_id from initiation
        credential: The full attestation payload from navigator.credentials.create()

    Returns:
        Tuple of (user_id, device_id)

    Raises:
        AuthError: If challenge is expired or invalid
        ForbiddenError: If credential verification fails
        ConflictError: If race condition creates duplicate active device or credential
        ValidationError: If input validation fails
    """
    # Get and consume challenge from Redis (one-time use)
    challenge_data = await get_challenge(registration_id)

    if challenge_data is None:
        raise AuthError("challenge expired or invalid")

    try:
        challenge_payload = json.loads(challenge_data.decode())
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise AuthError("invalid challenge data") from e

    # Verify challenge purpose binding
    if challenge_payload.get("purpose") != "registration":
        raise AuthError("challenge purpose mismatch")

    user_id = uuid.UUID(challenge_payload["user_id"])
    device_name = challenge_payload.get("device_name")
    device_metadata = challenge_payload.get("device_metadata", {})

    # Verify attestation response
    try:
        verified_credential = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge_payload["challenge"]),
            expected_origin=settings.WEBAUTHN_ORIGIN,
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            require_user_verification=False,
        )
    except Exception as e:
        raise AuthError(f"credential verification failed: {str(e)}") from e

    # Extract credential details
    credential_id = verified_credential.credential_id
    public_key = verified_credential.credential_public_key
    sign_count = verified_credential.sign_count or 0

    # Check for duplicate credential_id
    # (shouldn't happen with constraints, but validate anyway)
    result = await db.execute(
        sa.select(Device).where(Device.credential_id == credential_id)
    )
    if result.scalar_one_or_none() is not None:
        raise ConflictError("credential_id already registered")

    # Re-check single-device policy in transaction to prevent race
    result = await db.execute(
        sa.select(Device).where(
            sa.and_(Device.user_id == user_id, Device.is_active.is_(True))
        )
    )
    if result.scalar_one_or_none() is not None:
        raise ConflictError(
            "user already has an active device (concurrent registration detected)"
        )

    # Persist device
    now = datetime.now(timezone.utc)
    device = Device(
        user_id=user_id,
        credential_id=credential_id,
        public_key=public_key,
        sign_count=sign_count,
        device_name=device_name,
        device_metadata=device_metadata,
        is_active=True,
        last_login_at=now,
    )
    db.add(device)

    try:
        await db.commit()
    except Exception as e:
        raise ConflictError(f"failed to persist device: {str(e)}") from e

    return user_id, device.id
