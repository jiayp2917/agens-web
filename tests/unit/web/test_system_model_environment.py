from __future__ import annotations

from types import SimpleNamespace

import pytest

from web.backend.model_config_security import encrypt_api_key
from web.backend.service_model_config import ModelConfigService


@pytest.fixture(autouse=True)
def _clear_machine_model_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "AGNES_API_KEY",
        "DEEPSEEK_API_KEY",
        "AGENS_SYSTEM_MODEL_PROVIDER",
        "AGENS_SYSTEM_MODEL_BASE_URL",
        "AGENS_SYSTEM_MODEL",
        "AGENS_SYSTEM_MODEL_KEY_ENV",
        "MODEL_CONFIG_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)


def test_system_model_environment_selects_deepseek_without_persisting_a_key(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_SYSTEM_MODEL_PROVIDER", "DeepSeek")
    monkeypatch.setenv("AGENS_SYSTEM_MODEL_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("AGENS_SYSTEM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-system-key")
    service = ModelConfigService(SimpleNamespace(get_model_config=lambda: {}))

    config = service.system()

    assert config["provider"] == "DeepSeek"
    assert config["model"] == "deepseek-v4-flash"
    assert config["api_key_encrypted"] == ""
    assert config["api_key"] == "test-system-key"


def test_explicit_system_key_environment_does_not_depend_on_provider_label(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_SYSTEM_MODEL_PROVIDER", "OpenAI-compatible")
    monkeypatch.setenv("AGENS_SYSTEM_MODEL_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("AGENS_SYSTEM_MODEL", "compatible-model")
    monkeypatch.setenv("AGENS_SYSTEM_MODEL_KEY_ENV", "DEEPSEEK_API_KEY")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-system-key")
    service = ModelConfigService(SimpleNamespace(get_model_config=lambda: {}))

    config = service.system()

    assert config["provider"] == "OpenAI-compatible"
    assert config["base_url"] == "https://api.deepseek.com/v1"
    assert config["model"] == "compatible-model"
    assert config["api_key"] == "test-system-key"


def test_personal_model_configuration_still_overrides_system_environment(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_SYSTEM_MODEL_PROVIDER", "DeepSeek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-system-key")
    personal = {
        "provider": "Agens",
        "base_url": "https://apihub.agnes-ai.com/v1",
        "model": "personal-model",
        "api_key_encrypted": "ciphertext",
        "api_key_masked": "****test",
    }
    service = ModelConfigService(
        SimpleNamespace(get_model_config=lambda: {}, get_user_model_config=lambda _user_id: personal)
    )

    effective = service.effective("player-1")

    assert effective["source"] == "user"
    assert effective["model"] == "personal-model"


def test_stored_system_configuration_takes_priority_over_environment(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_SYSTEM_MODEL_PROVIDER", "DeepSeek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-system-key")
    stored = {
        "provider": "Agens",
        "base_url": "https://apihub.agnes-ai.com/v1",
        "model": "stored-model",
        "response_mode": "json_object",
        "stream": False,
        "api_key_encrypted": "ciphertext",
        "api_key_masked": "<set>",
    }

    config = ModelConfigService(SimpleNamespace(get_model_config=lambda: stored)).system()

    assert config["provider"] == "Agens"
    assert config["model"] == "stored-model"
    assert config["api_key_encrypted"] == "ciphertext"


@pytest.mark.parametrize(
    ("provider", "key_environment"),
    (("Agens", "AGNES_API_KEY"), ("DeepSeek", "DEEPSEEK_API_KEY")),
)
def test_environment_key_bypasses_unavailable_stored_ciphertext(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    key_environment: str,
) -> None:
    monkeypatch.setenv("AGENS_SYSTEM_MODEL_KEY_ENV", key_environment)
    monkeypatch.setenv(key_environment, "test-environment-key")
    stored = {
        "provider": provider,
        "base_url": "https://api.deepseek.com/v1",
        "model": "compatible-model",
        "api_key_encrypted": "fernet:unavailable-without-secret",
        "api_key_masked": "<stored>",
    }

    runtime = ModelConfigService(SimpleNamespace(get_model_config=lambda: stored)).runtime(None)

    assert runtime["api_key"] == "test-environment-key"
    assert runtime["api_key_set"] is True
    assert runtime["key_error"] == ""


def test_stored_key_remains_usable_when_secret_is_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    stored = {
        "provider": "Agens",
        "base_url": "https://apihub.agnes-ai.com/v1",
        "model": "compatible-model",
        "api_key_encrypted": encrypt_api_key("test-stored-key"),
        "api_key_masked": "<stored>",
    }

    runtime = ModelConfigService(SimpleNamespace(get_model_config=lambda: stored)).runtime(None)

    assert runtime["api_key"] == "test-stored-key"
    assert runtime["api_key_set"] is True
    assert runtime["key_error"] == ""


def test_missing_environment_and_unreadable_stored_key_has_safe_diagnostic() -> None:
    stored = {
        "provider": "Agens",
        "base_url": "https://apihub.agnes-ai.com/v1",
        "model": "compatible-model",
        "api_key_encrypted": "fernet:unavailable-without-secret",
        "api_key_masked": "<stored>",
    }

    runtime = ModelConfigService(SimpleNamespace(get_model_config=lambda: stored)).runtime(None)

    assert runtime["api_key"] == ""
    assert runtime["api_key_set"] is False
    assert runtime["key_error"] == "stored_model_key_unavailable"


def test_missing_system_key_has_safe_diagnostic() -> None:
    runtime = ModelConfigService(SimpleNamespace(get_model_config=lambda: {})).runtime(None)

    assert runtime["api_key"] == ""
    assert runtime["api_key_set"] is False
    assert runtime["key_error"] == "no_model_key_configured"
