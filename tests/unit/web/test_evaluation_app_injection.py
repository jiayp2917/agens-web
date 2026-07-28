"""Evaluation-only FastAPI wiring must not use player model settings."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agens_novel.artifacts import sink
from agens_novel.evaluation.model_config import EvaluationModelConfig, EvaluationModelConfigResolver
from web.backend import evaluation_app


def _evaluation_env(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENS_ENV", raising=False)
    monkeypatch.setenv("AGENS_EVALUATION_MODE", "1")
    monkeypatch.setenv("AGENS_ARTIFACT_ROOT", str(tmp_path / "evidence"))
    monkeypatch.setenv("AGENS_EVALUATION_PROVIDER", "DeepSeek")
    monkeypatch.setenv("AGENS_EVALUATION_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("AGENS_EVALUATION_BASE_URL", "https://provider.invalid/v1")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://evaluation@127.0.0.1:55432/agens_web_eval_test",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-evaluation-key")
    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)


def test_product_factory_rejects_evaluation_mode_without_the_isolated_factory(
    tmp_path, monkeypatch
) -> None:
    _evaluation_env(tmp_path, monkeypatch)
    from web.backend.app import create_app

    with pytest.raises(RuntimeError, match="evaluation mode requires"):
        create_app()


def test_create_app_injects_read_only_evaluation_resolver(tmp_path, monkeypatch) -> None:
    _evaluation_env(tmp_path, monkeypatch)
    monkeypatch.setattr(
        evaluation_app,
        "create_database",
        lambda: SimpleNamespace(get_user_model_config=lambda _user_id: {}),
    )

    app = evaluation_app.create_evaluation_app()
    service = app.state.service

    assert isinstance(service._model_config, EvaluationModelConfigResolver)
    assert app.state.evaluation_ledger is not None
    with pytest.raises(PermissionError, match="read-only"):
        service.update_model_settings("player-1", {"api_key": "not-used"})


def test_evaluation_app_runner_setup_does_not_read_a_key(tmp_path, monkeypatch) -> None:
    _evaluation_env(tmp_path, monkeypatch)
    monkeypatch.setattr(evaluation_app, "create_database", lambda: SimpleNamespace())
    app = evaluation_app.create_evaluation_app()
    resolver = app.state.service._model_config
    runtime_calls: list[bool] = []
    original_runtime_config = EvaluationModelConfig.runtime_config

    def runtime_config(self):
        runtime_calls.append(True)
        return original_runtime_config(self)

    monkeypatch.setattr(EvaluationModelConfig, "runtime_config", runtime_config)
    runner = SimpleNamespace(engine=SimpleNamespace(model_config={}, model_runtime_resolver=None, model_call_observer=None))

    resolver.apply_runner(runner)

    assert runtime_calls == []
    assert runner.engine.model_config["api_key_set"] is True
    assert runner.engine.model_runtime_resolver is not None


def test_evaluation_app_uses_a_record_only_shared_call_record(tmp_path, monkeypatch) -> None:
    _evaluation_env(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENS_EVALUATION_RECORD_ONLY", "1")
    monkeypatch.setattr(evaluation_app, "create_database", lambda: SimpleNamespace())

    app = evaluation_app.create_evaluation_app()

    assert app.state.evaluation_ledger.record_only is True
    assert app.state.evaluation_ledger.shared_budget is not None
    assert app.state.evaluation_ledger.shared_budget.summary()["reserved_total"] == 0


def test_evaluation_app_pins_the_requested_story_version(tmp_path, monkeypatch) -> None:
    _evaluation_env(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENS_EVALUATION_STORY_VERSION", "2")
    monkeypatch.setattr(evaluation_app, "create_database", lambda: SimpleNamespace())

    app = evaluation_app.create_evaluation_app()

    assert app.state.service._run_policy._story_version == 2


def test_evaluation_app_rejects_a_database_without_an_isolation_name(tmp_path, monkeypatch) -> None:
    _evaluation_env(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://evaluation@127.0.0.1:55432/agens_web_test",
    )

    with pytest.raises(RuntimeError, match="explicitly named evaluation database"):
        evaluation_app.create_evaluation_app()
