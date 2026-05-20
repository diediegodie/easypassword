"""Integration tests for WebAuthn authentication HTTP endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import Device, User
from app.modules.session.models import Session


class TestAuthenticationEndpoints:
    """Integration tests for authentication endpoints."""

    @pytest.fixture
    def client(self, app_client: TestClient) -> TestClient:
        return app_client

    def test_login_options_endpoint_mounted(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/login/options",
            json={"email": "test@example.com"},
        )
        assert response.status_code != 404

    def test_login_verify_endpoint_mounted(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/login/verify",
            json={"authentication_id": "test", "credential": {}},
        )
        assert response.status_code != 404

    def test_login_options_rejects_missing_active_device(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/api/v1/auth/login/options",
            json={"email": "missing-device@example.com"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_options_rejects_inactive_device(
        self, client: TestClient, db_session: AsyncSession
    ) -> None:
        user = User(email="inactive-user@example.com", account_status="active")
        db_session.add(user)
        await db_session.flush()
        device = Device(
            user_id=user.id,
            credential_id="inactive-cred",
            public_key=b"key",
            sign_count=0,
            device_name="Inactive",
            device_metadata={},
            is_active=False,
        )
        db_session.add(device)
        await db_session.commit()

        response = client.post(
            "/api/v1/auth/login/options",
            json={"email": "inactive-user@example.com"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_options_returns_authentication_options(
        self, client: TestClient, db_session: AsyncSession
    ) -> None:
        user = User(email="login-options@example.com", account_status="active")
        db_session.add(user)
        await db_session.flush()

        device = Device(
            user_id=user.id,
            credential_id="login-cred",
            public_key=b"login-key",
            sign_count=0,
            device_name="Device",
            device_metadata={},
            is_active=True,
        )
        db_session.add(device)
        await db_session.commit()

        response = client.post(
            "/api/v1/auth/login/options",
            json={"email": "login-options@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "authentication_id" in data
        assert "public_key" in data
        assert "challenge" in data["public_key"]

    @pytest.mark.asyncio
    async def test_login_verify_full_flow(
        self, client: TestClient, db_session: AsyncSession
    ) -> None:
        user = User(email="full-flow@example.com", account_status="active")
        db_session.add(user)
        await db_session.flush()
        device = Device(
            user_id=user.id,
            credential_id="fullflow-cred",
            public_key=b"fullflow-key",
            sign_count=0,
            device_name="Device",
            device_metadata={},
            is_active=True,
        )
        db_session.add(device)
        await db_session.commit()
        email = user.email

        options_response = client.post(
            "/api/v1/auth/login/options",
            json={"email": email},
        )
        assert options_response.status_code == 200
        authentication_id = options_response.json()["authentication_id"]

        mock_credential = {
            "id": "credential-id",
            "response": {
                "clientDataJSON": "test-data",
                "authenticatorData": "auth-data",
                "signature": "signature",
            },
        }

        with patch(
            "app.modules.auth.service.verify_authentication_response"
        ) as mock_verify:
            mock_verified = MagicMock()
            mock_verified.new_sign_count = 7
            mock_verify.return_value = mock_verified

            verify_response = client.post(
                "/api/v1/auth/login/verify",
                json={
                    "authentication_id": authentication_id,
                    "credential": mock_credential,
                },
            )

        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert verify_data["user_id"] == str(user.id)
        assert verify_data["device_id"] == str(device.id)
        assert verify_data["token_type"] == "Bearer"
        assert "refresh_token" in verify_response.cookies

        async def check_session() -> None:
            result = await db_session.execute(
                select(Session).where(Session.user_id == user.id)
            )
            session = result.scalar_one_or_none()
            assert session is not None
            assert session.device_id == device.id

        await check_session()

    @pytest.mark.asyncio
    async def test_login_verify_rejects_invalid_assertion(
        self, client: TestClient, db_session: AsyncSession
    ) -> None:
        user = User(email="invalid-flow@example.com", account_status="active")
        db_session.add(user)
        await db_session.flush()
        device = Device(
            user_id=user.id,
            credential_id="invalid-cred",
            public_key=b"invalid-key",
            sign_count=0,
            device_name="Device",
            device_metadata={},
            is_active=True,
        )
        db_session.add(device)
        await db_session.commit()
        email = user.email

        options_response = client.post(
            "/api/v1/auth/login/options",
            json={"email": email},
        )
        authentication_id = options_response.json()["authentication_id"]

        with patch(
            "app.modules.auth.service.verify_authentication_response"
        ) as mock_verify:
            mock_verify.side_effect = ValueError("invalid signature")

            verify_response = client.post(
                "/api/v1/auth/login/verify",
                json={
                    "authentication_id": authentication_id,
                    "credential": {"id": "cred", "response": {}},
                },
            )

        assert verify_response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_verify_replay_protection(
        self, client: TestClient, db_session: AsyncSession
    ) -> None:
        user = User(email="replay-flow@example.com", account_status="active")
        db_session.add(user)
        await db_session.flush()
        device = Device(
            user_id=user.id,
            credential_id="replay-flow-cred",
            public_key=b"replay-key",
            sign_count=0,
            device_name="Device",
            device_metadata={},
            is_active=True,
        )
        db_session.add(device)
        await db_session.commit()
        email = user.email

        options_response = client.post(
            "/api/v1/auth/login/options",
            json={"email": email},
        )
        authentication_id = options_response.json()["authentication_id"]

        mock_credential = {"id": "cred", "response": {}}

        with patch(
            "app.modules.auth.service.verify_authentication_response"
        ) as mock_verify:
            mock_verified = MagicMock()
            mock_verified.new_sign_count = 1
            mock_verify.return_value = mock_verified

            response1 = client.post(
                "/api/v1/auth/login/verify",
                json={
                    "authentication_id": authentication_id,
                    "credential": mock_credential,
                },
            )

        assert response1.status_code == 200

        response2 = client.post(
            "/api/v1/auth/login/verify",
            json={
                "authentication_id": authentication_id,
                "credential": mock_credential,
            },
        )

        assert response2.status_code == 401
