"""Model-config resolution extracted from WebGameService.

Owns the stored/env -> public -> runtime config chain so WebGameService can
delegate model-config logic without owning it. Mirrors the service_summaries.py
split shape: a small service object taking the db explicitly.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from agens_novel.settings import Settings

from .model_config_security import (
    ModelConfigSecretError,
    decrypt_api_key,
    encrypt_api_key,
    mask_api_key,
)
from .database import WebDatabaseProtocol

if TYPE_CHECKING:
    from .service import WebRunner

_GUEST_PREFIX = "guest:"


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
        base_url = str(payload.get("base_url") or Settings().base_url).strip()
        model = str(payload.get("model") or Settings().model).strip()
        provider = str(payload.get("provider") or "Agens").strip()
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
            "api_key_set": api_key_set,
            "api_key_masked": masked if api_key_set else "<unset>",
            "api_key_encrypted": encrypted,
        }

    def public_settings(self, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider": config.get("provider") or "Agens",
            "base_url": config.get("base_url") or Settings().base_url,
            "model": config.get("model") or Settings().model,
            "api_key_set": bool(config.get("api_key_set")),
            "api_key_masked": str(config.get("api_key_masked") or "<unset>"),
            "source": config.get("source") or "system",
        }

    def system(self) -> dict[str, Any]:
        stored = self.db.get_model_config() or {}
        settings = Settings()
        source = "system"
        env_key = os.environ.get("AGNES_API_KEY", "")
        if stored:
            encrypted = str(stored.get("api_key_encrypted") or "")
            config = {
                "provider": stored.get("provider") or "Agens",
                "base_url": stored.get("base_url") or settings.base_url,
                "model": stored.get("model") or settings.model,
                "api_key_set": bool(encrypted or env_key),
                "api_key_masked": stored.get("api_key_masked") if encrypted else (mask_api_key(env_key) if env_key else "<unset>"),
                "api_key_encrypted": encrypted,
                "source": source,
            }
            if not encrypted and env_key:
                config["api_key"] = env_key
        else:
            config = {
                "provider": "Agens",
                "base_url": os.environ.get("AGNES_BASE_URL") or settings.base_url,
                "model": os.environ.get("AGNES_MODEL") or settings.model,
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
        if encrypted:
            try:
                api_key = decrypt_api_key(encrypted)
            except ModelConfigSecretError:
                api_key = ""
                key_error = "MODEL_CONFIG_SECRET unavailable"
        return {
            "provider": effective.get("provider") or "Agens",
            "base_url": effective.get("base_url") or Settings().base_url,
            "model": effective.get("model") or Settings().model,
            "api_key": api_key,
            "api_key_set": bool(api_key),
            "source": effective.get("source") or "system",
            "key_error": key_error,
        }

    def apply_runner(self, runner: "WebRunner") -> None:
        runner.engine.model_config = self.runtime(runner.user_id)
