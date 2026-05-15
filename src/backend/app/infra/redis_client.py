from __future__ import annotations

from collections.abc import AsyncGenerator

from redis.asyncio import Redis

from app.core.config import settings
from app.infra.redis_keys import WEBAUTHN_CHALLENGE_KEY

redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=False)


async def get_redis() -> AsyncGenerator[Redis, None]:
    yield redis_client


async def set_challenge(challenge_id: str, challenge_bytes: bytes) -> None:
    key = WEBAUTHN_CHALLENGE_KEY.format(challenge_id)
    await redis_client.setex(
        key, settings.WEBAUTHN_CHALLENGE_TTL_SECONDS, challenge_bytes
    )


async def get_challenge(challenge_id: str) -> bytes | None:
    try:
        key = WEBAUTHN_CHALLENGE_KEY.format(challenge_id)
        value = await redis_client.getdel(key)
    except AttributeError:
        key = WEBAUTHN_CHALLENGE_KEY.format(challenge_id)
        value = await redis_client.get(key)
        if value is not None:
            await redis_client.delete(key)
    return value


_RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


async def set_rate_limit(key: str, max_requests: int, window_seconds: int) -> bool:
    current = await redis_client.execute_command(
        "EVAL",
        _RATE_LIMIT_SCRIPT,
        1,
        key,
        window_seconds,
    )
    if current is None:
        return False
    return int(current) <= max_requests
