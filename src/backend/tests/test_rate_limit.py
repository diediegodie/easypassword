from __future__ import annotations

import asyncio

from app.infra import redis_client as rc


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

    headers = {"x-forwarded-for": "127.0.0.1"}

    # Consume allowed requests
    for _ in range(rlmod.RATE_LIMIT_REQUESTS):
        resp = app_client.post("/api/v1/session/refresh", headers=headers)
        assert resp.status_code != 429

    # Next request should be blocked by local fallback
    resp = app_client.post("/api/v1/session/refresh", headers=headers)
    assert resp.status_code == 429
