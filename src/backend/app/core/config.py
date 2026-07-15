from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_settings import BaseSettings, SettingsConfigDict

# Determine the project root (where .env is located)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else None,
        extra="ignore",
        env_file_encoding="utf-8",
    )

    APP_ENV: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str
    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 5
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    WEBAUTHN_CHALLENGE_TTL_SECONDS: int = 90
    WEBAUTHN_REAUTH_REQUIRED_TTL_SECONDS: int = 90
    WEBAUTHN_RP_ID: str
    WEBAUTHN_RP_NAME: str = "EasyPassword"
    WEBAUTHN_ORIGIN: str
    CLOCK_SKEW_TOLERANCE_SECONDS: int = 120
    INACTIVITY_TIMEOUT_SECONDS: int = 60


if TYPE_CHECKING:
    settings = Settings.model_construct(
        SECRET_KEY="",
        DATABASE_URL="",
        WEBAUTHN_RP_ID="",
        WEBAUTHN_ORIGIN="",
    )
else:
    settings = Settings()
