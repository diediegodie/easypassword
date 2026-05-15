from __future__ import annotations

import asyncio

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
