"""OpenAI-compatible async LLM client.

This client is intentionally minimal — it wraps ``httpx.AsyncClient`` and
exposes ``call_llm`` and ``call_llm_stream`` functions. It supports both
streaming and non-streaming responses, both parsed via the SSE parser in
``llm/sse.py``.

The auth header and base URL are read from env (via ``Settings``) or passed
explicitly. The api key is never logged.

Priority: user custom (settings.json) > env var (AGNES_API_KEY) > built-in default.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any, Callable

import httpx

from .retry import with_retry
from .sse import extract_delta_text, iter_sse_events
from .types import LLMResponse, Message, Usage

log = logging.getLogger(__name__)


class LLMError(Exception):
    """Base class for LLM client errors."""


class LLMAuthError(LLMError):
    """401/403 from the upstream API."""


class LLMBadRequest(LLMError):
    """4xx other than auth."""


# ─────────────────────────────────────────────────────────────────────────────
# Built-in default API key (base64 obfuscated)
# ─────────────────────────────────────────────────────────────────────────────

# Production key (replaced at packaging time).
_DEFAULT_KEY_B64 = "c2stdkN2QlNJOGdsbGtyZTJrZktSR0UyZ25KU1BmYlJmSnVNY21CTnFITldMNGhZVzVY"
_DEFAULT_KEY = base64.b64decode(_DEFAULT_KEY_B64).decode("utf-8")


def _resolve_config(
    base_url: str | None,
    api_key: str | None,
    model: str | None,
) -> tuple[str, str, str]:
    """Resolve config from explicit args, env, or built-in default.

    Priority: user custom (explicit arg) > env var > built-in default.
    """
    base = base_url or os.environ.get("AGNES_BASE_URL") or "https://apihub.agnes-ai.com/v1"
    key = api_key or os.environ.get("AGNES_API_KEY", "") or _DEFAULT_KEY
    mdl = model or os.environ.get("AGNES_MODEL", "agnes-2.0-flash")
    return base, key, mdl


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _build_payload(
    messages: list[Message],
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    stream: bool,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [dict(m) for m in messages],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }


def mask_key(key: str) -> str:
    """Return a masked version of an API key for logging."""
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


async def call_llm(
    messages: list[Message],
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    stream: bool = False,
    timeout_seconds: float = 60.0,
    max_retries: int = 3,
) -> LLMResponse:
    """Call the OpenAI-compatible /v1/chat/completions endpoint.

    Returns a normalised :class:`LLMResponse`.
    Raises :class:`LLMError` subclasses on transport / HTTP failures.
    """
    base, key, mdl = _resolve_config(base_url, api_key, model)
    log.debug("call_llm: base=%s model=%s key=%s", base, mdl, mask_key(key))
    payload = _build_payload(
        messages,
        model=mdl,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=stream,
    )
    headers = _headers(key)
    url = f"{base.rstrip('/')}/chat/completions"

    started = time.monotonic()
    if stream:
        return await _call_stream(url, headers, payload, timeout_seconds, max_retries, started)
    return await _call_non_stream(url, headers, payload, timeout_seconds, max_retries, started)


async def call_llm_stream(
    messages: list[Message],
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout_seconds: float = 60.0,
    max_retries: int = 3,
    on_chunk: Callable[[str], None] | None = None,
) -> LLMResponse:
    """Stream LLM response with per-chunk callback.

    Like ``call_llm`` with ``stream=True``, but additionally invokes
    ``on_chunk(text)`` for each delta text chunk as it arrives.  The
    final accumulated text is still returned in the LLMResponse.
    """
    base, key, mdl = _resolve_config(base_url, api_key, model)
    log.debug("call_llm_stream: base=%s model=%s key=%s", base, mdl, mask_key(key))
    payload = _build_payload(
        messages,
        model=mdl,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    headers = _headers(key)
    url = f"{base.rstrip('/')}/chat/completions"
    started = time.monotonic()

    async def _do() -> LLMResponse:
        accumulated: list[str] = []
        model_name = mdl
        finish_reason = "stop"
        usage: Usage = {}
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code == 401 or resp.status_code == 403:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise LLMAuthError(f"HTTP {resp.status_code}: {body[:300]}")
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise LLMBadRequest(f"HTTP {resp.status_code}: {body[:300]}")
                resp.raise_for_status()

                async for event in iter_sse_events(resp.aiter_bytes()):
                    text = extract_delta_text(event)
                    if text:
                        accumulated.append(text)
                        if on_chunk is not None:
                            on_chunk(text)
                    if "model" in event:
                        model_name = event["model"]
                    choices = event.get("choices") or []
                    if choices and "finish_reason" in choices[0]:
                        finish_reason = choices[0]["finish_reason"] or "stop"
                    if "usage" in event and event["usage"]:
                        usage = event["usage"]  # type: ignore[assignment]

        elapsed_ms = int((time.monotonic() - started) * 1000)
        return LLMResponse(
            text="".join(accumulated),
            model=model_name,
            usage=usage,
            finish_reason=finish_reason,
            elapsed_ms=elapsed_ms,
            raw={"streamed": True},
        )

    return await with_retry(_do, max_retries=max_retries, label="llm_stream")


async def _call_non_stream(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
    max_retries: int,
    started: float,
) -> LLMResponse:
    async def _do() -> LLMResponse:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(url, headers=headers, json=payload)
            return _handle_non_stream_response(resp, started)

    return await with_retry(_do, max_retries=max_retries, label="llm_call")


async def _call_stream(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
    max_retries: int,
    started: float,
) -> LLMResponse:
    async def _do() -> LLMResponse:
        accumulated: list[str] = []
        model_name = payload["model"]
        finish_reason = "stop"
        usage: Usage = {}
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code == 401 or resp.status_code == 403:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise LLMAuthError(f"HTTP {resp.status_code}: {body[:300]}")
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise LLMBadRequest(f"HTTP {resp.status_code}: {body[:300]}")
                resp.raise_for_status()

                async for event in iter_sse_events(resp.aiter_bytes()):
                    text = extract_delta_text(event)
                    if text:
                        accumulated.append(text)
                    if "model" in event:
                        model_name = event["model"]
                    choices = event.get("choices") or []
                    if choices and "finish_reason" in choices[0]:
                        finish_reason = choices[0]["finish_reason"] or "stop"
                    if "usage" in event and event["usage"]:
                        usage = event["usage"]  # type: ignore[assignment]

        elapsed_ms = int((time.monotonic() - started) * 1000)
        return LLMResponse(
            text="".join(accumulated),
            model=model_name,
            usage=usage,
            finish_reason=finish_reason,
            elapsed_ms=elapsed_ms,
            raw={"streamed": True},
        )

    return await with_retry(_do, max_retries=max_retries, label="llm_stream")


def _handle_non_stream_response(resp: httpx.Response, started: float) -> LLMResponse:
    if resp.status_code == 401 or resp.status_code == 403:
        raise LLMAuthError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    if resp.status_code >= 400:
        raise LLMBadRequest(f"HTTP {resp.status_code}: {resp.text[:300]}")
    resp.raise_for_status()

    body = resp.json()
    try:
        first = body["choices"][0]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"Malformed response: missing 'choices[0]': {body!r}") from e

    text = first.get("message", {}).get("content") or first.get("text") or ""
    usage = body.get("usage") or {}
    elapsed_ms = int((time.monotonic() - started) * 1000)

    return LLMResponse(
        text=text,
        model=body.get("model", ""),
        usage=usage,
        finish_reason=first.get("finish_reason", "stop"),
        elapsed_ms=elapsed_ms,
        raw=body,
    )
