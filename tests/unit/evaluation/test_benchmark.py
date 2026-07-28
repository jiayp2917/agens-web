"""Tests for isolated frozen snapshots and anonymous blind-review packets."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.artifacts import sink
from agens_novel.evaluation.benchmark import (
    build_blind_review_packet,
    frozen_benchmark_acceptance,
    frozen_narrator_snapshots,
    run_frozen_benchmark,
)
from agens_novel.evaluation.ledger import EvaluationBudget, EvaluationLedger
from agens_novel.evaluation.model_config import EvaluationModelConfig


def _config(tmp_path, monkeypatch, provider: str) -> EvaluationModelConfig:
    monkeypatch.setenv("AGENS_EVALUATION_MODE", "1")
    monkeypatch.setenv("AGENS_ARTIFACT_ROOT", str(tmp_path / "evidence"))
    monkeypatch.setenv("AGENS_EVALUATION_PROVIDER", provider)
    monkeypatch.setenv("AGENS_EVALUATION_MODEL", f"{provider.lower()}-test")
    monkeypatch.setenv("AGENS_EVALUATION_BASE_URL", "https://provider.invalid/v1")
    monkeypatch.setenv("AGNES_API_KEY" if provider == "Agens" else "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(sink, "_restrict_windows_acl", lambda _root: None)
    return EvaluationModelConfig.from_environment()


def test_frozen_benchmark_uses_nine_independent_snapshots(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path, monkeypatch, "DeepSeek")

    def fake_run_agent(self, _agent, _user_input, _session, **_kwargs):
        ticket = self.model_call_observer.before_request(
            agent="narrator",
            transport="json_object",
            stream=False,
        )
        self.model_call_observer.after_request(
            ticket,
            elapsed_ms=1,
            usage={},
            success=True,
        )
        return {
            "narrative": "潮声渐远，旧灯照出一段尚未兑现的约定。",
            "choices": ["稳步探查", "结交舟客", "越过暗礁", "借潮试路"],
            "llm_error": "",
        }

    with patch("agens_novel.evaluation.benchmark.GameEngine.run_agent", fake_run_agent):
        report, _path = run_frozen_benchmark(
            config,
            ledger=EvaluationLedger(provider="DeepSeek", model="deepseek-test"),
        )

    snapshots = frozen_narrator_snapshots()
    assert len(snapshots) == 9
    assert [item.turn_count for item in snapshots if item.scenario_key == "low_risk"] == [1, 45, 90]
    assert all(item.session.story_version == 3 for item in snapshots)
    assert all(item.authority_hash for item in snapshots)
    assert len(report["results"]) == 9
    assert all(result["strict"] for result in report["results"])
    assert len({result["snapshot_id"] for result in report["results"]}) == 9
    assert report["acceptance"]["accepted"] is True


def test_frozen_benchmark_records_past_legacy_shared_budget_limits(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path, monkeypatch, "DeepSeek")
    budget = EvaluationBudget(
        tmp_path / "evidence",
        max_total_calls=1,
        max_narrator_calls=1,
    )

    def fake_run_agent(self, _agent, _user_input, _session, **_kwargs):
        ticket = self.model_call_observer.before_request(
            agent="narrator",
            transport="json_object",
            stream=False,
        )
        self.model_call_observer.after_request(
            ticket,
            elapsed_ms=1,
            usage={},
            success=True,
        )
        return {
            "narrative": "潮声渐远，旧灯照出一段尚未兑现的约定。",
            "choices": ["稳步探查", "结交船客", "越过暗礁", "借潮试路"],
            "llm_error": "",
        }

    with patch("agens_novel.evaluation.benchmark.GameEngine.run_agent", fake_run_agent):
        run_frozen_benchmark(
            config,
            ledger=EvaluationLedger(
                provider="DeepSeek",
                model="deepseek-test",
                shared_budget=budget,
            ),
        )

    assert budget.summary()["reserved_total"] == 9
    assert budget.summary()["reserved_narrator"] == 9


def test_blind_packet_hides_provider_and_model_names(tmp_path, monkeypatch) -> None:
    first = _config(tmp_path, monkeypatch, "Agens")
    second = _config(tmp_path, monkeypatch, "DeepSeek")

    def fake_run_agent(self, _agent, _user_input, _session, **_kwargs):
        narrative = "甲方叙事正文。" if self.model_config["provider"] == "Agens" else "乙方叙事正文。"
        return {
            "narrative": narrative,
            "choices": ["稳步探查", "结交舟客", "越过暗礁", "借潮试路"],
            "llm_error": "",
        }

    with patch("agens_novel.evaluation.benchmark.GameEngine.run_agent", fake_run_agent):
        first_report, _ = run_frozen_benchmark(
            first,
            ledger=EvaluationLedger(provider="Agens", model="agens-test"),
        )
        second_report, _ = run_frozen_benchmark(
            second,
            ledger=EvaluationLedger(provider="DeepSeek", model="deepseek-test"),
        )
    packet, path = build_blind_review_packet(first_report, second_report, review_seed="test")

    saved = path.read_text(encoding="utf-8")
    assert packet["pair_count"] == 9
    assert "Agens" not in saved
    assert "DeepSeek" not in saved


def test_frozen_benchmark_acceptance_reports_stable_issue_codes_without_text() -> None:
    report = {
        "results": [
            {
                "snapshot_id": item.snapshot_id,
                "strict": True,
                "narrative": "合格叙事。",
                "choices": ["稳住根基", "拜访旧友", "踏入险地", "静候天命"],
            }
            for item in frozen_narrator_snapshots()
        ]
    }

    assert frozen_benchmark_acceptance(report)["accepted"] is True
    report["results"][0]["narrative"] = "English residue"
    result = frozen_benchmark_acceptance(report)

    assert result["accepted"] is False
    assert result["issues"] == [
        {"level": "P1", "sample": "high_steady-opening", "code": "visible_english"}
    ]
