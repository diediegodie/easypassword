from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_refresh_token,
)


def test_test_settings_fixture(test_settings: Settings) -> None:
    assert test_settings.APP_ENV == "development"
    assert test_settings.REDIS_URL.startswith("redis://")


def test_access_token_round_trip() -> None:
    token = create_access_token({"sub": "user-123", "device_id": "device-456"})
    payload = decode_access_token(token)

    assert payload["sub"] == "user-123"
    assert payload["device_id"] == "device-456"
    assert "iat" in payload
    assert "exp" in payload


def test_refresh_token_hash_verification() -> None:
    token = generate_refresh_token()
    token_hash = hash_refresh_token(token)

    assert verify_refresh_token(token, token_hash)
    assert not verify_refresh_token(f"{token}x", token_hash)


def test_generate_refresh_token_is_unique() -> None:
    token_one = generate_refresh_token()
    token_two = generate_refresh_token()

    assert token_one
    assert token_two
    assert token_one != token_two


def test_settings_requires_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in ("SECRET_KEY", "DATABASE_URL", "WEBAUTHN_RP_ID", "WEBAUTHN_ORIGIN"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValidationError):
        # We pass _env_file=None to ensure pydantic-settings doesn't load a .env file
        # that might exist in the environment, which would satisfy the validation
        # even if we deleted the environment variables.
        Settings(_env_file=None)  # type: ignore


def test_health_endpoint_returns_ok(app_client) -> None:
    response = app_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
