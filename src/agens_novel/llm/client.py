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

import httpx

from agens_novel.settings import Settings

from .retry import RetryExhausted, is_retryable_status, with_retry
from .sse import extract_delta_text
from .types import LLMResponse, Message, Usage
from .url_security import UnsafeModelBaseUrl, validate_model_base_url_for_request

log = logging.getLogger(__name__)


class LLMError(Exception):
    """Base class for LLM client errors."""

    error_code = "llm_error"
    usage: Usage = {}
    response_diagnostics: dict[str, object] = {}


class LLMCompletionError(LLMError):
    """A 2xx completion that cannot safely be used as model content."""

    def __init__(
        self,
        error_code: str,
        *,
        usage: Usage,
        response_diagnostics: dict[str, object],
        elapsed_ms: int,
    ) -> None:
        self.error_code = error_code
        self.usage = usage
        self.response_diagnostics = response_diagnostics
        self.elapsed_ms = max(0, int(elapsed_ms))
        super().__init__(f"llm_call: {error_code}")


class LLMAuthError(LLMError):
    """401/403 from the upstream API."""


class LLMBadRequest(LLMError):
    """4xx other than auth."""


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
    """Return a presence marker without retaining any key characters."""
    return "<set>" if key else "<unset>"


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


def _http_client_options(timeout_seconds: float) -> dict[str, Any]:
    return {
        "timeout": timeout_seconds,
        "follow_redirects": False,
        "trust_env": True,
    }


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
    log.debug("call_llm: model=%s key=%s", mdl, mask_key(key))
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
    log.debug("call_llm_stream: model=%s key=%s", mdl, mask_key(key))
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
        return await _non_stream_attempt(url, headers, payload, timeout_seconds, started)

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
        return await _stream_attempt(
            url, headers, payload, timeout_seconds, started, on_chunk
        )

    return await _execute_with_retry(
        _do,
        max_retries=max_retries,
        total_timeout_seconds=total_timeout_seconds,
        label="llm_stream",
    )


async def _non_stream_attempt(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
    started: float,
) -> LLMResponse:
    async with httpx.AsyncClient(**_http_client_options(timeout_seconds)) as client:
        response = await client.post(url, headers=headers, json=payload)
        return _handle_non_stream_response(response, started)


async def _stream_attempt(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
    started: float,
    on_chunk: Callable[[str], None] | None,
) -> LLMResponse:
    async with httpx.AsyncClient(**_http_client_options(timeout_seconds)) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as response:
            return await _handle_stream_response(response, payload["model"], started, on_chunk)


