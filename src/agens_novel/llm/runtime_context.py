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


@dataclass(frozen=True)
class RuntimeModelConfig:
    provider: str
    model: str
    base_url: str
    api_key: str
    source: str = "env"
    key_error: str = ""

    @property
    def api_key_set(self) -> bool:
        return bool(self.api_key)


_CURRENT_CONFIG: ContextVar[RuntimeModelConfig | None] = ContextVar(
    "agens_runtime_model_config", default=None
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


def runtime_api_key() -> str:
    config = current_model_runtime()
    return config.api_key if config is not None else ""
