from __future__ import annotations

import asyncio

import pytest

from app.core.metrics import (
    replay_cache_evictions_total,
    replay_cache_hit_rate,
    replay_cache_hits_total,
    replay_cache_misses_total,
    replay_cache_size,
)
from app.infra import redis_client as rc
from app.infra.redis_keys import REPLAY_CACHE_KEY


class _FakeRedis:
    """Minimal async fake of ``redis.asyncio.Redis``."""

    def __init__(self) -> None:
        self.set_calls: list[dict] = []
        self.dbsize_calls: int = 0
        self.incr_calls: list[str] = []
        self._dbsize_return: int = 0
        self._set_return: object = True
        self._stored: dict[str, int] = {}

    async def set(
        self, key: str, value: int, *, nx: bool = False, ex: int | None = None
    ) -> int | None:
        self.set_calls.append({"key": key, "value": value, "nx": nx, "ex": ex})
        if nx:
            if key in self._stored:
                self._set_return = None
                return None
            self._stored[key] = value
            self._set_return = True
            return True
        self._stored[key] = value
        self._set_return = True
        return True

    async def dbsize(self) -> int:
        self.dbsize_calls += 1
        return self._dbsize_return

    async def incr(self, key: str) -> int:
        self.incr_calls.append(key)
        self._stored[key] = int(self._stored.get(key, 0)) + 1
        return int(self._stored[key])

    async def get(self, key: str) -> object:
        return self._stored.get(key)

    def set_dbsize_return(self, value: int) -> None:
        self._dbsize_return = value


def _reset_counters() -> None:
    """Reset Prometheus counters/gauges between tests."""
    for metric in (
        replay_cache_hits_total,
        replay_cache_misses_total,
        replay_cache_evictions_total,
    ):
        metric._value.set(0)  # type: ignore[attr-defined]
    replay_cache_size.set(0)
    replay_cache_hit_rate._sum.set(0)  # type: ignore[attr-defined]
    replay_cache_hit_rate._buckets.clear()  # type: ignore[attr-defined]
    for _ in range(len(replay_cache_hit_rate._buckets) + 1):  # type: ignore[attr-defined]
        replay_cache_hit_rate._buckets.append(0)  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _reset_metrics():
    _reset_counters()
    yield
    _reset_counters()


@pytest.mark.unit
def test_add_replay_blob_miss_returns_true_and_increments(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(rc, "redis_client", fake)

    result = asyncio.run(rc.add_replay_blob("user-1", "hash-aaa", ttl=300))

    assert result is True
    assert len(fake.set_calls) == 1
    call = fake.set_calls[0]
    assert call["key"] == REPLAY_CACHE_KEY.format(
        user_id="user-1", blob_hash="hash-aaa"
    )
    assert call["nx"] is True
    assert call["ex"] == 300
    assert replay_cache_misses_total._value.get() == 1  # type: ignore[attr-defined]
    assert replay_cache_hits_total._value.get() == 0  # type: ignore[attr-defined]


@pytest.mark.unit
def test_add_replay_blob_hit_returns_false_and_increments(monkeypatch) -> None:
    fake = _FakeRedis()
    fake._stored[REPLAY_CACHE_KEY.format(user_id="user-2", blob_hash="hash-bbb")] = 1
    monkeypatch.setattr(rc, "redis_client", fake)

    result = asyncio.run(rc.add_replay_blob("user-2", "hash-bbb", ttl=300))

    assert result is False
    assert len(fake.set_calls) == 1
    assert fake.set_calls[0]["nx"] is True
    assert replay_cache_hits_total._value.get() == 1  # type: ignore[attr-defined]
    assert replay_cache_misses_total._value.get() == 0  # type: ignore[attr-defined]


@pytest.mark.unit
def test_add_replay_blob_updates_cache_size_gauge_on_miss(monkeypatch) -> None:
    fake = _FakeRedis()
    fake.set_dbsize_return(42)
    monkeypatch.setattr(rc, "redis_client", fake)

    asyncio.run(rc.add_replay_blob("user-3", "hash-ccc", ttl=60))

    assert fake.dbsize_calls == 1
    assert replay_cache_size._value.get() == 42  # type: ignore[attr-defined]


@pytest.mark.unit
def test_add_replay_blob_hit_does_not_update_size_gauge(monkeypatch) -> None:
    """On a cache hit the size gauge must not be touched (no new key)."""
    fake = _FakeRedis()
    fake._stored[REPLAY_CACHE_KEY.format(user_id="u", blob_hash="h")] = 1
    fake.set_dbsize_return(99)
    monkeypatch.setattr(rc, "redis_client", fake)

    asyncio.run(rc.add_replay_blob("u", "h", ttl=10))

    assert fake.dbsize_calls == 0
    assert replay_cache_size._value.get() == 0  # type: ignore[attr-defined]


@pytest.mark.unit
def test_track_replay_cache_eviction_increments_counter(monkeypatch) -> None:
    fake = _FakeRedis()
    fake.set_dbsize_return(7)
    monkeypatch.setattr(rc, "redis_client", fake)

    asyncio.run(rc.track_replay_cache_eviction())

    assert replay_cache_evictions_total._value.get() == 1  # type: ignore[attr-defined]
    assert fake.dbsize_calls == 1
    assert replay_cache_size._value.get() == 7  # type: ignore[attr-defined]


@pytest.mark.unit
def test_track_replay_cache_eviction_multiple(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(rc, "redis_client", fake)

    for _ in range(5):
        asyncio.run(rc.track_replay_cache_eviction())

    assert replay_cache_evictions_total._value.get() == 5  # type: ignore[attr-defined]


@pytest.mark.unit
def test_increment_replay_cache_total_ops_calls_incr(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(rc, "redis_client", fake)

    asyncio.run(rc.increment_replay_cache_total_ops())

    assert fake.incr_calls == ["replay_cache_total_ops"]


@pytest.mark.unit
def test_increment_replay_cache_total_ops_accumulates(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(rc, "redis_client", fake)

    asyncio.run(rc.increment_replay_cache_total_ops())
    asyncio.run(rc.increment_replay_cache_total_ops())
    asyncio.run(rc.increment_replay_cache_total_ops())

    assert fake.incr_calls == ["replay_cache_total_ops"] * 3
    assert fake._stored["replay_cache_total_ops"] == 3


@pytest.mark.unit
def test_miss_then_hit_sequence(monkeypatch) -> None:
    """Simulate the realistic flow: first write is a miss, replay is a hit."""
    fake = _FakeRedis()
    monkeypatch.setattr(rc, "redis_client", fake)

    first = asyncio.run(rc.add_replay_blob("user-seq", "hash-seq", ttl=300))
    second = asyncio.run(rc.add_replay_blob("user-seq", "hash-seq", ttl=300))

    assert first is True
    assert second is False
    assert replay_cache_misses_total._value.get() == 1  # type: ignore[attr-defined]
    assert replay_cache_hits_total._value.get() == 1  # type: ignore[attr-defined]
