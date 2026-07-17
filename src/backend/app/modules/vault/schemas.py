from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class VaultItemResponse(BaseModel):
    id: str
    service_name: str
    login_name: str
    password_blob: str
    notes_blob: str | None = None
    created_at: datetime
    updated_at: datetime


class VaultCreateRequest(BaseModel):
    service_name: str = Field(..., min_length=1, max_length=255)
    login_name: str = Field(..., min_length=1, max_length=255)
    password_blob: str = Field(..., min_length=1)
    notes_blob: str | None = None


class VaultUpdateRequest(BaseModel):
    service_name: str | None = Field(None, min_length=1, max_length=255)
    login_name: str | None = Field(None, min_length=1, max_length=255)
    password_blob: str | None = Field(None, min_length=1)
    notes_blob: str | None = None
