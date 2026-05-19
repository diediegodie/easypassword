from __future__ import annotations

import asyncio

import pytest

from app.infra import redis_client as rc
from app.infra.redis_keys import RATE_LIMIT_KEY


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rate_limit_integration_end_to_end(fake_redis) -> None:
    # Uses real Redis service when RUN_INTEGRATION=1; otherwise uses an
    # in-process async fake Redis provided by the `fake_redis` fixture.
    key = RATE_LIMIT_KEY.format(
        client_ip="127.0.0.1",
        user="user-int",
        path="/int/test",
    )
    max_requests = 3
    window_seconds = 2

    # Allow up to max_requests
    for _ in range(max_requests):
        allowed = await rc.set_rate_limit(key, max_requests, window_seconds)
        assert allowed

    # Next request should be blocked
    allowed = await rc.set_rate_limit(key, max_requests, window_seconds)
    assert not allowed

    # Wait for the window to expire and ensure requests are allowed again
    await asyncio.sleep(window_seconds + 0.5)
    allowed = await rc.set_rate_limit(key, max_requests, window_seconds)
    assert allowed
