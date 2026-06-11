"""Pydantic Settings: env-only configuration with secret redaction.

The Settings class is the single source of truth for runtime configuration.
The API key is loaded from the AGNES_API_KEY env var and masked on repr.
Never log the Settings object directly — call `settings.public_summary()`
instead.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _mask(value: str | None) -> str:
    """Mask a secret value for safe display. Returns '***' if value is empty."""
    if not value:
        return "<unset>"
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}***{value[-4:]}"


class Settings(BaseSettings):
    """Env-driven settings. Loaded lazily, masked on repr."""

    model_config = SettingsConfigDict(
        env_prefix="AGNES_",
        env_file=None,  # Explicitly disable .env loading — env vars only.
        extra="ignore",
        case_sensitive=False,
    )

    # Core API
    api_key: str = Field(default="", description="Loaded from AGNES_API_KEY env var")
    base_url: str = Field(default="https://apihub.agnes-ai.com/v1")
    model: str = Field(default="agnes-2.0-flash")

    # LLM call defaults
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=32000)
    request_timeout_seconds: float = Field(default=60.0, gt=0)

    # Retry
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_initial_backoff_seconds: float = Field(default=1.0, gt=0)
    retry_max_backoff_seconds: float = Field(default=8.0, gt=0)

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
