"""Non-serializable per-invocation model credentials.

Agent graph state is checkpointed and may be inspected by diagnostics.  API
keys must therefore stay outside that state while a single model invocation is
in flight.  ``ContextVar`` keeps the value local to the current synchronous
runner / async graph chain and naturally isolates concurrent requests.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class RuntimeModelConfig:
    provider: str
    model: str
    base_url: str
    api_key: str
    source: str = "env"
    key_error: str = ""
    provider_transport: str = ""

    @property
    def api_key_set(self) -> bool:
        return bool(self.api_key)

    def public_metadata(self) -> dict[str, str | bool]:
        """Return runtime facts safe to retain on a long-lived engine."""
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_set": self.api_key_set,
            "source": self.source,
            "key_error": self.key_error,
            "provider_transport": self.provider_transport,
        }


_CURRENT_CONFIG: ContextVar[RuntimeModelConfig | None] = ContextVar(
    "agens_runtime_model_config", default=None
)


class ModelCallObserver(Protocol):
    """Observe safe request metadata without receiving prompts, URLs, or keys."""

    def before_request(self, *, agent: str, transport: str, stream: bool) -> Any: ...

    def after_request(
        self,
        ticket: Any,
        *,
        elapsed_ms: int,
        usage: dict[str, int],
        success: bool,
        error_code: str = "",
        response_diagnostics: dict[str, object] | None = None,
    ) -> None: ...


_CURRENT_CALL_CONTEXT: ContextVar[tuple[str, ModelCallObserver] | None] = ContextVar(
    "agens_model_call_observer", default=None
)


@contextmanager
def model_runtime(config: RuntimeModelConfig) -> Iterator[None]:
    """Install one private model config for the duration of an agent graph."""
    token: Token[RuntimeModelConfig | None] = _CURRENT_CONFIG.set(config)
    try:
        yield
    finally:
        _CURRENT_CONFIG.reset(token)


def current_model_runtime() -> RuntimeModelConfig | None:
    """Return the active invocation config without exposing it to graph state."""
    return _CURRENT_CONFIG.get()


@contextmanager
def model_call_observer(agent: str, observer: ModelCallObserver | None) -> Iterator[None]:
    """Expose one non-secret observer for the duration of an Agent graph."""
    if observer is None:
        yield
        return
    token = _CURRENT_CALL_CONTEXT.set((agent, observer))
    try:
        yield
    finally:
        _CURRENT_CALL_CONTEXT.reset(token)


def current_model_call_observer() -> tuple[str, ModelCallObserver] | None:
    """Return the active observer context, if local evaluation installed one."""
    return _CURRENT_CALL_CONTEXT.get()


def runtime_api_key() -> str:
    config = current_model_runtime()
    return config.api_key if config is not None else ""
