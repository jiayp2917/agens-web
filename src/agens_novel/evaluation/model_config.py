"""Private, read-only model configuration for local evaluation runs."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..artifacts.sink import ArtifactPolicyError, ensure_evaluation_sink_ready
from ..llm.runtime_context import ModelCallObserver, RuntimeModelConfig
from ..settings import Settings

if TYPE_CHECKING:
    from web.backend.service import WebRunner

_KEY_ENV_BY_PROVIDER = {
    "agens": "AGNES_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}
_TRANSPORTS = {"json_schema", "json_object", "legacy_tags"}
_DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-flash"
_DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"


@dataclass(frozen=True)
class EvaluationModelConfig:
    """Non-secret evaluation settings loaded from the current process only."""

    provider: str
    model: str
    base_url: str
    key_environment: str
    provider_transport: str = ""

    @classmethod
    def from_environment(cls) -> EvaluationModelConfig:
        """Load an evaluation provider without copying its key into config."""
        ensure_evaluation_sink_ready()
        provider = os.environ.get("AGENS_EVALUATION_PROVIDER", "").strip()
        default_model, default_base_url = _provider_defaults(provider)
        model = os.environ.get("AGENS_EVALUATION_MODEL", "").strip() or default_model
        base_url = os.environ.get("AGENS_EVALUATION_BASE_URL", "").strip() or default_base_url
        provider_transport = os.environ.get("AGENS_EVALUATION_TRANSPORT", "").strip().lower()
        key_environment = _KEY_ENV_BY_PROVIDER.get(provider.lower())
        if not provider or not model or not base_url or not key_environment:
            raise ArtifactPolicyError("evaluation provider, model, and base URL must be configured")
        if provider_transport and provider_transport not in _TRANSPORTS:
            raise ArtifactPolicyError("evaluation transport is unsupported")
        return cls(
            provider=provider,
            model=model,
            base_url=base_url,
            key_environment=key_environment,
            provider_transport=provider_transport,
        )

    def runtime_config(self) -> RuntimeModelConfig:
        """Read a key only at the boundary that starts an Agent invocation."""
        api_key = os.environ.get(self.key_environment, "")
        if not api_key:
            raise ArtifactPolicyError("evaluation provider key is unavailable")
        return RuntimeModelConfig(
            provider=self.provider,
            model=self.model,
            base_url=self.base_url,
            api_key=api_key,
            source="evaluation",
            provider_transport=self.provider_transport,
        )

    def public_metadata(self) -> dict[str, str | bool]:
        """Return runner metadata without reading the provider key.

        Evaluation runners need to advertise that a private resolver exists so
        the normal opening path will invoke it.  Reading the key here would
        make runner setup another credential boundary, so the resolver is the
        only code that reads it.
        """
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_set": True,
            "source": "evaluation",
            "key_error": "",
            "provider_transport": self.provider_transport,
        }


class EvaluationModelConfigResolver:
    """Inject one read-only evaluation config into a WebGameService runner."""

    def __init__(
        self,
        config: EvaluationModelConfig,
        *,
        model_call_observer: ModelCallObserver | None = None,
    ) -> None:
        self._config = config
        self._model_call_observer = model_call_observer

    def apply_runner(self, runner: WebRunner) -> None:
        runner.engine.model_config = self._config.public_metadata()
        runner.engine.model_runtime_resolver = self._config.runtime_config
        runner.engine.model_call_observer = self._model_call_observer

    # These members make accidental use through product settings fail closed.
    def build_stored(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise PermissionError("evaluation configuration is read-only")

    def public_settings(self, _config: dict[str, Any]) -> dict[str, Any]:
        raise PermissionError("evaluation configuration has no player settings")

    def system(self) -> dict[str, Any]:
        raise PermissionError("evaluation configuration has no system default")

    def effective(self, _user_id: str | None) -> dict[str, Any]:
        raise PermissionError("evaluation configuration has no player scope")

    def runtime(self, _user_id: str | None) -> dict[str, Any]:
        raise PermissionError("evaluation configuration must remain private")


def resolve_evaluation_runtime(
    factory: Callable[[], EvaluationModelConfig] = EvaluationModelConfig.from_environment,
) -> RuntimeModelConfig:
    """Small seam for scripts that need one direct agent invocation."""
    return factory().runtime_config()


def _provider_defaults(provider: str) -> tuple[str, str]:
    """Return non-secret defaults for a provider selected by the evaluator."""
    normalized = provider.strip().lower()
    if normalized == "agens":
        settings = Settings()
        return settings.model, settings.base_url
    if normalized == "deepseek":
        return _DEEPSEEK_DEFAULT_MODEL, _DEEPSEEK_DEFAULT_BASE_URL
    return "", ""
