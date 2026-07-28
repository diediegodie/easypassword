"""Integration tests for WebAuthn registration HTTP endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import Device, User
from app.modules.session.models import Session

pytestmark = pytest.mark.integration


class TestRegistrationEndpoints:
    """Integration tests for registration endpoints."""

    @pytest.fixture
    def client(self, app_client: TestClient) -> TestClient:
        """Provide test client."""
        return app_client

    def test_register_options_endpoint_mounted(self, client: TestClient) -> None:
        """Test that registration options endpoint is reachable."""
        response = client.post(
            "/api/v1/auth/register/options",
            json={
                "email": "test@example.com",
                "device_name": "Test Device",
            },
        )
        assert response.status_code != 404

    def test_register_options_creates_user(self, client: TestClient) -> None:
        """Test that registration options endpoint creates new user."""
        response = client.post(
            "/api/v1/auth/register/options",
            json={
                "email": "newuser@example.com",
                "device_name": "iPhone",
                "device_metadata": {"platform": "iOS"},
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "registration_id" in data
        assert "public_key" in data
        assert "challenge" in data["public_key"]
        assert "rp" in data["public_key"]

    def test_register_options_rejects_duplicate_active_device(
        self, client: TestClient, db_session: AsyncSession
    ) -> None:
        """Test that options endpoint rejects when user has active device."""

        async def setup_user_with_device():
            user = User(email="existing@example.com", account_status="active")
            db_session.add(user)
            await db_session.flush()

            device = Device(
                user_id=user.id,
                credential_id="existing-cred",
                public_key=b"test-key",
                sign_count=0,
                device_name="Existing",
                device_metadata={},
                is_active=True,
            )
            db_session.add(device)
            await db_session.commit()

        import asyncio

        asyncio.run(setup_user_with_device())

        response = client.post(
            "/api/v1/auth/register/options",
            json={"email": "existing@example.com"},
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_register_options_email_normalization(
        self, client: TestClient, db_session: AsyncSession
    ) -> None:
        """Test that email is normalized."""
        response = client.post(
            "/api/v1/auth/register/options",
            json={
                "email": "TestUser@Example.COM",
                "device_name": "Test",
            },
        )

        assert response.status_code == 200

        result = await db_session.execute(
            select(User).where(User.email == "testuser@example.com")
        )
        user = result.scalar_one_or_none()
        assert user is not None

    def test_register_verify_endpoint_mounted(self, client: TestClient) -> None:
        """Test that registration verify endpoint is reachable."""
        response = client.post(
            "/api/v1/auth/register/verify",
            json={
                "registration_id": "test-id",
                "credential": {},
            },
        )
        assert response.status_code != 404

    def test_register_verify_rejects_missing_challenge(
        self, client: TestClient
    ) -> None:
        """Test that verify rejects missing challenge."""
        response = client.post(
            "/api/v1/auth/register/verify",
            json={
                "registration_id": "non-existent-id",
                "credential": {"id": "cred"},
            },
        )

        assert response.status_code == 401

    def test_register_verify_full_flow(self, client: TestClient) -> None:
        """Test complete registration flow: options -> verify."""

        options_response = client.post(
            "/api/v1/auth/register/options",
            json={
                "email": "fullflow@example.com",
                "device_name": "Full Flow Device",
                "device_metadata": {"test": True},
            },
        )

        assert options_response.status_code == 200
        options_data = options_response.json()
        registration_id = options_data["registration_id"]

        mock_credential = {
            "id": "credential-id",
            "response": {
                "clientDataJSON": "test-data",
                "attestationObject": "test-object",
            },
        }

        with patch(
            "app.modules.auth.service.verify_registration_response"
        ) as mock_verify:
            mock_verified = MagicMock()
            mock_verified.credential_id = "test-credential-id"
            mock_verified.credential_public_key = b"test-public-key"
            mock_verified.sign_count = 0
            mock_verify.return_value = mock_verified

            verify_response = client.post(
                "/api/v1/auth/register/verify",
                json={
                    "registration_id": registration_id,
                    "credential": mock_credential,
                },
            )

        assert verify_response.status_code == 200
        verify_data = verify_response.json()

        assert "access_token" in verify_data
        assert "device_id" in verify_data
        assert "user_id" in verify_data
        assert verify_data["token_type"] == "Bearer"

        assert "refresh_token" in verify_response.cookies

        async def check_session():
            from sqlalchemy.ext.asyncio import AsyncSession

            db = AsyncSession()
            result = await db.execute(
                select(Session).where(
                    Session.user_id == uuid.UUID(verify_data["user_id"])
                )
            )
            session = result.scalar_one_or_none()
            assert session is not None
            assert session.device_id == uuid.UUID(verify_data["device_id"])
            await db.close()

    def test_register_verify_replay_protection(self, client: TestClient) -> None:
        """Test that challenge cannot be reused."""

        options_response = client.post(
            "/api/v1/auth/register/options",
            json={"email": "replay@example.com"},
        )

        registration_id = options_response.json()["registration_id"]

        mock_credential = {"id": "cred"}

        with patch(
            "app.modules.auth.service.verify_registration_response"
        ) as mock_verify:
            mock_verified = MagicMock()
            mock_verified.credential_id = "cred-id-1"
            mock_verified.credential_public_key = b"key-1"
            mock_verified.sign_count = 0
            mock_verify.return_value = mock_verified

            response1 = client.post(
                "/api/v1/auth/register/verify",
                json={
                    "registration_id": registration_id,
                    "credential": mock_credential,
                },
            )

        assert response1.status_code == 200

        response2 = client.post(
            "/api/v1/auth/register/verify",
            json={
                "registration_id": registration_id,
                "credential": mock_credential,
            },
        )

        assert response2.status_code == 401

    def test_register_verify_issues_session_tokens(self, client: TestClient) -> None:
        """Test that successful registration issues session tokens."""

        options_response = client.post(
            "/api/v1/auth/register/options",
            json={"email": "tokens@example.com", "device_name": "Token Test"},
        )

        registration_id = options_response.json()["registration_id"]

        with patch(
            "app.modules.auth.service.verify_registration_response"
        ) as mock_verify:
            mock_verified = MagicMock()
            mock_verified.credential_id = "token-cred-id"
            mock_verified.credential_public_key = b"token-key"
            mock_verified.sign_count = 0
            mock_verify.return_value = mock_verified

            verify_response = client.post(
                "/api/v1/auth/register/verify",
                json={
                    "registration_id": registration_id,
                    "credential": {"id": "cred"},
                },
            )

        assert verify_response.status_code == 200
        data = verify_response.json()

        access_token = data["access_token"]
        assert len(access_token.split(".")) == 3  # JWT has 3 parts

        cookies = verify_response.cookies
        assert cookies.get("refresh_token") is not None

    def test_register_options_optional_fields(self, client: TestClient) -> None:
        """Test that device_name and device_metadata are optional."""
        response = client.post(
            "/api/v1/auth/register/options",
            json={"email": "minimal@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "registration_id" in data
        assert "public_key" in data
