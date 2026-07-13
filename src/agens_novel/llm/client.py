"""OpenAI-compatible async LLM client.

This client is intentionally minimal: it wraps synchronous ``httpx.Client`` and
exposes ``call_llm`` and ``call_llm_stream`` functions. It supports both
streaming and non-streaming responses, both parsed via the SSE parser in
``llm/sse.py``.

The auth header and base URL are read from env or passed explicitly. The API
key is never logged, and the repository does not ship a built-in key.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from agens_novel.settings import Settings

from .retry import RetryExhausted, is_retryable_status, with_retry
from .sse import extract_delta_text
from .types import LLMResponse, Message, Usage
from .url_security import UnsafeModelBaseUrl, validate_model_base_url_for_request

log = logging.getLogger(__name__)


class LLMError(Exception):
    """Base class for LLM client errors."""


class LLMAuthError(LLMError):
    """401/403 from the upstream API."""


class LLMBadRequest(LLMError):
    """4xx other than auth."""


class InvalidEgressProxyUrl(ValueError):
    """Raised when the explicit outbound proxy URL is malformed."""


def _resolve_config(
    base_url: str | None,
    api_key: str | None,
    model: str | None,
) -> tuple[str, str, str]:
    """Resolve config from explicit args or env.

    Base URL and model keep safe defaults; API key must be supplied by
    explicit arg or ``AGNES_API_KEY``.
    """
    base = base_url or os.environ.get("AGNES_BASE_URL") or Settings().base_url
    key = os.environ.get("AGNES_API_KEY", "") if api_key is None else api_key
    mdl = model or os.environ.get("AGNES_MODEL", Settings().model)
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
    response_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [dict(m) for m in messages],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if response_format:
        payload["response_format"] = response_format
    return payload


def mask_key(key: str) -> str:
    """Return a masked version of an API key for logging."""
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


def _resolve_request_options(
    timeout_seconds: float | None,
    max_retries: int | None,
) -> tuple[float, int]:
    """Resolve request timeout/retries from args or environment."""
    if timeout_seconds is None:
        try:
            timeout_seconds = float(os.environ.get("AGNES_REQUEST_TIMEOUT_SECONDS", "60.0"))
        except ValueError:
            timeout_seconds = 60.0
    if max_retries is None:
        try:
            max_retries = int(os.environ.get("AGNES_MAX_RETRIES", "3"))
        except ValueError:
            max_retries = 3
    return max(1.0, timeout_seconds), max(0, max_retries)


def _resolve_total_timeout(total_timeout_seconds: float | None) -> float:
    if total_timeout_seconds is None:
        try:
            total_timeout_seconds = float(os.environ.get("AGNES_TOTAL_TIMEOUT_SECONDS", "90.0"))
        except ValueError:
            total_timeout_seconds = 90.0
    return max(1.0, total_timeout_seconds)


def validate_egress_proxy_url(raw_url: str) -> str:
    value = str(raw_url or "").strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise InvalidEgressProxyUrl("AGENS_EGRESS_PROXY_URL is invalid.") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise InvalidEgressProxyUrl("AGENS_EGRESS_PROXY_URL must use HTTP or HTTPS.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise InvalidEgressProxyUrl(
            "AGENS_EGRESS_PROXY_URL must not contain credentials or an empty host."
        )
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise InvalidEgressProxyUrl(
            "AGENS_EGRESS_PROXY_URL must not contain a path, query, or fragment."
        )
    hostname = parsed.hostname.rstrip(".").lower()
    if not hostname or "%" in hostname:
        raise InvalidEgressProxyUrl("AGENS_EGRESS_PROXY_URL contains an invalid host.")
    normalized_host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = f"{normalized_host}:{port}" if port is not None else normalized_host
    return urlunsplit((parsed.scheme.lower(), netloc, "", "", ""))


def _http_client_options(timeout_seconds: float) -> dict[str, Any]:
    options: dict[str, Any] = {
        "timeout": timeout_seconds,
        "follow_redirects": False,
        "trust_env": False,
    }
    proxy = validate_egress_proxy_url(os.environ.get("AGENS_EGRESS_PROXY_URL", ""))
    if proxy:
        options["proxy"] = proxy
    return options


async def call_llm(
    messages: list[Message],
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    stream: bool = False,
    timeout_seconds: float | None = None,
    total_timeout_seconds: float | None = None,
    max_retries: int | None = None,
    response_format: dict[str, Any] | None = None,
) -> LLMResponse:
    """Call the OpenAI-compatible /v1/chat/completions endpoint.

    Returns a normalised :class:`LLMResponse`.
    Raises :class:`LLMError` subclasses on transport / HTTP failures.
    """
    base, key, mdl = _resolve_config(base_url, api_key, model)
    base = await _safe_request_base_url(base)
    timeout_seconds, max_retries = _resolve_request_options(timeout_seconds, max_retries)
    total_timeout_seconds = _resolve_total_timeout(total_timeout_seconds)
    log.debug("call_llm: base=%s model=%s key=%s", base, mdl, mask_key(key))
    payload = _build_payload(
        messages,
        model=mdl,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=stream,
        response_format=response_format,
    )
    headers = _headers(key)
    url = f"{base.rstrip('/')}/chat/completions"

    started = time.monotonic()
    if stream:
        return await _call_stream(
            url,
            headers,
            payload,
            timeout_seconds,
            total_timeout_seconds,
            max_retries,
            started,
        )
    return await _call_non_stream(
        url,
        headers,
        payload,
        timeout_seconds,
        total_timeout_seconds,
        max_retries,
        started,
    )


async def call_llm_stream(
    messages: list[Message],
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout_seconds: float | None = None,
    total_timeout_seconds: float | None = None,
    max_retries: int | None = None,
    on_chunk: Callable[[str], None] | None = None,
    response_format: dict[str, Any] | None = None,
) -> LLMResponse:
    """Stream LLM response with per-chunk callback.

    Like ``call_llm`` with ``stream=True``, but additionally invokes
    ``on_chunk(text)`` for each delta text chunk as it arrives.  The
    final accumulated text is still returned in the LLMResponse.
    """
    base, key, mdl = _resolve_config(base_url, api_key, model)
    base = await _safe_request_base_url(base)
    timeout_seconds, max_retries = _resolve_request_options(timeout_seconds, max_retries)
    total_timeout_seconds = _resolve_total_timeout(total_timeout_seconds)
    log.debug("call_llm_stream: base=%s model=%s key=%s", base, mdl, mask_key(key))
    payload = _build_payload(
        messages,
        model=mdl,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        response_format=response_format,
    )
    headers = _headers(key)
    url = f"{base.rstrip('/')}/chat/completions"
    started = time.monotonic()
    return await _call_stream(
        url,
        headers,
        payload,
        timeout_seconds,
        total_timeout_seconds,
        max_retries,
        started,
        on_chunk=on_chunk,
    )


async def _call_non_stream(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
    total_timeout_seconds: float,
    max_retries: int,
    started: float,
) -> LLMResponse:
    async def _do() -> LLMResponse:
        async with httpx.AsyncClient(**_http_client_options(timeout_seconds)) as client:
            resp = await client.post(url, headers=headers, json=payload)
            return _handle_non_stream_response(resp, started)

    return await _execute_with_retry(
        _do,
        max_retries=max_retries,
        total_timeout_seconds=total_timeout_seconds,
        label="llm_call",
    )


async def _call_stream(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
    total_timeout_seconds: float,
    max_retries: int,
    started: float,
    on_chunk: Callable[[str], None] | None = None,
) -> LLMResponse:
    async def _do() -> LLMResponse:
        async with httpx.AsyncClient(**_http_client_options(timeout_seconds)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                return await _handle_stream_response(
                    resp,
                    payload["model"],
                    started,
                    on_chunk,
                )

    return await _execute_with_retry(
        _do,
        max_retries=max_retries,
        total_timeout_seconds=total_timeout_seconds,
        label="llm_stream",
    )


def _handle_non_stream_response(resp: httpx.Response, started: float) -> LLMResponse:
    if resp.status_code == 401 or resp.status_code == 403:
        raise LLMAuthError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    if 300 <= resp.status_code < 400:
        raise LLMBadRequest(f"HTTP {resp.status_code}: upstream redirect refused")
    if is_retryable_status(resp.status_code):
        resp.raise_for_status()
    if resp.status_code >= 400:
        raise LLMBadRequest(f"HTTP {resp.status_code}: {resp.text[:300]}")
    resp.raise_for_status()

    body = resp.json()
    try:
        first = body["choices"][0]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"Malformed response: missing 'choices[0]': {body!r}") from e

    text = first.get("message", {}).get("content") or first.get("text") or ""
    usage = _normalize_usage(body.get("usage"))
    elapsed_ms = int((time.monotonic() - started) * 1000)

    return LLMResponse(
        text=text,
        model=body.get("model", ""),
        usage=usage,
        finish_reason=first.get("finish_reason", "stop"),
        elapsed_ms=elapsed_ms,
        raw=body,
    )


def _normalize_usage(value: Any) -> Usage:
    if not isinstance(value, dict):
        return {}
    return Usage(
        prompt_tokens=_token_count(value.get("prompt_tokens")),
        completion_tokens=_token_count(value.get("completion_tokens")),
        total_tokens=_token_count(value.get("total_tokens")),
    )


def _token_count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


@dataclass
class _StreamState:
    model_name: str
    accumulated: list[str] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Usage = field(default_factory=Usage)

    def consume(self, event: dict[str, Any], on_chunk: Callable[[str], None] | None) -> None:
        text = extract_delta_text(event)
        if text:
            self.accumulated.append(text)
            if on_chunk is not None:
                on_chunk(text)
        if event.get("model"):
            self.model_name = str(event["model"])
        choices = event.get("choices") or []
        if choices and isinstance(choices[0], dict) and "finish_reason" in choices[0]:
            self.finish_reason = str(choices[0]["finish_reason"] or "stop")
        if event.get("usage"):
            self.usage = _normalize_usage(event["usage"])


async def _handle_stream_response(
    resp: httpx.Response,
    default_model: str,
    started: float,
    on_chunk: Callable[[str], None] | None = None,
) -> LLMResponse:
    if resp.status_code == 401 or resp.status_code == 403:
        raise LLMAuthError(f"HTTP {resp.status_code}: {(await _read_response_text(resp))[:300]}")
    if 300 <= resp.status_code < 400:
        raise LLMBadRequest(f"HTTP {resp.status_code}: upstream redirect refused")
    if is_retryable_status(resp.status_code):
        await resp.aread()
        resp.raise_for_status()
    if resp.status_code >= 400:
        raise LLMBadRequest(f"HTTP {resp.status_code}: {(await _read_response_text(resp))[:300]}")
    resp.raise_for_status()

    state = _StreamState(model_name=default_model)
    buffer = ""

    async for raw in resp.aiter_bytes():
        buffer += raw.decode("utf-8", errors="replace")
        *lines, buffer = buffer.split("\n")
        for event in _parse_sse_lines(lines):
            state.consume(event, on_chunk)

    for event in _parse_sse_lines([buffer]):
        state.consume(event, on_chunk)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    return LLMResponse(
        text="".join(state.accumulated),
        model=state.model_name,
        usage=state.usage,
        finish_reason=state.finish_reason,
        elapsed_ms=elapsed_ms,
        raw={"streamed": True},
    )


async def _read_response_text(resp: httpx.Response) -> str:
    try:
        return (await resp.aread()).decode("utf-8", "replace")
    except Exception:
        return resp.text


async def _safe_request_base_url(base_url: str) -> str:
    try:
        return await validate_model_base_url_for_request(base_url)
    except UnsafeModelBaseUrl as exc:
        raise LLMBadRequest(str(exc)) from exc


async def _execute_with_retry(
    operation: Callable[[], Any],
    *,
    max_retries: int,
    total_timeout_seconds: float,
    label: str,
) -> LLMResponse:
    try:
        async with asyncio.timeout(total_timeout_seconds):
            return await with_retry(
                operation,
                max_retries=max_retries,
                label=label,
            )
    except TimeoutError as exc:
        raise LLMError(f"{label}: total timeout exceeded") from exc
    except RetryExhausted as exc:
        raise LLMError(f"{label}: upstream transport unavailable") from exc
    except httpx.HTTPStatusError as exc:
        raise LLMError(f"{label}: upstream HTTP {exc.response.status_code}") from exc


def _parse_sse_lines(lines: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in lines:
        line = line.rstrip("\r").strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events
