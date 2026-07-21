"""Coverage for the pure-rule v3 risk matrix driver."""

from __future__ import annotations

from scripts.validate_v3_risk_matrix import MatrixCase, run_case, run_matrix


def test_one_matrix_case_is_seed_reproducible() -> None:
    case = MatrixCase("forest", "普通", "medium", "A", 7)

    assert run_case(case) == run_case(case)


def test_small_v3_matrix_covers_all_groups_without_model_calls() -> None:
    result = run_matrix(seeds_per_group=2)

    assert result["story_version"] == 3
    assert len(result["groups"]) == 48
    assert sum(result["terminal_counts"].values()) == 96
    assert {item["comparison"] for item in result["directional"]} == {
        "higher_difficulty_than_normal",
        "risk_route_c_than_steady_a",
        "low_aptitude_than_high",
    }
