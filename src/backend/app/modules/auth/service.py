from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, options_to_json
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialType,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import settings
from app.core.errors import AuthError, ConflictError
from app.infra.redis_client import (
    clear_device_reauthentication_required,
    get_challenge,
    set_challenge,
)
from app.modules.auth.models import Device, User


async def generate_registration_options_for_user(
    db: AsyncSession,
    email: str,
    device_name: str | None = None,
    device_metadata: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Generate WebAuthn registration options for a new device.
    """
    email = email.lower().strip()

    result = await db.execute(sa.select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(email=email, account_status="active")
        db.add(user)
        await db.flush()
    else:
        result = await db.execute(
            sa.select(Device).where(
                sa.and_(Device.user_id == user.id, Device.is_active.is_(True))
            )
        )
        if result.scalar_one_or_none() is not None:
            raise ConflictError(
                "User already has an active device (single-device policy)"
            )

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

    registration_id = str(uuid.uuid4())

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

    await set_challenge(registration_id, json.dumps(challenge_payload).encode())

    await db.commit()
    return registration_id, registration_options_dict


async def generate_authentication_options_for_user(
    db: AsyncSession,
    email: str,
) -> tuple[str, dict[str, Any]]:
    """
    Generate WebAuthn authentication options for an existing user with an active device.
    """
    email = email.lower().strip()

    result = await db.execute(sa.select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        raise AuthError("user not found")

    result = await db.execute(
        sa.select(Device).where(
            sa.and_(Device.user_id == user.id, Device.is_active.is_(True))
        )
    )
    device = result.scalar_one_or_none()

    if device is None:
        raise AuthError("no active device found for user")

    allowed_credential = PublicKeyCredentialDescriptor(
        id=device.credential_id.encode(),
        type=PublicKeyCredentialType.PUBLIC_KEY,
    )

    authentication_options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=[allowed_credential],
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    authentication_options_dict = json.loads(options_to_json(authentication_options))

    authentication_id = str(uuid.uuid4())

    challenge_payload = {
        "purpose": "authentication",
        "user_id": str(user.id),
        "device_id": str(device.id),
        "credential_id": device.credential_id,
        "authentication_id": authentication_id,
        "challenge": authentication_options_dict["challenge"],
        "rp_id": settings.WEBAUTHN_RP_ID,
        "origin": settings.WEBAUTHN_ORIGIN,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    await set_challenge(authentication_id, json.dumps(challenge_payload).encode())

    return authentication_id, authentication_options_dict


async def verify_authentication_credential(
    db: AsyncSession,
    authentication_id: str,
    credential: dict,
) -> tuple[uuid.UUID, uuid.UUID]:
    """
    Verify WebAuthn authentication credential and update device login state.
    """
    challenge_data = await get_challenge(authentication_id)

    if challenge_data is None:
        raise AuthError("challenge expired or invalid")

    try:
        challenge_payload = json.loads(challenge_data.decode())
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise AuthError("invalid challenge data") from e

    if challenge_payload.get("purpose") != "authentication":
        raise AuthError("challenge purpose mismatch")

    user_id = uuid.UUID(challenge_payload["user_id"])
    device_id = uuid.UUID(challenge_payload["device_id"])

    result = await db.execute(sa.select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()

    if device is None or not device.is_active:
        raise AuthError("inactive or missing device")

    if device.credential_id != challenge_payload["credential_id"]:
        raise AuthError("credential mismatch")

    created_at_str = challenge_payload.get("created_at")
    if created_at_str:
        try:
            created_at = datetime.fromisoformat(created_at_str)
        except ValueError as exc:
            raise AuthError("invalid challenge data") from exc

        if datetime.now(timezone.utc) > created_at + timedelta(
            seconds=(
                settings.WEBAUTHN_CHALLENGE_TTL_SECONDS
                + settings.CLOCK_SKEW_TOLERANCE_SECONDS
            )
        ):
            raise AuthError("challenge expired or invalid")

    try:
        verified_assertion = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge_payload["challenge"]),
            expected_origin=settings.WEBAUTHN_ORIGIN,
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            credential_public_key=device.public_key,
            credential_current_sign_count=device.sign_count,
            require_user_verification=False,
        )
    except Exception as e:
        raise AuthError(f"credential verification failed: {str(e)}") from e

    device.sign_count = verified_assertion.new_sign_count or device.sign_count
    device.last_login_at = datetime.now(timezone.utc)

    await clear_device_reauthentication_required(str(device_id))
    await db.commit()

    return user_id, device_id


async def verify_registration_credential(
    db: AsyncSession,
    registration_id: str,
    credential: dict,
) -> tuple[uuid.UUID, uuid.UUID]:
    """
    Verify WebAuthn registration credential and persist the device.
    """
    challenge_data = await get_challenge(registration_id)

    if challenge_data is None:
        raise AuthError("challenge expired or invalid")

    try:
        challenge_payload = json.loads(challenge_data.decode())
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise AuthError("invalid challenge data") from e

    if challenge_payload.get("purpose") != "registration":
        raise AuthError("challenge purpose mismatch")

    user_id = uuid.UUID(challenge_payload["user_id"])
    device_name = challenge_payload.get("device_name")
    device_metadata = challenge_payload.get("device_metadata", {})

    created_at_str = challenge_payload.get("created_at")
    if created_at_str:
        try:
            created_at = datetime.fromisoformat(created_at_str)
        except ValueError as exc:
            raise AuthError("invalid challenge data") from exc

        if datetime.now(timezone.utc) > created_at + timedelta(
            seconds=(
                settings.WEBAUTHN_CHALLENGE_TTL_SECONDS
                + settings.CLOCK_SKEW_TOLERANCE_SECONDS
            )
        ):
            raise AuthError("challenge expired or invalid")

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

    credential_id = verified_credential.credential_id
    public_key = verified_credential.credential_public_key
    sign_count = verified_credential.sign_count or 0

    result = await db.execute(
        sa.select(Device).where(Device.credential_id == credential_id)
    )
    if result.scalar_one_or_none() is not None:
        raise ConflictError("credential_id already registered")

    result = await db.execute(
        sa.select(Device).where(
            sa.and_(Device.user_id == user_id, Device.is_active.is_(True))
        )
    )
    if result.scalar_one_or_none() is not None:
        raise ConflictError(
            "user already has an active device (concurrent registration detected)"
        )

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
