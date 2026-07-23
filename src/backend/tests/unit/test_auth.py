from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt
from starlette.requests import Request

from app.core.config import settings
from app.core.errors import ERR_INVALID_TOKEN, ERR_TOKEN_REVOKED, ERR_UNAUTHORIZED
from app.core.metrics import (
    vault_auth_token_expiry_failures_total,
    vault_auth_token_scope_failures_total,
    vault_auth_token_validations_total,
)
from app.core.middleware.auth import JWTAuthMiddleware, require_vault_scope


def _generate_rsa_keypair() -> tuple[str, str]:
    """Generate a fresh 2048-bit RSA key pair and return (private_pem, public_pem)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    pub_pem = (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return priv_pem, pub_pem


@pytest.fixture(autouse=True)
def configure_test_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[tuple[str, str], None, None]:
    """Generate ephemeral RSA keys, write to temp files, patch settings.

    Yields (private_key_pem, public_key_pem) so tests can sign tokens.
    Keys are generated fresh each run — no secrets in any tracked file.
    """
    priv_pem, pub_pem = _generate_rsa_keypair()
    priv_key_file = tmp_path / "test_private_key.pem"
    pub_key_file = tmp_path / "test_public_key.pem"
    priv_key_file.write_text(priv_pem)
    pub_key_file.write_text(pub_pem)

    # Patch the settings singleton directly (it was instantiated at import time,
    # so monkeypatch.setenv alone won't affect it).
    monkeypatch.setattr(settings, "JWT_PUBLIC_KEY", str(pub_key_file))
    monkeypatch.setattr(settings, "REVOCATION_LIST_BACKEND", "redis")
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-key")
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(settings, "WEBAUTHN_RP_ID", "localhost")
    monkeypatch.setattr(settings, "WEBAUTHN_ORIGIN", "http://localhost")

    yield priv_pem, pub_pem


def _create_token(claims: dict[str, object], key: str) -> str:
    defaults = {
        "sub": "user-123",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
        "scope": "vault:read",
        "jti": "unique-jti",
    }
    defaults.update(claims)
    return jwt.encode(defaults, key, algorithm="RS256")


@pytest.mark.asyncio
async def test_valid_token_passes(
    configure_test_settings: tuple[str, str],
) -> None:
    priv_key, _ = configure_test_settings
    token = _create_token({}, priv_key)
    middleware = JWTAuthMiddleware()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )

    result = await middleware(request)
    assert result["payload"]["sub"] == "user-123"
    assert vault_auth_token_validations_total.labels(status="success")._value.get() >= 1


@pytest.mark.asyncio
async def test_expired_token_rejected_with_err_unauthorized(
    configure_test_settings: tuple[str, str],
) -> None:
    priv_key, _ = configure_test_settings
    token = _create_token(
        {"exp": int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp())},
        priv_key,
    )
    middleware = JWTAuthMiddleware()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )

    with pytest.raises(ERR_UNAUTHORIZED):
        await middleware(request)
    assert vault_auth_token_expiry_failures_total._value.get() >= 1


@pytest.mark.asyncio
async def test_malformed_token_rejected_with_err_invalid_token(
    configure_test_settings: tuple[str, str],
) -> None:
    middleware = JWTAuthMiddleware()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", b"Bearer not-a-token")],
        }
    )

    with pytest.raises(ERR_INVALID_TOKEN):
        await middleware(request)


@pytest.mark.asyncio
async def test_revoked_token_rejected_with_err_token_revoked(
    configure_test_settings: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    priv_key, _ = configure_test_settings
    token = _create_token({"jti": "revoked-jti"}, priv_key)
    middleware = JWTAuthMiddleware()

    async def fake_is_token_revoked(self, token_value: str, jti: str) -> bool:  # type: ignore[override]
        return True

    monkeypatch.setattr(JWTAuthMiddleware, "_is_token_revoked", fake_is_token_revoked)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )

    with pytest.raises(ERR_TOKEN_REVOKED):
        await middleware(request)


@pytest.mark.asyncio
async def test_scope_mismatch_rejected_with_err_unauthorized(
    configure_test_settings: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    priv_key, _ = configure_test_settings
    token = _create_token({"scope": "vault:write"}, priv_key)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )

    async def fake_middleware(self: object, request: object) -> dict[str, object]:
        return {"payload": {"scope": "vault:write"}}

    monkeypatch.setattr(JWTAuthMiddleware, "__call__", fake_middleware)

    with pytest.raises(ERR_UNAUTHORIZED):
        await require_vault_scope("vault:read")(request)
    assert vault_auth_token_scope_failures_total._value.get() >= 1
