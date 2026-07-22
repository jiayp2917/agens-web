"""Tests for local-only, secret-contained evaluation config."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agens_novel.artifacts import sink
from agens_novel.evaluation.model_config import (
    EvaluationModelConfig,
    EvaluationModelConfigResolver,
)


def _evaluation_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENS_EVALUATION_MODE", "1")
    monkeypatch.setenv("AGENS_ARTIFACT_ROOT", str(tmp_path / "evidence"))
    monkeypatch.setenv("AGENS_EVALUATION_PROVIDER", "DeepSeek")
    monkeypatch.setenv("AGENS_EVALUATION_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("AGENS_EVALUATION_BASE_URL", "https://api.deepseek.example/v1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-evaluation-key")
    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)


def test_evaluation_config_keeps_key_out_of_persisted_configuration(tmp_path, monkeypatch) -> None:
    _evaluation_env(tmp_path, monkeypatch)

    config = EvaluationModelConfig.from_environment()

    assert "test-evaluation-key" not in repr(config)
    assert config.key_environment == "DEEPSEEK_API_KEY"
    assert config.runtime_config().api_key == "test-evaluation-key"


def test_evaluation_resolver_installs_public_metadata_and_private_callback(tmp_path, monkeypatch) -> None:
    _evaluation_env(tmp_path, monkeypatch)
    engine = SimpleNamespace(model_config={}, model_runtime_resolver=None)
    runner = SimpleNamespace(engine=engine)
    config = EvaluationModelConfig.from_environment()
    calls: list[bool] = []
    original_runtime_config = EvaluationModelConfig.runtime_config

    def runtime_config(self):
        calls.append(True)
        return original_runtime_config(self)

    monkeypatch.setattr(EvaluationModelConfig, "runtime_config", runtime_config)

    EvaluationModelConfigResolver(config).apply_runner(runner)

    assert engine.model_config["provider"] == "DeepSeek"
    assert "api_key" not in engine.model_config
    assert engine.model_runtime_resolver is not None
    assert calls == []
    assert engine.model_runtime_resolver().api_key == "test-evaluation-key"
    assert calls == [True]


def test_evaluation_transport_is_explicit_and_never_uses_product_config(tmp_path, monkeypatch) -> None:
    _evaluation_env(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENS_EVALUATION_TRANSPORT", "json_object")

    config = EvaluationModelConfig.from_environment()

    assert config.provider_transport == "json_object"
    assert config.runtime_config().public_metadata()["provider_transport"] == "json_object"


def test_evaluation_config_rejects_unknown_transport(tmp_path, monkeypatch) -> None:
    _evaluation_env(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENS_EVALUATION_TRANSPORT", "invalid")

    with pytest.raises(sink.ArtifactPolicyError, match="transport"):
        EvaluationModelConfig.from_environment()


def test_evaluation_config_rejects_unknown_provider(tmp_path, monkeypatch) -> None:
    _evaluation_env(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENS_EVALUATION_PROVIDER", "other")

    with pytest.raises(sink.ArtifactPolicyError, match="provider"):
        EvaluationModelConfig.from_environment()


def test_evaluation_config_uses_non_secret_agens_profile_defaults(tmp_path, monkeypatch) -> None:
    _evaluation_env(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENS_EVALUATION_PROVIDER", "agens")
    monkeypatch.delenv("AGENS_EVALUATION_MODEL")
    monkeypatch.delenv("AGENS_EVALUATION_BASE_URL")
    monkeypatch.setenv("AGNES_MODEL", "agens-evaluation-model")
    monkeypatch.setenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")

    config = EvaluationModelConfig.from_environment()

    assert config.model == "agens-evaluation-model"
    assert config.base_url == "https://apihub.agnes-ai.com/v1"


def test_evaluation_config_uses_locked_deepseek_profile_defaults(tmp_path, monkeypatch) -> None:
    _evaluation_env(tmp_path, monkeypatch)
    monkeypatch.delenv("AGENS_EVALUATION_MODEL")
    monkeypatch.delenv("AGENS_EVALUATION_BASE_URL")

    config = EvaluationModelConfig.from_environment()

    assert config.model == "deepseek-v4-flash"
    assert config.base_url == "https://api.deepseek.com/v1"
