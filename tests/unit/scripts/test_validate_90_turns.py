"""Golden-route validation driver coverage."""

from __future__ import annotations

from scripts.validate_90_turns import run_golden_route


def test_golden_route_reaches_ascension_within_ninety_turns() -> None:
    result = run_golden_route(seed="agens-golden-169")

    assert result["story_version"] == 2
    assert result["ascended_within_limit"] is True
    assert result["turn_count"] <= 90
    assert [item["realm"] for item in result["checkpoints"]] == [
        "筑基",
        "金丹",
        "元婴",
        "化神",
        "合体",
        "大乘",
        "渡劫",
        "飞升",
    ]
