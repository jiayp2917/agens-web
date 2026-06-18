"""Environment-driven settings with secret redaction.

The Settings class is the single source of truth for runtime configuration.
The API key is loaded from the AGNES_API_KEY env var and masked on repr.
Never log the Settings object directly — call ``settings.public_summary()``
instead.

No external dependencies; safe to use from the web backend and tests.
"""

from __future__ import annotations

import os
from typing import Any


def _mask(value: str | None) -> str:
    """Mask a secret value for safe display. Returns '<unset>' if value is empty."""
    if not value:
        return "<unset>"
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}***{value[-4:]}"


class Settings:
    """Env-driven settings. Loaded from AGNES_* env vars, masked on repr.

    Accepts ``**overrides`` so callers can inject values programmatically
    (e.g. ``Settings(api_key="sk-...")``).
    """

    def __init__(self, **overrides: Any) -> None:
        self.api_key: str = overrides.get(
            "api_key", os.environ.get("AGNES_API_KEY", ""),
        )
        self.base_url: str = overrides.get(
            "base_url", os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1"),
        )
        self.model: str = overrides.get(
            "model", os.environ.get("AGNES_MODEL", "agnes-2.0-flash"),
        )
        self.temperature: float = float(overrides.get(
            "temperature", os.environ.get("AGNES_TEMPERATURE", "0.7"),
        ))
        self.max_tokens: int = int(overrides.get(
            "max_tokens", os.environ.get("AGNES_MAX_TOKENS", "4096"),
        ))
        self.request_timeout_seconds: float = float(overrides.get(
            "request_timeout_seconds", os.environ.get("AGNES_REQUEST_TIMEOUT_SECONDS", "60.0"),
        ))
        self.max_retries: int = int(overrides.get(
            "max_retries", os.environ.get("AGNES_MAX_RETRIES", "3"),
        ))
        self.retry_initial_backoff_seconds: float = float(overrides.get(
            "retry_initial_backoff_seconds", os.environ.get("AGNES_RETRY_INITIAL_BACKOFF_SECONDS", "1.0"),
        ))
        self.retry_max_backoff_seconds: float = float(overrides.get(
            "retry_max_backoff_seconds", os.environ.get("AGNES_RETRY_MAX_BACKOFF_SECONDS", "8.0"),
        ))

    def __repr__(self) -> str:
        """Mask api_key in repr to prevent accidental leak in tracebacks."""
        return (
            f"Settings(api_key={_mask(self.api_key)}, base_url={self.base_url!r}, "
            f"model={self.model!r}, temperature={self.temperature}, "
            f"max_tokens={self.max_tokens})"
        )

    def public_summary(self) -> dict[str, Any]:
        """A log-safe dict — never includes the raw api_key."""
        return {
            "api_key": _mask(self.api_key),
            "base_url": self.base_url,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "request_timeout_seconds": self.request_timeout_seconds,
            "max_retries": self.max_retries,
        }

    def has_api_key(self) -> bool:
        return bool(self.api_key)
