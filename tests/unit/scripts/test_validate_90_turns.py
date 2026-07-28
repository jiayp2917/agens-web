from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "validate_90_turns",
    ROOT / "scripts" / "validate_90_turns.py",
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_v3_golden_route_reports_the_requested_content_version() -> None:
    result = runner.run_v3_scenario(scenario_key="high_steady", max_turns=90)

    assert result["story_version"] == 3
    assert result["turn_count"] == 90
    assert result["accepted_within_limit"] is True


@pytest.mark.parametrize(
    ("scenario_key", "expected_resolution"),
    (
        ("high_steady", "resolved"),
        ("low_risk", "failed"),
        ("middle_mixed", "resolved"),
    ),
)
def test_fixed_v3_scenarios_resolve_at_90_and_continue_in_post_arc(
    scenario_key: str,
    expected_resolution: str,
) -> None:
    at_resolution = runner.run_v3_scenario(scenario_key=scenario_key, max_turns=90)
    after_post_arc = runner.run_v3_scenario(scenario_key=scenario_key, max_turns=95)

    assert at_resolution["turn_count"] == 90
    assert at_resolution["trajectory_count"] == 90
    assert at_resolution["story_resolution"] == expected_resolution
    assert at_resolution["story_status"] == "post_arc"
    assert at_resolution["accepted_within_limit"] is True

    assert after_post_arc["turn_count"] == 95
    assert after_post_arc["trajectory_count"] == 95
    assert after_post_arc["story_resolution"] == expected_resolution
    assert after_post_arc["story_status"] == "post_arc"
    assert after_post_arc["accepted_within_limit"] is True
