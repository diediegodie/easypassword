from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

from app.core.config import settings
from app.infra.redis_keys import DEVICE_REAUTH_REQUIRED_KEY, WEBAUTHN_CHALLENGE_KEY

redis_client: Redis | None = None


def _new_redis_client() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=False)


@asynccontextmanager
async def _redis_client_context() -> AsyncGenerator[Redis, None]:
    if redis_client is not None:
        yield redis_client
        return

    client = _new_redis_client()
    try:
        yield client
    finally:
        await client.close()


@asynccontextmanager
async def get_redis() -> AsyncGenerator[Redis, None]:
    async with _redis_client_context() as client:
        yield client


async def set_challenge(challenge_id: str, challenge_bytes: bytes) -> None:
    key = WEBAUTHN_CHALLENGE_KEY.format(challenge_id)
    ttl = settings.WEBAUTHN_CHALLENGE_TTL_SECONDS
    async with _redis_client_context() as client:
        await client.setex(
            key,
            ttl,
            challenge_bytes,
        )


async def get_challenge(challenge_id: str) -> bytes | None:
    key = WEBAUTHN_CHALLENGE_KEY.format(challenge_id)
    async with _redis_client_context() as client:
        try:
            value = await client.getdel(key)
        except AttributeError:
            value = await client.get(key)
            if value is not None:
                await client.delete(key)
    return value


async def set_device_reauthentication_required(device_id: str) -> None:
    key = DEVICE_REAUTH_REQUIRED_KEY.format(device_id)
    async with _redis_client_context() as client:
        await client.setex(
            key,
            settings.WEBAUTHN_REAUTH_REQUIRED_TTL_SECONDS,
            b"1",
        )


async def clear_device_reauthentication_required(device_id: str) -> None:
    key = DEVICE_REAUTH_REQUIRED_KEY.format(device_id)
    async with _redis_client_context() as client:
        await client.delete(key)


async def is_device_reauthentication_required(device_id: str) -> bool:
    key = DEVICE_REAUTH_REQUIRED_KEY.format(device_id)
    async with _redis_client_context() as client:
        return await client.get(key) is not None


_RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


async def set_rate_limit(key: str, max_requests: int, window_seconds: int) -> bool:
    async with _redis_client_context() as client:
        current = await client.execute_command(
            "EVAL",
            _RATE_LIMIT_SCRIPT,
            1,
            key,
            window_seconds,
        )
    if current is None:
        return False
    return int(current) <= max_requests


from app.infra.redis_keys import REPLAY_CACHE_KEY


async def add_replay_blob(user_id: str, blob_hash: str, ttl: int) -> bool:
    key = REPLAY_CACHE_KEY.format(user_id=user_id, blob_hash=blob_hash)
    async with _redis_client_context() as client:
        result = await client.set(key, b"1", nx=True, ex=ttl)
    return result is True
