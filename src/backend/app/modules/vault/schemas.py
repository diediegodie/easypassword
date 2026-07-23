from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

SUSPICIOUS_KEY_NAMES = {
    "password",
    "secret",
    "private_key",
    "encryption_key",
    "key",
    "master_key",
    "credentials",
}


class VaultItemResponse(BaseModel):
    id: str
    service_name: str
    login_name: str
    password_blob: str
    notes_blob: str | None = None
    created_at: datetime
    updated_at: datetime
    blob_version_detected: int = 1
    migration_recommended: bool = False


class VaultCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_name: str = Field(..., min_length=1, max_length=255)
    login_name: str = Field(..., min_length=1, max_length=255)
    password_blob: str = Field(..., min_length=1)
    notes_blob: str | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_suspicious_keys(cls, values: dict[str, object]) -> dict[str, object]:
        if not isinstance(values, dict):
            return values
        for key in values.keys():
            if key in SUSPICIOUS_KEY_NAMES:
                raise ValueError(f"suspicious key field: {key}")
        return values


class VaultUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_name: str | None = Field(None, min_length=1, max_length=255)
    login_name: str | None = Field(None, min_length=1, max_length=255)
    password_blob: str | None = Field(None, min_length=1)
    notes_blob: str | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_suspicious_keys(cls, values: dict[str, object]) -> dict[str, object]:
        if not isinstance(values, dict):
            return values
        for key in values.keys():
            if key in SUSPICIOUS_KEY_NAMES:
                raise ValueError(f"suspicious key field: {key}")
        return values
