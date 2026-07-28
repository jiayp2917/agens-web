from __future__ import annotations

from types import SimpleNamespace

from web.backend.service_model_config import ModelConfigService


def test_system_model_environment_selects_deepseek_without_persisting_a_key(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_SYSTEM_MODEL_PROVIDER", "DeepSeek")
    monkeypatch.setenv("AGENS_SYSTEM_MODEL_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("AGENS_SYSTEM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-system-key")
    service = ModelConfigService(SimpleNamespace(get_model_config=lambda: {"provider": "Agens"}))

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
    service = ModelConfigService(SimpleNamespace(get_model_config=lambda: {"provider": "Agens"}))

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
