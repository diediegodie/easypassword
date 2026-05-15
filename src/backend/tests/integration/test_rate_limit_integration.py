from __future__ import annotations

import asyncio
import time

import pytest

from app.infra import redis_client as rc
from app.infra.redis_keys import RATE_LIMIT_KEY


@pytest.mark.integration
def test_rate_limit_integration_end_to_end() -> None:
    # Uses real Redis service. Configure CI to provide REDIS_URL=redis://redis:6379
    key = RATE_LIMIT_KEY.format(client_ip="127.0.0.1", path="/int/test")
    max_requests = 3
    window_seconds = 2

    # Allow up to max_requests
    for _ in range(max_requests):
        allowed = asyncio.run(rc.set_rate_limit(key, max_requests, window_seconds))
        assert allowed

    # Next request should be blocked
    allowed = asyncio.run(rc.set_rate_limit(key, max_requests, window_seconds))
    assert not allowed

    # Wait for the window to expire and ensure requests are allowed again
    time.sleep(window_seconds + 0.5)
    allowed = asyncio.run(rc.set_rate_limit(key, max_requests, window_seconds))
    assert allowed
