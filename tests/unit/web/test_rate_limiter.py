"""Shared and fail-closed rate limiter coverage."""

from __future__ import annotations

import pytest
import redis
from fastapi import HTTPException

from web.backend.security import (
    _REDIS_SLIDING_WINDOW_SCRIPT,
    InMemoryRateLimiter,
    RedisRateLimiter,
    create_rate_limiter,
)


class _SharedRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def eval(self, _script, _num_keys, key, _window_ms, limit, _member):
        count = self.counts.get(key, 0)
        if count >= int(limit):
            return 0
        self.counts[key] = count + 1
        return 1

    def ping(self) -> bool:
        return True


class _UnavailableRedis:
    def eval(self, *_args):
        raise redis.ConnectionError("unavailable")

    def ping(self) -> bool:
        raise redis.ConnectionError("unavailable")


def test_two_redis_limiter_instances_share_one_counter() -> None:
    shared = _SharedRedis()
    first = RedisRateLimiter("redis://unused", client=shared)
    second = RedisRateLimiter("redis://unused", client=shared)

    first.check("turn:client", limit=2, window_seconds=60)
    second.check("turn:client", limit=2, window_seconds=60)

    with pytest.raises(HTTPException) as exc_info:
        first.check("turn:client", limit=2, window_seconds=60)
    assert exc_info.value.status_code == 429


def test_redis_limiter_fails_closed_when_backend_is_unavailable() -> None:
    limiter = RedisRateLimiter("redis://unused", client=_UnavailableRedis())

    with pytest.raises(HTTPException) as exc_info:
        limiter.check("turn:client", limit=2, window_seconds=60)

    assert exc_info.value.status_code == 503
    assert limiter.ping() is False


def test_redis_script_is_atomic_sliding_window() -> None:
    assert "ZREMRANGEBYSCORE" in _REDIS_SLIDING_WINDOW_SCRIPT
    assert "ZCARD" in _REDIS_SLIDING_WINDOW_SCRIPT
    assert "ZADD" in _REDIS_SLIDING_WINDOW_SCRIPT
    assert "PEXPIRE" in _REDIS_SLIDING_WINDOW_SCRIPT


def test_local_factory_defaults_to_memory(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_ENV", "development")
    monkeypatch.delenv("AGENS_RATE_LIMIT_BACKEND", raising=False)

    assert isinstance(create_rate_limiter(), InMemoryRateLimiter)
