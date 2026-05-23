from __future__ import annotations

import asyncio
import uuid

from app.core.security import create_access_token
from app.infra import redis_client as rc
from app.infra.redis_keys import RATE_LIMIT_KEY


def test_set_rate_limit_allows_when_below(monkeypatch) -> None:
    async def fake_execute_command(*a, **k):
        return 1

    monkeypatch.setattr(rc.redis_client, "execute_command", fake_execute_command)

    result = asyncio.run(rc.set_rate_limit("k", 10, 60))
    assert result is True


def test_set_rate_limit_blocks_when_over(monkeypatch) -> None:
    async def fake_execute_command(*a, **k):
        return 11

    monkeypatch.setattr(rc.redis_client, "execute_command", fake_execute_command)

    result = asyncio.run(rc.set_rate_limit("k", 10, 60))
    assert result is False


def test_require_rate_limit_local_fallback_blocks_after_limit(
    app_client, monkeypatch
) -> None:
    import app.core.rate_limit as rlmod

    # Force Redis failure by replacing set_rate_limit with one that raises
    def raising_set_rate_limit(*a, **k):
        raise Exception("redis down")

    monkeypatch.setattr(rlmod, "set_rate_limit", raising_set_rate_limit)

    # Reset local counters
    rlmod._LOCAL_RATE_LIMITS.clear()

    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    token_a = create_access_token({"sub": user_a, "device_id": str(uuid.uuid4())})
    token_b = create_access_token({"sub": user_b, "device_id": str(uuid.uuid4())})
    headers_a = {
        "x-forwarded-for": "127.0.0.1",
        "authorization": f"Bearer {token_a}",
    }
    headers_b = {
        "x-forwarded-for": "127.0.0.1",
        "authorization": f"Bearer {token_b}",
    }

    # Consume allowed requests for user A on same IP
    for _ in range(rlmod.RATE_LIMIT_REQUESTS):
        resp = app_client.post("/api/v1/session/refresh", headers=headers_a)
        assert resp.status_code != 429

    # Next request for user A should be blocked
    resp = app_client.post("/api/v1/session/refresh", headers=headers_a)
    assert resp.status_code == 429

    # User B on same IP should still have its own quota
    resp = app_client.post("/api/v1/session/refresh", headers=headers_b)
    assert resp.status_code != 429


def test_require_rate_limit_uses_ip_user_path_key(app_client, monkeypatch) -> None:
    import app.core.rate_limit as rlmod

    captured: dict[str, str] = {}
    user = str(uuid.uuid4())
    token = create_access_token({"sub": user, "device_id": str(uuid.uuid4())})

    async def capture_set_rate_limit(key: str, *a, **k):
        captured["key"] = key
        return True

    monkeypatch.setattr(rlmod, "set_rate_limit", capture_set_rate_limit)

    headers = {
        "x-forwarded-for": "198.51.100.10",
        "authorization": f"Bearer {token}",
    }
    app_client.post("/api/v1/session/refresh", headers=headers)

    assert captured["key"] == RATE_LIMIT_KEY.format(
        client_ip="198.51.100.10",
        user=user,
        path="/api/v1/session/refresh",
    )
