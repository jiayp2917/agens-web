"""Model-config resolution extracted from WebGameService.

Owns the stored/env -> public -> runtime config chain so WebGameService can
delegate model-config logic without owning it. Mirrors the service_summaries.py
split shape: a small service object taking the db explicitly.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Protocol

from agens_novel.llm.runtime_context import RuntimeModelConfig
from agens_novel.llm.url_security import validate_model_base_url
from agens_novel.settings import Settings

from .database import WebDatabaseProtocol
from .model_config_security import (
    ModelConfigSecretError,
    decrypt_api_key,
    encrypt_api_key,
    mask_api_key,
)

if TYPE_CHECKING:
    from .service import WebRunner

_GUEST_PREFIX = "guest:"
_SYSTEM_KEY_ENV_BY_PROVIDER = {
    "agens": "AGNES_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}
_SYSTEM_KEY_ENVIRONMENTS = frozenset(_SYSTEM_KEY_ENV_BY_PROVIDER.values())
_DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
_DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-flash"
_RESPONSE_MODES = {"json_schema", "json_object"}


class ModelConfigResolver(Protocol):
    """Attach a private runtime config resolver to one Web game runner."""

    def build_stored(
        self,
        payload: dict[str, Any],
        *,
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def public_settings(self, config: dict[str, Any]) -> dict[str, Any]: ...

    def system(self) -> dict[str, Any]: ...

    def effective(self, user_id: str | None) -> dict[str, Any]: ...

    def runtime(self, user_id: str | None) -> dict[str, Any]: ...

    def apply_runner(self, runner: WebRunner) -> None: ...


class ModelConfigService:
    """Resolve stored/env model config into public and runtime forms."""

    def __init__(self, db: WebDatabaseProtocol) -> None:
        self.db = db

    def build_stored(
        self,
        payload: dict[str, Any],
        *,
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing = existing or {}
        base_url = validate_model_base_url(
            str(payload.get("base_url") or Settings().base_url).strip(),
            resolve_dns=True,
        )
        model = str(payload.get("model") or Settings().model).strip()
        provider = str(payload.get("provider") or "Agens").strip()
        response_mode = str(
            payload.get("response_mode") or existing.get("response_mode") or "json_object"
        ).strip().lower()
        if response_mode not in _RESPONSE_MODES:
            raise ValueError("response_mode is unsupported")
        api_key = str(payload.get("api_key") or "").strip()
        encrypted = str(existing.get("api_key_encrypted") or "")
        masked = str(existing.get("api_key_masked") or "<unset>")
        if api_key:
            try:
                encrypted = encrypt_api_key(api_key)
            except ModelConfigSecretError as exc:
                raise ValueError("MODEL_CONFIG_SECRET is required to save model keys.") from exc
            masked = mask_api_key(api_key)
        elif not encrypted:
            raise ValueError("API Key is required when creating a stored model config.")
        api_key_set = bool(encrypted)
        return {
            "provider": provider,
            "base_url": base_url,
            "model": model,
            "response_mode": response_mode,
            "stream": bool(payload.get("stream", existing.get("stream", False))),
            "api_key_set": api_key_set,
            "api_key_masked": masked if api_key_set else "<unset>",
            "api_key_encrypted": encrypted,
        }

    def public_settings(self, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider": config.get("provider") or "Agens",
            "base_url": config.get("base_url") or Settings().base_url,
            "model": config.get("model") or Settings().model,
            "response_mode": config.get("response_mode") or "json_object",
            "stream": bool(config.get("stream", False)),
            "api_key_set": bool(config.get("api_key_set")),
            "api_key_masked": str(config.get("api_key_masked") or "<unset>"),
            "source": config.get("source") or "system",
        }

    def system(self) -> dict[str, Any]:
        stored = self.db.get_model_config() or {}
        settings = Settings()
        source = "system"
        env_key = _system_environment_api_key()
        if stored:
            encrypted = str(stored.get("api_key_encrypted") or "")
            config = {
                "provider": stored.get("provider") or "Agens",
                "base_url": stored.get("base_url") or settings.base_url,
                "model": stored.get("model") or settings.model,
                "response_mode": stored.get("response_mode") or "json_object",
                "stream": bool(stored.get("stream", False)),
                "api_key_set": bool(encrypted or env_key),
                "api_key_masked": mask_api_key(env_key) if env_key else stored.get("api_key_masked", "<unset>"),
                "api_key_encrypted": encrypted,
                "source": source,
            }
            if env_key:
                config["api_key"] = env_key
        else:
            configured = _system_environment_config()
            if configured is not None:
                return configured
            config = {
                "provider": "Agens",
                "base_url": os.environ.get("AGNES_BASE_URL") or settings.base_url,
                "model": os.environ.get("AGNES_MODEL") or settings.model,
                "response_mode": os.environ.get("AGENS_MODEL_RESPONSE_MODE") or "json_object",
                "stream": os.environ.get("AGENS_MODEL_STREAM") == "1",
                "api_key_set": bool(env_key),
                "api_key_masked": mask_api_key(env_key) if env_key else "<unset>",
                "api_key_encrypted": "",
                "source": source,
                "api_key": env_key,
            }
        return config

    def effective(self, user_id: str | None) -> dict[str, Any]:
        if user_id and not user_id.startswith(_GUEST_PREFIX):
            personal = self.db.get_user_model_config(user_id)
            if personal is not None and personal.get("api_key_encrypted"):
                return {
                    "provider": personal.get("provider") or "Agens",
                    "base_url": personal.get("base_url") or Settings().base_url,
                    "model": personal.get("model") or Settings().model,
                    "response_mode": personal.get("response_mode") or "json_object",
                    "stream": bool(personal.get("stream", False)),
                    "api_key_set": bool(personal.get("api_key_encrypted")),
                    "api_key_masked": personal.get("api_key_masked") if personal.get("api_key_encrypted") else "<unset>",
                    "api_key_encrypted": personal.get("api_key_encrypted") or "",
                    "source": "user",
                }
        return self.system()

    def runtime(self, user_id: str | None) -> dict[str, Any]:
        effective = self.effective(user_id)
        encrypted = str(effective.get("api_key_encrypted") or "")
        api_key = str(effective.get("api_key") or "")
        key_error = ""
        if encrypted and not api_key:
            try:
                api_key = decrypt_api_key(encrypted)
            except ModelConfigSecretError:
                api_key = ""
                key_error = "stored_model_key_unavailable"
        if not api_key and not key_error:
            key_error = "no_model_key_configured"
        return {
            "provider": effective.get("provider") or "Agens",
            "base_url": effective.get("base_url") or Settings().base_url,
            "model": effective.get("model") or Settings().model,
            "response_mode": effective.get("response_mode") or "json_object",
            "stream": bool(effective.get("stream", False)),
            "api_key": api_key,
            "api_key_set": bool(api_key),
            "source": effective.get("source") or "system",
            "key_error": key_error,
        }

    def runtime_config(self, user_id: str | None) -> RuntimeModelConfig:
        """Resolve one private config immediately before an Agent call."""
        runtime = self.runtime(user_id)
        return RuntimeModelConfig(
            provider=str(runtime["provider"]),
            model=str(runtime["model"]),
            base_url=str(runtime["base_url"]),
            api_key=str(runtime["api_key"]),
            source=str(runtime["source"]),
            key_error=str(runtime["key_error"]),
            response_mode=str(runtime["response_mode"]),
            stream=bool(runtime["stream"]),
        )

    def apply_runner(self, runner: WebRunner) -> None:
        # The runner retains only safe metadata. The resolver decrypts a key
        # only for the single call that installs the private ContextVar.
        metadata = self.runtime_config(runner.user_id).public_metadata()
        runner.engine.model_config = metadata
        runner.engine.model_runtime_resolver = lambda: self.runtime_config(runner.user_id)


def _system_environment_config() -> dict[str, Any] | None:
    """Resolve the deployment-owned system model without persisting its key."""
    provider_raw = os.environ.get("AGENS_SYSTEM_MODEL_PROVIDER", "").strip()
    base_url_raw = os.environ.get("AGENS_SYSTEM_MODEL_BASE_URL", "").strip()
    model_raw = os.environ.get("AGENS_SYSTEM_MODEL", "").strip()
    key_environment_raw = os.environ.get("AGENS_SYSTEM_MODEL_KEY_ENV", "").strip()
    if not any((provider_raw, base_url_raw, model_raw, key_environment_raw)):
        return None

    settings = Settings()
    if key_environment_raw:
        if key_environment_raw not in _SYSTEM_KEY_ENVIRONMENTS:
            raise ValueError("AGENS_SYSTEM_MODEL_KEY_ENV is unsupported")
        provider = provider_raw or "Agens"
        default_base_url, default_model = settings.base_url, settings.model
        key_environment = key_environment_raw
    else:
        # Existing deployments selected their private key from the provider
        # label. Keep that configuration readable while new configs use the
        # explicit restricted key-variable field above.
        provider_key = provider_raw.lower() or "agens"
        legacy_key_environment = _SYSTEM_KEY_ENV_BY_PROVIDER.get(provider_key)
        if legacy_key_environment is None:
            raise ValueError("AGENS_SYSTEM_MODEL_KEY_ENV is required for this provider")
        key_environment = legacy_key_environment
        provider = "DeepSeek" if provider_key == "deepseek" else "Agens"
        default_base_url, default_model = settings.base_url, settings.model
        if provider_key == "deepseek":
            default_base_url, default_model = (
                _DEEPSEEK_DEFAULT_BASE_URL,
                _DEEPSEEK_DEFAULT_MODEL,
            )
    base_url = validate_model_base_url(base_url_raw or default_base_url, resolve_dns=False)
    model = model_raw or default_model
    response_mode = os.environ.get("AGENS_SYSTEM_MODEL_RESPONSE_MODE", "json_object").strip().lower()
    if response_mode not in _RESPONSE_MODES:
        raise ValueError("AGENS_SYSTEM_MODEL_RESPONSE_MODE is unsupported")
    api_key = os.environ.get(key_environment, "")
    return {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "response_mode": response_mode,
        "stream": os.environ.get("AGENS_SYSTEM_MODEL_STREAM") == "1",
        "api_key_set": bool(api_key),
        "api_key_masked": mask_api_key(api_key) if api_key else "<unset>",
        "api_key_encrypted": "",
        "source": "system",
        "api_key": api_key,
    }


def _system_environment_api_key() -> str:
    """Read the explicitly configured system key, then the Agens-compatible default."""
    key_environment = os.environ.get("AGENS_SYSTEM_MODEL_KEY_ENV", "").strip()
    if key_environment in _SYSTEM_KEY_ENVIRONMENTS:
        return os.environ.get(key_environment, "")
    return os.environ.get("AGNES_API_KEY", "")
