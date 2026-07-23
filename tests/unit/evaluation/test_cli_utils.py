"""Tests for pure evaluation CLI parsing helpers."""

from __future__ import annotations

import json

import pytest

from agens_novel.evaluation.cli_utils import environment_limit, load_price_card, number_or_none


def test_load_price_card_parses_optional_rates(tmp_path) -> None:
    path = tmp_path / "prices.json"
    path.write_text(
        json.dumps(
            {
                "effective_date": "2026-07-23",
                "currency": "CNY",
                "input_per_million": "1.5",
                "output_per_million": 2,
                "cached_input_per_million": None,
            }
        ),
        encoding="utf-8",
    )

    price_card = load_price_card(path)

    assert price_card is not None
    assert price_card.input_per_million == 1.5
    assert price_card.output_per_million == 2.0
    assert price_card.cached_input_per_million is None


def test_price_card_rejects_non_object_and_negative_rates(tmp_path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        load_price_card(path)
    with pytest.raises(ValueError, match="non-negative"):
        number_or_none(-0.1)


def test_environment_limit_uses_default_or_configured_value(monkeypatch) -> None:
    assert environment_limit("AGENS_TEST_LIMIT", 7) == 7
    monkeypatch.setenv("AGENS_TEST_LIMIT", "11")
    assert environment_limit("AGENS_TEST_LIMIT", 7) == 11
