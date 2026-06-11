"""Exponential backoff retry helper for httpx calls."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

log = logging.getLogger(__name__)

T = TypeVar("T")

# Status codes worth retrying on.
RETRYABLE_HTTP_STATUSES: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})


def is_retryable_status(status_code: int) -> bool:
    return status_code in RETRYABLE_HTTP_STATUSES


class RetryExhausted(Exception):
    """Raised when all retry attempts are exhausted."""


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    initial_backoff: float = 1.0,
    max_backoff: float = 8.0,
    label: str = "llm_call",
) -> T:
    """Run an async callable with exponential backoff + jitter.

    Retries on:
      * httpx.TransportError (network, timeout)
      * HTTP status codes in RETRYABLE_HTTP_STATUSES

    Does NOT retry on 4xx (other than the list above) or on user errors.
    """
    attempt = 0
    while True:
        try:
            return await fn()
        except httpx.TransportError as e:
            if attempt >= max_retries:
                raise RetryExhausted(f"{label}: network error after {attempt} retries: {e}") from e
            delay = _backoff(attempt, initial_backoff, max_backoff)
            log.warning("%s: network error (attempt %d): %s; retrying in %.2fs",
                        label, attempt + 1, e, delay)
            await asyncio.sleep(delay)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if not is_retryable_status(status) or attempt >= max_retries:
                raise
            delay = _backoff(attempt, initial_backoff, max_backoff)
            log.warning("%s: HTTP %d (attempt %d); retrying in %.2fs",
                        label, status, attempt + 1, delay)
            await asyncio.sleep(delay)
        attempt += 1


def _backoff(attempt: int, initial: float, maximum: float) -> float:
    # Exponential with full jitter.
    raw = initial * (2 ** attempt)
    return random.uniform(0, min(maximum, raw))
