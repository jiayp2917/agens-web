"""Settings: env-only, repr-masked."""

from __future__ import annotations

import pytest

from agens_novel.settings import Settings, _mask


def test_mask_short() -> None:
    assert _mask(None) == "<unset>"
    assert _mask("") == "<unset>"
    assert _mask("abc") == "***"
    assert _mask("12345678") == "***"


def test_mask_long() -> None:
    masked = _mask("sk-abcdefghijklmnop")
    assert masked.startswith("sk-")
    assert masked.endswith("mnop")
    assert "***" in masked
    # The middle portion of the secret must NOT appear in the masked form.
    assert "cdefghijkl" not in masked


def test_settings_repr_hides_key(set_api_key: str) -> None:
    s = Settings(api_key=set_api_key)
    text = repr(s)
    assert set_api_key not in text, f"api_key leaked in repr: {text}"
    assert "***" in text


def test_settings_public_summary_hides_key(set_api_key: str) -> None:
    s = Settings(api_key=set_api_key)
    summary = s.public_summary()
    assert summary["api_key"] != set_api_key
    assert "***" in summary["api_key"]


def test_settings_defaults_when_unset(clean_settings) -> None:
    s = Settings()
    assert s.base_url == "https://apihub.agnes-ai.com/v1"
    assert s.model == "agnes-2.0-flash"
    assert s.temperature == 0.7
    assert not s.has_api_key()
