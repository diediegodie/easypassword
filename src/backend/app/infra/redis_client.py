from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

from app.core.config import settings
from app.core.metrics import (
    replay_cache_evictions_total,
    replay_cache_hit_rate,
    replay_cache_hits_total,
    replay_cache_misses_total,
    replay_cache_size,
    vault_iv_conflicts_total,
)
from app.infra.redis_keys import (
    DEVICE_REAUTH_REQUIRED_KEY,
    IV_CACHE_KEY,
    REPLAY_CACHE_KEY,
    WEBAUTHN_CHALLENGE_KEY,
)

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


async def get_redis() -> AsyncGenerator[Redis, None]:
    """Plain async generator for use with FastAPI ``Depends()``."""
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


async def add_replay_blob(user_id: str, blob_hash: str, ttl: int) -> bool:
    """
    This function adds a blob hash to the replay cache for a given user.
    It returns True if the blob was added (cache miss), or False if it was
    already present (cache hit). It also updates Prometheus metrics accordingly.
    """
    key = REPLAY_CACHE_KEY.format(user_id=user_id, blob_hash=blob_hash)
    async with _redis_client_context() as client:
        result = await client.set(key, b"1", nx=True, ex=ttl)

        if result is True:
            replay_cache_misses_total.inc()
            current_size = await client.dbsize()
            replay_cache_size.set(current_size)
            return True
        else:
            replay_cache_hits_total.inc()
            total_ops = await client.get("replay_cache_total_ops")
            if total_ops is not None:
                hits = await client.get("replay_cache_hits")
                if hits is not None:
                    hit_rate = int(hits) / int(total_ops)
                    replay_cache_hit_rate.observe(hit_rate)
            return False


async def track_replay_cache_eviction():
    """This function should be called when a key expires in the replay cache."""
    replay_cache_evictions_total.inc()
    async with _redis_client_context() as client:
        current_size = await client.dbsize()
        replay_cache_size.set(current_size)


async def increment_replay_cache_total_ops():
    """Increment the total operations counter for hit rate calculation."""
    async with _redis_client_context() as client:
        await client.incr("replay_cache_total_ops")


async def check_iv_duplicate(user_id: str, iv_hex: str, ttl: int) -> bool:
    """Check for a duplicate IV within a user context."""
    key = IV_CACHE_KEY.format(user_id=user_id, iv_hex=iv_hex)
    async with _redis_client_context() as client:
        result = await client.set(key, b"1", nx=True, ex=ttl)
        if result is True:
            return True
        else:
            vault_iv_conflicts_total.inc()
            return False