def _handle_non_stream_response(resp: httpx.Response, started: float) -> LLMResponse:
    if resp.status_code == 401 or resp.status_code == 403:
        raise _with_error_code(
            LLMAuthError(f"HTTP {resp.status_code}: upstream authentication failed"),
            _http_error_code(resp.status_code),
        )
    if 300 <= resp.status_code < 400:
        raise _with_error_code(
            LLMBadRequest(f"HTTP {resp.status_code}: upstream redirect refused"),
            "http_redirect",
        )
    if is_retryable_status(resp.status_code):
        resp.raise_for_status()
    if resp.status_code >= 400:
        raise _with_error_code(
            LLMBadRequest(f"HTTP {resp.status_code}: upstream request rejected"),
            _http_error_code(resp.status_code),
        )
    resp.raise_for_status()

    body = resp.json()
    try:
        choices = body["choices"]
        first = choices[0]
    except (KeyError, IndexError, TypeError) as e:
        raise _with_error_code(
            LLMError("llm_call: malformed_response_missing_choices"),
            "malformed_response",
        ) from e

    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    text_value = first.get("text") if isinstance(first, dict) else None
    text = content if isinstance(content, str) else text_value if isinstance(text_value, str) else ""
    usage = _normalize_usage(body.get("usage"))
    diagnostics = _response_diagnostics(
        choices=choices,
        first=first,
        content=content,
        text_field=text_value,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if not text:
        error_code = "refusal_completion" if diagnostics["refusal_present"] else "empty_completion"
        raise LLMCompletionError(
            error_code,
            usage=usage,
            response_diagnostics=diagnostics,
            elapsed_ms=elapsed_ms,
        )

    return LLMResponse(
        text=text,
        model=body.get("model", ""),
        usage=usage,
        finish_reason=first.get("finish_reason", "stop"),
        elapsed_ms=elapsed_ms,
        raw=body,
        response_diagnostics=diagnostics,
    )


def _response_diagnostics(
    *,
    choices: Any,
    first: Any,
    content: Any,
    text_field: Any,
) -> dict[str, object]:
    """Return response-shape facts without retaining any provider text."""
    message = first.get("message") if isinstance(first, dict) else None
    finish_reason = first.get("finish_reason") if isinstance(first, dict) else None
    normalized_finish_reason = str(finish_reason or "missing").strip().lower()
    if normalized_finish_reason not in {
        "stop",
        "length",
        "content_filter",
        "tool_calls",
        "function_call",
        "refusal",
        "missing",
    }:
        normalized_finish_reason = "other"
    refusal = message.get("refusal") if isinstance(message, dict) else None
    reasoning = message.get("reasoning_content") if isinstance(message, dict) else None
    resolved_text = content if isinstance(content, str) else text_field if isinstance(text_field, str) else ""
    return {
        "finish_reason": normalized_finish_reason,
        "choices_present": isinstance(choices, list) and bool(choices),
        "message_present": isinstance(message, dict),
        "content_present": bool(resolved_text),
        "content_length": len(resolved_text),
        "reasoning_content_present": bool(reasoning),
        "refusal_present": bool(refusal),
        "content_field_present": content is not None,
        "text_field_present": text_field is not None,
    }


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
        raise _with_error_code(
            LLMAuthError(f"HTTP {resp.status_code}: {(await _read_response_text(resp))[:300]}"),
            _http_error_code(resp.status_code),
        )
    if 300 <= resp.status_code < 400:
        raise _with_error_code(
            LLMBadRequest(f"HTTP {resp.status_code}: upstream redirect refused"),
            "http_redirect",
        )
    if is_retryable_status(resp.status_code):
        await resp.aread()
        resp.raise_for_status()
    if resp.status_code >= 400:
        raise _with_error_code(
            LLMBadRequest(f"HTTP {resp.status_code}: {(await _read_response_text(resp))[:300]}"),
            _http_error_code(resp.status_code),
        )
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
        raise _with_error_code(LLMBadRequest(str(exc)), "unsafe_base_url") from exc


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
        raise _with_error_code(
            LLMError(f"{label}: total timeout exceeded"),
            "timeout",
            response_diagnostics={"transport_error_category": "total_timeout"},
        ) from exc
    except RetryExhausted as exc:
        raise _with_error_code(
            LLMError(f"{label}: upstream transport unavailable"),
            "transport_unavailable",
            response_diagnostics={
                "transport_error_category": _transport_error_category(exc.__cause__)
            },
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise _with_error_code(
            LLMError(f"{label}: upstream HTTP {exc.response.status_code}"),
            _http_error_code(exc.response.status_code),
        ) from exc


def _with_error_code(
    error: LLMError,
    code: str,
    *,
    response_diagnostics: dict[str, object] | None = None,
) -> LLMError:
    error.error_code = code
    if response_diagnostics is not None:
        error.response_diagnostics = dict(response_diagnostics)
    return error


def _http_error_code(status_code: int) -> str:
    if status_code in {400, 401, 403, 404, 408, 413, 422, 425, 429}:
        return f"http_{status_code}"
    if 500 <= status_code <= 599:
        return "http_5xx"
    return "http_other"


def _transport_error_category(error: BaseException | None) -> str:
    """Return a stable, non-sensitive category for a failed HTTP transport."""
    if isinstance(error, httpx.ConnectTimeout):
        return "connect_timeout"
    if isinstance(error, httpx.ReadTimeout):
        return "read_timeout"
    if isinstance(error, httpx.WriteTimeout):
        return "write_timeout"
    if isinstance(error, httpx.PoolTimeout):
        return "pool_timeout"
    if isinstance(error, httpx.ConnectError):
        return "connect_error"
    if isinstance(error, httpx.ProtocolError):
        return "protocol_error"
    if isinstance(error, httpx.TransportError):
        return "transport_error"
    return "unknown"


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
