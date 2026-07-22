"""Tests for the deterministic local playthrough runner."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.artifacts import sink
from agens_novel.evaluation.ledger import EvaluationLedger
from agens_novel.evaluation.model_config import EvaluationModelConfig
from agens_novel.evaluation.playthrough import canonical_slots, run_canonical_playthrough
from agens_novel.evaluation.scenarios import canonical_v3_scenarios


def test_playthrough_uses_canonical_binding_and_records_safe_result(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENS_EVALUATION_MODE", "1")
    monkeypatch.setenv("AGENS_ARTIFACT_ROOT", str(tmp_path / "evidence"))
    monkeypatch.setenv("AGENS_EVALUATION_PROVIDER", "DeepSeek")
    monkeypatch.setenv("AGENS_EVALUATION_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("AGENS_EVALUATION_BASE_URL", "https://api.deepseek.example/v1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-evaluation-key")
    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)
    config = EvaluationModelConfig.from_environment()

    def fake_turn(_agent, _input, _session, **_kwargs):
        return {
            "narrative": "潮雾散开，渡口的旧灯仍在。",
            "choices": ["A 守住渡口", "B 询问舟客", "C 越过暗礁", "D 借潮试路"],
            "state_delta": {},
            "llm_error": "",
        }

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_turn):
        result = run_canonical_playthrough(
            config,
            canonical_v3_scenarios()[0],
            story_version=3,
            ledger=EvaluationLedger(provider="DeepSeek", model="deepseek-v4-flash"),
            max_turns=2,
        )

    assert result["turn_count"] == 2
    assert result["run_seed"] == "v3-eval-frontier-high-steady-000"
    assert result["narrator_event_count"] == 2
    assert result["narrator_final_strict"] == 2
    assert result["local_story_active"] is False
    assert len(result["accepted_turns"]) == 2
    assert all(turn["authority"]["matches_expected"] for turn in result["accepted_turns"])
    assert all(turn["strict"]["final"] for turn in result["accepted_turns"])
    assert all(len(turn["choices"]) == 4 for turn in result["accepted_turns"])
    assert sink.external_inventory(tmp_path / "evidence")["file_count"] >= 2


def test_canonical_slots_extend_only_for_post_arc_coverage() -> None:
    scenario = canonical_v3_scenarios()[0]

    assert canonical_slots(scenario, max_turns=90) == scenario.slots
    assert canonical_slots(scenario, max_turns=95) == scenario.slots + ("A",) * 5
