from __future__ import annotations

import importlib.util
from pathlib import Path

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
