"""Tests for local evaluation accounting and request caps."""

from __future__ import annotations

import pytest

from agens_novel.evaluation.ledger import (
    EvaluationBudgetExceeded,
    EvaluationLedger,
    PriceCard,
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
