"""Environment-driven settings with secret redaction.

The Settings class is the single source of truth for runtime configuration.
The API key is loaded from the AGNES_API_KEY env var and masked on repr.
Never log the Settings object directly — call ``settings.public_summary()``
instead.

Uses pydantic-settings for env-var loading.
"""

from __future__ import annotations

from typing import Any

from pydantic_settings import BaseSettings

from agens_novel.utils.secrets import mask as _mask


class Settings(BaseSettings):
    """Env-driven settings. Loaded from AGNES_* env vars, masked on repr.

    Accepts keyword overrides so callers can inject values programmatically
    (e.g. ``Settings(api_key="sk-...")``).
    """

    model_config = {"env_prefix": "AGNES_"}

    api_key: str = ""
    base_url: str = "https://apihub.agnes-ai.com/v1"
    model: str = "agnes-2.0-flash"
    temperature: float = 0.7
    max_tokens: int = 4096
    request_timeout_seconds: float = 60.0
    total_timeout_seconds: float = 90.0
    max_retries: int = 3
    retry_initial_backoff_seconds: float = 1.0
    retry_max_backoff_seconds: float = 8.0

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
            "total_timeout_seconds": self.total_timeout_seconds,
            "max_retries": self.max_retries,
        }

    def has_api_key(self) -> bool:
        return bool(self.api_key)
