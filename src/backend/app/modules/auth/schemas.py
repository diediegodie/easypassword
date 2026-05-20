"""Request and response schemas for WebAuthn registration."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegistrationInitiationRequest(BaseModel):
    """Request schema for WebAuthn registration initiation."""

    email: EmailStr
    device_name: str | None = Field(
        None,
        max_length=255,
        description="User-friendly name for the device (e.g., 'iPhone', 'MacBook')",
    )
    device_metadata: dict[str, Any] | None = Field(
        None,
        description="Optional device metadata (platform, browser, etc.)",
    )


class RegistrationInitiationResponse(BaseModel):
    """Response schema for WebAuthn registration initiation."""

    registration_id: str = Field(
        description="Server-generated unique identifier for this registration session"
    )
    public_key: dict[str, Any] = Field(
        description="WebAuthn registration options for navigator.credentials.create()"
    )


class RegistrationCompletionRequest(BaseModel):
    """Request schema for WebAuthn registration completion."""

    registration_id: str = Field(
        description="The registration_id returned from initiation endpoint"
    )
    credential: dict[str, Any] = Field(
        description="Full attestation payload from navigator.credentials.create()"
    )


class RegistrationCompletionResponse(BaseModel):
    """Response schema for WebAuthn registration completion."""

    access_token: str
    device_id: UUID
    user_id: UUID
    token_type: str = "Bearer"


class AuthenticationInitiationRequest(BaseModel):
    """Request schema for WebAuthn authentication initiation."""

    email: EmailStr


class AuthenticationInitiationResponse(BaseModel):
    """Response schema for WebAuthn authentication initiation."""

    authentication_id: str = Field(
        description="Server-generated unique identifier for this authentication session"
    )
    public_key: dict[str, Any] = Field(
        description="WebAuthn authentication options for navigator.credentials.get()"
    )


class AuthenticationCompletionRequest(BaseModel):
    """Request schema for WebAuthn authentication completion."""

    authentication_id: str = Field(
        description="The authentication_id returned from initiation endpoint"
    )
    credential: dict[str, Any] = Field(
        description="Full assertion payload from navigator.credentials.get()"
    )


class AuthenticationCompletionResponse(BaseModel):
    """Response schema for WebAuthn authentication completion."""

    access_token: str
    device_id: UUID
    user_id: UUID
    token_type: str = "Bearer"
