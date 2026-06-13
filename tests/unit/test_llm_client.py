"""Tests for LLM client — config priority and base64 key handling."""

from __future__ import annotations

import base64
import os
import pytest

from agens_novel.llm.client import _resolve_config, _DEFAULT_KEY_B64, _DEFAULT_KEY, mask_key


class TestResolveConfig:
    """Test three-level priority: user custom > env var > built-in default."""

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

    def test_env_vars_second_priority(self, monkeypatch):
        monkeypatch.delenv("AGNES_BASE_URL", raising=False)
        monkeypatch.delenv("AGNES_API_KEY", raising=False)
        monkeypatch.delenv("AGNES_MODEL", raising=False)

        base, key, mdl = _resolve_config(None, None, None)
        assert base == "https://apihub.agnes-ai.com/v1"
        assert key == _DEFAULT_KEY
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

    def test_empty_env_uses_default(self, monkeypatch):
        """Empty string env var should fall through to default."""
        monkeypatch.setenv("AGNES_API_KEY", "")
        monkeypatch.delenv("AGNES_BASE_URL", raising=False)
        monkeypatch.delenv("AGNES_MODEL", raising=False)

        base, key, mdl = _resolve_config(None, None, None)
        assert key == _DEFAULT_KEY  # empty string falls through


class TestBuiltinKey:
    """Test base64 encode/decode of built-in key."""

    def test_default_key_decodes_correctly(self):
        decoded = base64.b64decode(_DEFAULT_KEY_B64).decode("utf-8")
        assert decoded == _DEFAULT_KEY

    def test_default_key_is_not_empty(self):
        assert len(_DEFAULT_KEY) > 0

    def test_default_key_b64_is_valid_base64(self):
        # Should not raise
        base64.b64decode(_DEFAULT_KEY_B64)


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
