"""Tests for record-only local evaluation accounting."""

from __future__ import annotations

import json

import pytest

from agens_novel.evaluation.ledger import (
    EvaluationBudget,
    EvaluationBudgetExceeded,
    EvaluationLedger,
    PriceCard,
    configured_evaluation_limits,
    evaluation_budget_root,
    evaluation_record_only,
)


def test_ledger_records_past_legacy_call_and_time_limits() -> None:
    now = [100.0]
    ledger = EvaluationLedger(
        provider="Agens",
        model="test",
        max_total_calls=1,
        max_narrator_calls=1,
        max_elapsed_seconds=0.0,
        clock=lambda: now[0],
    )

    first = ledger.reserve("narrator")
    now[0] += 5.0
    second = ledger.reserve("narrator")
    ledger.record(
        request_id=first,
        agent="narrator",
        transport="json_object",
        elapsed_ms=10,
        usage={"total_tokens": 3},
    )
    ledger.record(
        request_id=second,
        agent="narrator",
        transport="json_object",
        elapsed_ms=20,
        usage={"total_tokens": 4},
    )

    assert ledger.summary()["call_count"] == 2
    assert ledger.summary()["narrator_call_count"] == 2
    assert ledger.summary()["run_elapsed_ms"] == 5000
    assert ledger.summary()["record_only"] is True


def test_ledger_keeps_cost_metrics_without_using_a_cost_limit() -> None:
    price = PriceCard("2026-07-21", "USD", input_per_million=1.0, output_per_million=2.0)
    ledger = EvaluationLedger(
        provider="Agens",
        model="test",
        price_card=price,
        cost_limit=0.00003,
    )

    for _ in range(2):
        request_id = ledger.reserve("narrator")
        ledger.record(
            request_id=request_id,
            agent="narrator",
            transport="json_object",
            elapsed_ms=100,
            usage={"prompt_tokens": 10, "completion_tokens": 10},
        )

    assert ledger.summary()["estimated_cost"] == pytest.approx(0.00006)
    assert ledger.summary()["call_count"] == 2


def test_shared_call_record_survives_multiple_ledgers_without_caps(tmp_path) -> None:
    record = EvaluationBudget(
        tmp_path / "external-evidence",
        max_total_calls=1,
        max_narrator_calls=1,
        hard_cost_limit=0.01,
    )
    first = EvaluationLedger(provider="Agens", model="test", shared_budget=record)
    second = EvaluationLedger(provider="DeepSeek", model="test", shared_budget=record)

    assert first.reserve("narrator") == "global-0001"
    assert second.reserve("judge") == "global-0002"
    assert second.reserve("world_builder") == "global-0003"

    assert record.summary() == {
        "reserved_total": 3,
        "reserved_narrator": 1,
        "reserved_cost": 0.0,
    }


def test_shared_call_record_migrates_old_budget_state_without_resetting_usage(tmp_path) -> None:
    root = tmp_path / "prior-evidence"
    root.mkdir()
    (root / "evaluation-budget.json").write_text(
        json.dumps(
            {
                "version": 1,
                "max_total_calls": 2,
                "max_narrator_calls": 1,
                "hard_cost_limit": 0.2,
                "reserved_total": 2,
                "reserved_narrator": 1,
                "reserved_cost": 0.1,
                "sequence": 2,
            }
        ),
        encoding="utf-8",
    )

    record = EvaluationBudget.open_existing(root)

    assert record.reserve("narrator") == "global-0003"
    assert record.summary()["reserved_total"] == 3
    saved = json.loads((root / "evaluation-budget.json").read_text(encoding="utf-8"))
    assert saved == {
        "reserved_cost": 0.1,
        "reserved_narrator": 2,
        "reserved_total": 3,
        "sequence": 3,
        "version": 2,
    }


def test_configured_budget_root_accepts_a_new_external_record_root(tmp_path, monkeypatch) -> None:
    target = tmp_path / "new-record"
    monkeypatch.setenv("AGENS_EVALUATION_BUDGET_ROOT", str(target))

    assert evaluation_budget_root(tmp_path / "new-evidence") == target.resolve()


def test_configured_budget_root_rejects_a_repository_path(monkeypatch) -> None:
    from agens_novel import paths

    monkeypatch.setenv("AGENS_EVALUATION_BUDGET_ROOT", str(paths.PROJECT_ROOT))

    with pytest.raises(EvaluationBudgetExceeded, match="outside the repository"):
        evaluation_budget_root(paths.PROJECT_ROOT / "evidence")


def test_legacy_limit_configuration_is_inert(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_EVALUATION_MAX_TOTAL_CALLS", "1")
    monkeypatch.setenv("AGENS_EVALUATION_MAX_NARRATOR_CALLS", "1")
    monkeypatch.delenv("AGENS_EVALUATION_RECORD_ONLY", raising=False)

    assert configured_evaluation_limits() == (0, 0)
    assert evaluation_record_only() is True
