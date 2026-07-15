from __future__ import annotations

import asyncio
import time

from app.core.config import settings
from app.infra import redis_client as rc
from app.infra.redis_keys import WEBAUTHN_CHALLENGE_KEY


def test_set_challenge_uses_ttl(monkeypatch) -> None:
    recorded: dict = {}

    async def fake_setex(key, ttl, value):
        recorded["key"] = key
        recorded["ttl"] = ttl
        recorded["value"] = value

    monkeypatch.setattr(rc.redis_client, "setex", fake_setex)

    challenge_id = "test-ch"
    challenge_bytes = b"bytes"

    asyncio.run(rc.set_challenge(challenge_id, challenge_bytes))

    assert recorded["ttl"] == settings.WEBAUTHN_CHALLENGE_TTL_SECONDS
    assert recorded["value"] == challenge_bytes
    assert recorded["key"] == WEBAUTHN_CHALLENGE_KEY.format(challenge_id)


def test_get_challenge_getdel(monkeypatch) -> None:
    async def fake_getdel(key):
        return b"ch-getdel"

    monkeypatch.setattr(rc.redis_client, "getdel", fake_getdel)

    value = asyncio.run(rc.get_challenge("id-getdel"))
    assert value == b"ch-getdel"


def test_get_challenge_fallback(monkeypatch) -> None:
    deleted = {}

    async def raise_attr(*a, **k):
        raise AttributeError

    async def fake_get(key):
        return b"ch-get"

    async def fake_delete(key):
        deleted["key"] = key

    monkeypatch.setattr(rc.redis_client, "getdel", raise_attr)
    monkeypatch.setattr(rc.redis_client, "get", fake_get)
    monkeypatch.setattr(rc.redis_client, "delete", fake_delete)

    value = asyncio.run(rc.get_challenge("id-fallback"))
    assert value == b"ch-get"
    assert deleted["key"] == WEBAUTHN_CHALLENGE_KEY.format("id-fallback")


def test_reauthentication_flag_uses_short_ttl(monkeypatch) -> None:
    recorded: dict[str, int | bytes | str] = {}

    async def fake_setex(key, ttl, value):
        recorded["key"] = key
        recorded["ttl"] = ttl
        recorded["value"] = value

    monkeypatch.setattr(rc.redis_client, "setex", fake_setex)

    asyncio.run(rc.set_device_reauthentication_required("device-reauth"))

    assert recorded["key"] == "device:reauth:device-reauth"
    assert recorded["ttl"] == settings.WEBAUTHN_REAUTH_REQUIRED_TTL_SECONDS
    ttl = recorded["ttl"]
    assert isinstance(ttl, int)
    assert ttl < 120
    assert recorded["value"] == b"1"


def test_clear_reauthentication_flag(monkeypatch) -> None:
    deleted: dict[str, str] = {}

    async def fake_delete(key):
        deleted["key"] = key

    monkeypatch.setattr(rc.redis_client, "delete", fake_delete)

    asyncio.run(rc.clear_device_reauthentication_required("device-reauth"))

    assert deleted["key"] == "device:reauth:device-reauth"


def test_is_device_reauthentication_required(monkeypatch) -> None:
    async def fake_get(key):
        return b"1"

    monkeypatch.setattr(rc.redis_client, "get", fake_get)

    assert asyncio.run(rc.is_device_reauthentication_required("device-reauth")) is True


def test_reauthentication_flag_expires_after_ttl(monkeypatch) -> None:
    recorded: dict[str, tuple[bytes, float]] = {}

    class FakeRedis:
        async def setex(self, key: str, ttl: int, value: bytes) -> None:
            recorded[key] = (value, time.time() + ttl)

        async def get(self, key: str) -> bytes | None:
            entry = recorded.get(key)
            if entry is None:
                return None
            value, expiry = entry
            if time.time() >= expiry:
                return None
            return value

        async def delete(self, key: str) -> None:
            recorded.pop(key, None)

    fake_redis = FakeRedis()
    monkeypatch.setattr(rc, "redis_client", fake_redis)

    asyncio.run(rc.set_device_reauthentication_required("device-reauth"))
    assert asyncio.run(rc.is_device_reauthentication_required("device-reauth")) is True

    key = "device:reauth:device-reauth"
    recorded[key] = (b"1", time.time() - 1)
    assert asyncio.run(rc.is_device_reauthentication_required("device-reauth")) is False
