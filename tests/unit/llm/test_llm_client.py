"""Tests for LLM client config priority and key masking."""

from __future__ import annotations

import time

import httpx
import pytest

from agens_novel.llm.client import (
    LLMBadRequest,
    _execute_with_retry,
    _handle_non_stream_response,
    _resolve_config,
    _resolve_request_options,
    _resolve_total_timeout,
    mask_key,
)
from agens_novel.llm.types import LLMResponse


class TestResolveConfig:
    """Test config priority: explicit args > env var > non-secret defaults."""

    def test_explicit_args_highest_priority(self, monkeypatch):
        monkeypatch.setenv("AGNES_BASE_URL", "https://env-url.com/v1")
        monkeypatch.setenv("AGNES_API_KEY", "sk-env-key")
        monkeypatch.setenv("AGNES_MODEL", "env-model")

        base, key, mdl = _resolve_config(
            base_url="https://custom-url.com/v1",
            api_key="sk-custom-key",
            model="custom-model",
        )
        assert base == "https://custom-url.com/v1"
        assert key == "sk-custom-key"
        assert mdl == "custom-model"

    def test_defaults_without_api_key(self, monkeypatch):
        monkeypatch.delenv("AGNES_BASE_URL", raising=False)
        monkeypatch.delenv("AGNES_API_KEY", raising=False)
        monkeypatch.delenv("AGNES_MODEL", raising=False)

        base, key, mdl = _resolve_config(None, None, None)
        assert base == "https://apihub.agnes-ai.com/v1"
        assert key == ""
        assert mdl == "agnes-2.0-flash"

    def test_env_vars_override_defaults(self, monkeypatch):
        monkeypatch.setenv("AGNES_BASE_URL", "https://my-url.com/v1")
        monkeypatch.setenv("AGNES_API_KEY", "sk-my-key")
        monkeypatch.setenv("AGNES_MODEL", "my-model")

        base, key, mdl = _resolve_config(None, None, None)
        assert base == "https://my-url.com/v1"
        assert key == "sk-my-key"
        assert mdl == "my-model"

    def test_partial_env_override(self, monkeypatch):
        monkeypatch.delenv("AGNES_BASE_URL", raising=False)
        monkeypatch.setenv("AGNES_API_KEY", "sk-partial-key")
        monkeypatch.delenv("AGNES_MODEL", raising=False)

        base, key, mdl = _resolve_config(None, None, None)
        assert base == "https://apihub.agnes-ai.com/v1"  # default
        assert key == "sk-partial-key"  # env
        assert mdl == "agnes-2.0-flash"  # default

    def test_empty_env_keeps_key_empty(self, monkeypatch):
        """Empty API key env var stays empty; no built-in key is used."""
        monkeypatch.setenv("AGNES_API_KEY", "")
        monkeypatch.delenv("AGNES_BASE_URL", raising=False)
        monkeypatch.delenv("AGNES_MODEL", raising=False)

        base, key, mdl = _resolve_config(None, None, None)
        assert base == "https://apihub.agnes-ai.com/v1"
        assert key == ""
        assert mdl == "agnes-2.0-flash"


class TestMaskKey:
    """Test API key masking for logging."""

    def test_short_key(self):
        assert mask_key("sk") == "****"

    def test_normal_key(self):
        masked = mask_key("sk-1234567890abcdef")
        assert masked.startswith("sk-1")
        assert masked.endswith("cdef")
        assert "****" in masked

    def test_exact_8_chars(self):
        # mask_key returns "****" for keys with length <= 8
        masked = mask_key("12345678")
        assert masked == "****"

    def test_9_chars_key(self):
        masked = mask_key("123456789")
        assert masked == "1234****6789"

    def test_empty_key(self):
        assert mask_key("") == "****"


class TestResolveRequestOptions:
    def test_env_timeout_and_retries(self, monkeypatch):
        monkeypatch.setenv("AGNES_REQUEST_TIMEOUT_SECONDS", "12")
        monkeypatch.setenv("AGNES_MAX_RETRIES", "0")

        timeout, retries = _resolve_request_options(None, None)

        assert timeout == 12.0
        assert retries == 0

    def test_explicit_options_override_env(self, monkeypatch):
        monkeypatch.setenv("AGNES_REQUEST_TIMEOUT_SECONDS", "12")
        monkeypatch.setenv("AGNES_MAX_RETRIES", "0")

        timeout, retries = _resolve_request_options(30.0, 2)

        assert timeout == 30.0
        assert retries == 2

    def test_total_timeout_uses_environment(self, monkeypatch):
        monkeypatch.setenv("AGNES_TOTAL_TIMEOUT_SECONDS", "17")
        assert _resolve_total_timeout(None) == 17.0


def test_retryable_response_is_not_collapsed_to_bad_request() -> None:
    response = httpx.Response(
        429,
        request=httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions"),
    )

    with pytest.raises(httpx.HTTPStatusError):
        _handle_non_stream_response(response, time.monotonic())


def test_non_retryable_400_remains_bad_request() -> None:
    response = httpx.Response(
        400,
        text="invalid",
        request=httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions"),
    )

    with pytest.raises(LLMBadRequest):
        _handle_non_stream_response(response, time.monotonic())


def test_redirect_response_is_rejected_without_following_location() -> None:
    response = httpx.Response(
        307,
        headers={"location": "http://127.0.0.1/internal"},
        json={"choices": [{"message": {"content": "must not be accepted"}}]},
        request=httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions"),
    )

    with pytest.raises(LLMBadRequest, match="redirect refused"):
        _handle_non_stream_response(response, time.monotonic())


@pytest.mark.asyncio
async def test_total_timeout_cancels_retry_operation() -> None:
    async def never_finishes() -> LLMResponse:
        import asyncio

        await asyncio.sleep(5)
        raise AssertionError("unreachable")

    with pytest.raises(Exception, match="total timeout exceeded"):
        await _execute_with_retry(
            never_finishes,
            max_retries=0,
            total_timeout_seconds=0.01,
            label="test_call",
        )
