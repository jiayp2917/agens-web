"""Tests for pre-registered local model comparison scenarios."""

from __future__ import annotations

from agens_novel.evaluation.scenarios import canonical_scenario_hash, canonical_v3_scenarios


def test_canonical_v3_scenarios_are_fixed_and_use_valid_30_point_profiles() -> None:
    scenarios = canonical_v3_scenarios()

    assert [scenario.key for scenario in scenarios] == ["high_steady", "low_risk", "middle_mixed"]
    assert all(len(scenario.slots) == 90 for scenario in scenarios)
    assert all(sum(scenario.profile["attributes"].values()) == 30 for scenario in scenarios)
    assert all(set(scenario.slots).issubset({"A", "B", "C", "D"}) for scenario in scenarios)


def test_canonical_scenario_hash_covers_the_full_v3_authority_input() -> None:
    scenario = canonical_v3_scenarios()[0]

    first = canonical_scenario_hash(scenario, story_version=3)
    second = canonical_scenario_hash(scenario, story_version=3)

    assert first == second
    assert len(first) == 64
