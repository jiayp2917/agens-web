"""Non-network tests for the one-request opening canary."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from agens_novel.evaluation.ledger import EvaluationLedger
from agens_novel.evaluation.model_config import EvaluationModelConfig

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "run_opening_canary",
    ROOT / "scripts" / "run_opening_canary.py",
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_opening_canary_rejects_a_non_strict_opening(monkeypatch) -> None:
    monkeypatch.delenv("AGNES_MAX_RETRIES", raising=False)
    config = EvaluationModelConfig(
        provider="Agens",
        model="test-model",
        base_url="https://provider.invalid/v1",
        key_environment="AGNES_API_KEY",
    )
    observed: list[str] = []

    def start_from_profile(self, _profile):
        observed.append("1")
        assert os.environ["AGENS_EVALUATION_OPENING_MAX_ATTEMPTS"] == "1"
        assert os.environ["AGNES_MAX_RETRIES"] == "0"
        self.log_model_result(
            agent="world_builder",
            source="profile_opening",
            status="incomplete_output",
            reason="invalid opening",
            result={"generated_data": {}, "llm_error": ""},
        )

    monkeypatch.setattr("agens_novel.engine.game_engine.GameEngine.start_from_profile", start_from_profile)
    result = runner.run_opening_canary(
        config,
        "high_steady",
        EvaluationLedger(provider="Agens", model="test"),
    )

    assert observed == ["1"]
    assert result["accepted"] is False
    assert result["opening_event_count"] == 1
    assert result["opening_strict"] is False
    assert "AGNES_MAX_RETRIES" not in os.environ
