from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import require_rate_limit
from app.core.security import refresh_cookie_secure
from app.infra.database import get_db
from app.modules.auth.schemas import (
    AuthenticationCompletionRequest,
    AuthenticationCompletionResponse,
    AuthenticationInitiationRequest,
    AuthenticationInitiationResponse,
    RegistrationCompletionRequest,
    RegistrationCompletionResponse,
    RegistrationInitiationRequest,
    RegistrationInitiationResponse,
)
from app.modules.auth.service import (
    generate_authentication_options_for_user,
    generate_registration_options_for_user,
    verify_authentication_credential,
    verify_registration_credential,
)
from app.modules.session.service import create_session

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    dependencies=[Depends(require_rate_limit)],
)


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/register/options")
async def register_options(
    request: RegistrationInitiationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RegistrationInitiationResponse:
    """
    Initiate WebAuthn registration for a new device.

    This endpoint generates WebAuthn registration options and stores a challenge
    in Redis for one-time consumption during verification. If the user doesn't exist,
    they will be created. If the user already has an active device, a 409 Conflict
    is returned (single-device policy).

    Returns:
        registration_id: Unique identifier for this registration session
        public_key: WebAuthn registration options for navigator.credentials.create()
    """
    registration_id, public_key = await generate_registration_options_for_user(
        db=db,
        email=request.email,
        device_name=request.device_name,
        device_metadata=request.device_metadata,
    )
    return RegistrationInitiationResponse(
        registration_id=registration_id,
        public_key=public_key,
    )


@router.post("/login/options")
async def login_options(
    request: AuthenticationInitiationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthenticationInitiationResponse:
    """
    Initiate WebAuthn authentication for an existing device.

    This endpoint returns WebAuthn assertion options and stores a one-time
    challenge in Redis. The login flow is only valid for an active device.
    """
    authentication_id, public_key = await generate_authentication_options_for_user(
        db=db,
        email=request.email,
    )
    return AuthenticationInitiationResponse(
        authentication_id=authentication_id,
        public_key=public_key,
    )


@router.post("/login/verify")
async def login_verify(
    request: AuthenticationCompletionRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthenticationCompletionResponse:
    """
    Complete WebAuthn authentication and issue session tokens.

    The challenge is consumed one-time from Redis. After successful verification,
    an access token is returned and a refresh token cookie is set.
    """
    user_id, device_id = await verify_authentication_credential(
        db=db,
        authentication_id=request.authentication_id,
        credential=request.credential,
    )

    access_token, refresh_token = await create_session(
        db=db, user_id=user_id, device_id=device_id
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=refresh_cookie_secure(),
        samesite="strict",
        path="/",
    )

    return AuthenticationCompletionResponse(
        access_token=access_token,
        device_id=device_id,
        user_id=user_id,
        token_type="Bearer",
    )


@router.post("/register/verify")
async def register_verify(
    request: RegistrationCompletionRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RegistrationCompletionResponse:
    """
    Complete WebAuthn registration and issue initial session.

    This endpoint verifies the WebAuthn attestation credential, persists the device,
    and issues initial session tokens. The challenge is consumed one-time from Redis
    and cannot be reused. After successful verification, an access token is returned
    in the response and a refresh token is set in an HttpOnly cookie.

    Returns:
        access_token: JWT access token (5-minute TTL)
        device_id: UUID of the registered device
        user_id: UUID of the user
        token_type: Always "Bearer"
    """
    user_id, device_id = await verify_registration_credential(
        db=db,
        registration_id=request.registration_id,
        credential=request.credential,
    )

    # Issue initial session tokens
    access_token, refresh_token = await create_session(
        db=db, user_id=user_id, device_id=device_id
    )

    # Set refresh token in HttpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=refresh_cookie_secure(),
        samesite="strict",
        path="/",
    )

    return RegistrationCompletionResponse(
        access_token=access_token,
        device_id=device_id,
        user_id=user_id,
        token_type="Bearer",
    )
