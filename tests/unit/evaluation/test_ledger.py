"""Tests for local evaluation accounting and request caps."""

from __future__ import annotations

import pytest

from agens_novel.evaluation.ledger import (
    EvaluationBudget,
    EvaluationBudgetExceeded,
    EvaluationLedger,
    PriceCard,
    configured_evaluation_limits,
    evaluation_budget_root,
)


def test_ledger_enforces_narrator_and_total_caps_before_dispatch() -> None:
    ledger = EvaluationLedger(provider="Agens", model="test", max_total_calls=2, max_narrator_calls=1)

    assert ledger.reserve("narrator") == "call-0001"
    assert ledger.reserve("judge") == "call-0002"
    with pytest.raises(EvaluationBudgetExceeded, match="provider request cap"):
        ledger.reserve("world_opening")


def test_ledger_enforces_elapsed_time_cap_before_dispatch() -> None:
    now = [100.0]
    ledger = EvaluationLedger(
        provider="Agens",
        model="test",
        max_elapsed_seconds=5.0,
        clock=lambda: now[0],
    )

    assert ledger.reserve("narrator") == "call-0001"
    now[0] += 5.0

    with pytest.raises(EvaluationBudgetExceeded, match="time cap"):
        ledger.reserve("narrator")
    assert ledger.summary()["run_elapsed_ms"] == 5000


def test_record_only_ledger_keeps_metrics_without_enforcing_caps() -> None:
    ledger = EvaluationLedger(
        provider="Agens",
        model="test",
        max_total_calls=1,
        max_narrator_calls=1,
        max_elapsed_seconds=0.0,
        record_only=True,
    )

    first = ledger.reserve("narrator")
    second = ledger.reserve("narrator")
    ledger.record(
        request_id=first,
        agent="narrator",
        transport="json_schema",
        elapsed_ms=10,
        usage={"total_tokens": 3},
    )
    ledger.record(
        request_id=second,
        agent="narrator",
        transport="json_schema",
        elapsed_ms=20,
        usage={"total_tokens": 4},
    )

    assert ledger.summary()["record_only"] is True
    assert ledger.summary()["call_count"] == 2


def test_ledger_reports_unknown_cost_without_a_confirmed_price_card() -> None:
    ledger = EvaluationLedger(provider="DeepSeek", model="test")
    call_id = ledger.reserve("narrator")
    ledger.record(
        request_id=call_id,
        agent="narrator",
        transport="json_object",
        elapsed_ms=120,
        usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        strict=True,
    )

    assert ledger.summary()["estimated_cost"] is None


def test_ledger_estimates_cost_and_stops_later_calls_at_cost_cap() -> None:
    price = PriceCard("2026-07-21", "USD", input_per_million=1.0, output_per_million=2.0)
    ledger = EvaluationLedger(
        provider="Agens",
        model="test",
        price_card=price,
        cost_limit=0.00003,
    )
    first = ledger.reserve("narrator")
    ledger.record(
        request_id=first,
        agent="narrator",
        transport="json_schema",
        elapsed_ms=100,
        usage={"prompt_tokens": 10, "completion_tokens": 10},
    )
    second = ledger.reserve("narrator")

    with pytest.raises(EvaluationBudgetExceeded, match="cost cap"):
        ledger.record(
            request_id=second,
            agent="narrator",
            transport="json_schema",
            elapsed_ms=100,
            usage={"prompt_tokens": 10, "completion_tokens": 10},
        )


def test_shared_budget_survives_multiple_ledgers_without_resetting_limits(tmp_path) -> None:
    budget = EvaluationBudget(
        tmp_path / "external-evidence",
        max_total_calls=2,
        max_narrator_calls=1,
    )
    first = EvaluationLedger(
        provider="Agens",
        model="test",
        shared_budget=budget,
    )
    second = EvaluationLedger(
        provider="DeepSeek",
        model="test",
        shared_budget=budget,
    )

    assert first.reserve("narrator") == "global-0001"
    assert second.reserve("judge") == "global-0002"
    with pytest.raises(EvaluationBudgetExceeded, match="provider request cap"):
        second.reserve("world_builder")

    assert budget.summary()["reserved_total"] == 2
    assert budget.summary()["reserved_narrator"] == 1


def test_configured_budget_root_reuses_existing_external_ledger(tmp_path, monkeypatch) -> None:
    existing = tmp_path / "prior-evidence"
    EvaluationBudget(existing, max_total_calls=2, max_narrator_calls=1)
    monkeypatch.setenv("AGENS_EVALUATION_BUDGET_ROOT", str(existing))

    assert evaluation_budget_root(tmp_path / "new-evidence") == existing.resolve()


def test_configured_budget_root_rejects_missing_ledger(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENS_EVALUATION_BUDGET_ROOT", str(tmp_path / "missing"))

    with pytest.raises(EvaluationBudgetExceeded, match="existing ledger"):
        evaluation_budget_root(tmp_path / "new-evidence")


def test_shared_budget_rejects_a_cost_before_the_next_dispatch(tmp_path) -> None:
    budget = EvaluationBudget(
        tmp_path / "external-evidence",
        max_total_calls=3,
        max_narrator_calls=3,
        hard_cost_limit=0.2,
    )
    ledger = EvaluationLedger(
        provider="Agens",
        model="test",
        reservation_cost=0.11,
        shared_budget=budget,
    )

    assert ledger.reserve("narrator") == "global-0001"
    with pytest.raises(EvaluationBudgetExceeded, match="cost cap"):
        ledger.reserve("narrator")


def test_shared_budget_upgrade_preserves_usage_and_records_the_authorization(tmp_path) -> None:
    budget = EvaluationBudget(tmp_path / "external-evidence", max_total_calls=2, max_narrator_calls=1)
    budget.reserve("narrator")

    summary = budget.upgrade_limits(
        max_total_calls=5,
        max_narrator_calls=4,
        reason="authorized_release_recovery",
    )

    assert summary["reserved_total"] == 1
    assert summary["reserved_narrator"] == 1
    assert summary["max_total_calls"] == 5
    assert budget.reserve("narrator") == "global-0002"
    with pytest.raises(EvaluationBudgetExceeded, match="only increase"):
        budget.upgrade_limits(max_total_calls=4, max_narrator_calls=4, reason="invalid")


def test_configured_limits_are_read_without_resetting_the_shared_budget(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_EVALUATION_MAX_TOTAL_CALLS", "950")
    monkeypatch.setenv("AGENS_EVALUATION_MAX_NARRATOR_CALLS", "850")

    assert configured_evaluation_limits() == (950, 850)
