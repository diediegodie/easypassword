"""Integration tests for WebAuthn authentication HTTP endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.models import Device, User
from app.modules.session.models import Session
from app.modules.session.service import create_session

pytestmark = pytest.mark.integration


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
    async def test_protected_endpoint_inactivity_requires_webauthn(
        self, client: TestClient, db_session: AsyncSession
    ) -> None:
        user = User(email="protected-inactivity@example.com", account_status="active")
        db_session.add(user)
        await db_session.flush()

        device = Device(
            user_id=user.id,
            credential_id="protected-cred",
            public_key=b"key",
            sign_count=0,
            device_name="Device",
            device_metadata={},
            is_active=True,
        )
        db_session.add(device)
        await db_session.commit()

        access_token, refresh_token = await create_session(
            db_session,
            user.id,
            device.id,
        )
        assert access_token
        assert refresh_token

        initial_session = (
            await db_session.execute(select(Session).where(Session.user_id == user.id))
        ).scalar_one()
        initial_last_activity = initial_session.last_activity_at

        response = client.get(
            "/api/v1/protected/test",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        refreshed_session = (
            await db_session.execute(
                select(Session).where(Session.id == initial_session.id)
            )
        ).scalar_one()
        assert refreshed_session.last_activity_at >= initial_last_activity

        refreshed_session.last_activity_at = datetime.now(timezone.utc) - timedelta(
            seconds=settings.INACTIVITY_TIMEOUT_SECONDS + 1
        )
        await db_session.commit()

        response = client.get(
            "/api/v1/protected/test",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 401
        assert response.json()["code"] == "ReauthenticationRequired"
        assert response.json()["detail"] == "Session expired due to inactivity"

        options_response = client.post(
            "/api/v1/auth/login/options",
            json={"email": user.email},
        )
        assert options_response.status_code == 200
        authentication_id = options_response.json()["authentication_id"]

        mock_credential = {
            "id": "credential-id",
            "response": {
                "clientDataJSON": "data",
                "authenticatorData": "auth-data",
                "signature": "signature",
            },
        }

        with patch(
            "app.modules.auth.service.verify_authentication_response"
        ) as mock_verify:
            mock_verified = MagicMock()
            mock_verified.new_sign_count = 5
            mock_verify.return_value = mock_verified

            verify_response = client.post(
                "/api/v1/auth/login/verify",
                json={
                    "authentication_id": authentication_id,
                    "credential": mock_credential,
                },
            )

        assert verify_response.status_code == 200
        new_access_token = verify_response.json()["access_token"]

        second_protected_response = client.get(
            "/api/v1/protected/test",
            headers={"Authorization": f"Bearer {new_access_token}"},
        )
        assert second_protected_response.status_code == 200
        assert second_protected_response.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_refresh_endpoint_rejects_inactivity_until_webauthn_login(
        self, client: TestClient, db_session: AsyncSession
    ) -> None:
        user = User(email="refresh-endpoint@example.com", account_status="active")
        db_session.add(user)
        await db_session.flush()

        device = Device(
            user_id=user.id,
            credential_id="refresh-endpoint-cred",
            public_key=b"key",
            sign_count=0,
            device_name="Device",
            device_metadata={},
            is_active=True,
        )
        db_session.add(device)
        await db_session.commit()

        access_token, refresh_token = await create_session(
            db_session,
            user.id,
            device.id,
        )
        assert refresh_token

        session = (
            await db_session.execute(select(Session).where(Session.user_id == user.id))
        ).scalar_one()
        session.last_activity_at = datetime.now(timezone.utc) - timedelta(
            seconds=settings.INACTIVITY_TIMEOUT_SECONDS + 1
        )
        await db_session.commit()

        refresh_response = client.post(
            "/api/v1/session/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_response.status_code == 401
        assert refresh_response.json()["code"] == "ReauthenticationRequired"

        options_response = client.post(
            "/api/v1/auth/login/options",
            json={"email": user.email},
        )
        assert options_response.status_code == 200
        authentication_id = options_response.json()["authentication_id"]

        mock_credential = {
            "id": "credential-id",
            "response": {
                "clientDataJSON": "data",
                "authenticatorData": "auth-data",
                "signature": "signature",
            },
        }

        with patch(
            "app.modules.auth.service.verify_authentication_response"
        ) as mock_verify:
            mock_verified = MagicMock()
            mock_verified.new_sign_count = 5
            mock_verify.return_value = mock_verified

            verify_response = client.post(
                "/api/v1/auth/login/verify",
                json={
                    "authentication_id": authentication_id,
                    "credential": mock_credential,
                },
            )

        assert verify_response.status_code == 200
        new_refresh_token = verify_response.cookies.get("refresh_token")
        assert new_refresh_token is not None

        refresh_response_after = client.post(
            "/api/v1/session/refresh",
            json={"refresh_token": new_refresh_token},
        )
        assert refresh_response_after.status_code == 200
        assert "access_token" in refresh_response_after.json()

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
