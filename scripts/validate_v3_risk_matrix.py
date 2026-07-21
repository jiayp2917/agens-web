"""Pure-rule v3 risk matrix for local gameplay validation."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agens_novel.engine.start_flow import apply_profile_session
from agens_novel.engine.story_catalog import opening_story_binding
from agens_novel.engine.turn_rules import settle_turn_outcome
from agens_novel.game.realm import RealmSystem
from agens_novel.session.game_session import GameSession

WORLD_KEYS = ("frontier", "clan", "ocean", "forest")
DIFFICULTIES = ("普通", "困难")
APTITUDES: dict[str, dict[str, int]] = {
    "high": {
        "root_bone": 8,
        "comprehension": 8,
        "luck": 6,
        "willpower": 3,
        "physique": 3,
        "soul": 2,
    },
    "medium": {
        "root_bone": 5,
        "comprehension": 5,
        "luck": 5,
        "willpower": 5,
        "physique": 5,
        "soul": 5,
    },
    "low": {
        "root_bone": 2,
        "comprehension": 2,
        "luck": 2,
        "willpower": 8,
        "physique": 8,
        "soul": 8,
    },
}
ROUTES = {"A": "稳妥", "C": "风险"}
TERMINALS = ("ascension", "death", "longevity", "main_success", "main_failure", "unresolved")


@dataclass(frozen=True)
class MatrixCase:
    world: str
    difficulty: str
    aptitude: str
    route: str
    seed: int

    @property
    def key(self) -> str:
        return "|".join((self.world, self.difficulty, self.aptitude, self.route))


def run_case(case: MatrixCase, *, max_turns: int = 90) -> dict[str, Any]:
    """Run one v3 rule-only scenario without an engine agent or a database."""
    session = GameSession()
    apply_profile_session(
        session,
        {
            "char_name": "矩阵验真者",
            "talent": "苦修",
            "spirit_root": "火灵根",
            "spirit_root_grade": "地",
            "family_background": "散修遗孤",
            "difficulty": case.difficulty,
            "attributes": APTITUDES[case.aptitude],
        },
    )
    session.run_seed = f"v3-risk|{case.key}|{case.seed}"
    session.rule_rng_counter = 0
    session.world_profile = {"world_key": case.world, "fate_hooks": ["苦修", "天命"]}
    binding = opening_story_binding(
        case.world,
        ["苦修", "天命"],
        content_version=3,
        run_seed=session.run_seed,
        character_name=session.char_name,
    )
    session.story_key = binding["story_key"]
    session.story_version = binding["story_version"]
    session.story_state = binding["story_state"]
    realm_system = RealmSystem()

    while session.turn_count < max_turns and not session.game_over:
        can_breakthrough, _reason = realm_system.can_attempt_breakthrough(session)
        if can_breakthrough:
            _settle_breakthrough(session, realm_system)
        else:
            _settle_choice(session, realm_system, case.route)

    terminal = _terminal_kind(session)
    return {
        "case": case.key,
        "seed": case.seed,
        "turn_count": session.turn_count,
        "terminal": terminal,
        "negative": terminal in {"death", "longevity", "main_failure"},
        "realm": session.realm,
        "story_resolution": str(session.story_state.get("arc_resolution") or ""),
    }


def run_matrix(*, seeds_per_group: int = 200, max_turns: int = 90) -> dict[str, Any]:
    """Run the fixed world/difficulty/aptitude/route matrix deterministically."""
    if seeds_per_group <= 0:
        raise ValueError("seeds_per_group must be positive")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for world in WORLD_KEYS:
        for difficulty in DIFFICULTIES:
            for aptitude in APTITUDES:
                for route in ROUTES:
                    cases = [
                        run_case(
                            MatrixCase(world, difficulty, aptitude, route, seed),
                            max_turns=max_turns,
                        )
                        for seed in range(seeds_per_group)
                    ]
                    grouped[cases[0]["case"]] = cases
    groups = [_group_summary(key, values) for key, values in sorted(grouped.items())]
    directional = _directional_summaries(grouped)
    return {
        "story_version": 3,
        "seeds_per_group": seeds_per_group,
        "max_turns": max_turns,
        "groups": groups,
        "directional": directional,
        "terminal_counts": dict(Counter(item["terminal"] for values in grouped.values() for item in values)),
    }


def assert_directional_risk(matrix: dict[str, Any]) -> None:
    """Enforce the planned 10pp directional gap with a positive paired CI."""
    if not any(matrix.get("terminal_counts", {}).get(kind, 0) for kind in ("main_success", "ascension")):
        raise AssertionError("risk matrix produced no successful outcome")
    if not any(
        matrix.get("terminal_counts", {}).get(kind, 0)
        for kind in ("death", "longevity", "main_failure")
    ):
        raise AssertionError("risk matrix produced no negative outcome")
    for result in matrix.get("directional", []):
        if result["negative_rate_difference"] < 0.10:
            raise AssertionError(f"{result['comparison']} gap is below 10 percentage points")
        if result["paired_difference_ci95"][0] <= 0:
            raise AssertionError(f"{result['comparison']} paired CI does not establish a positive gap")


def _settle_choice(session: GameSession, realm_system: RealmSystem, route: str) -> None:
    session.turn_count += 1
    session.realm_turn_count += 1
    outcome = settle_turn_outcome(route, session)
    session.apply_delta(outcome.state_delta)
    if not session.game_over:
        stage_delta = realm_system.try_advance_stage(session)
        if stage_delta is not None:
            session.apply_delta(stage_delta)
    _advance_rng_counter(session)


def _settle_breakthrough(session: GameSession, realm_system: RealmSystem) -> None:
    delta = realm_system.attempt_breakthrough(session)
    session.turn_count += 1
    session.realm_turn_count += 1
    session.apply_delta(delta)
    _advance_rng_counter(session)


def _advance_rng_counter(session: GameSession) -> None:
    session.rule_rng_counter = max(0, int(session.rule_rng_counter or 0)) + 1


def _terminal_kind(session: GameSession) -> str:
    if session.finale:
        return "ascension"
    if session.game_over:
        reason = str(session.error or "")
        if "险境失手" in reason:
            return "death"
        if "寿" in reason or "坐化" in reason or "病衰" in reason:
            return "longevity"
        return "death"
    resolution = str(session.story_state.get("arc_resolution") or "")
    if resolution == "resolved":
        return "main_success"
    if resolution == "failed":
        return "main_failure"
    return "unresolved"


def _group_summary(key: str, values: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(item["terminal"] for item in values)
    total = len(values)
    negative = sum(1 for item in values if item["negative"])
    return {
        "case": key,
        "count": total,
        "terminals": {terminal: counts.get(terminal, 0) for terminal in TERMINALS},
        "negative_rate": negative / total,
        "negative_rate_wilson95": _wilson_interval(negative, total),
    }


def _directional_summaries(grouped: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    comparisons = {
        "higher_difficulty_than_normal": _paired_values(
            grouped,
            treatment=lambda world, _difficulty, aptitude, route: (world, "困难", aptitude, route),
            control=lambda world, _difficulty, aptitude, route: (world, "普通", aptitude, route),
            include=lambda _world, _difficulty, _aptitude, route: route == "A",
        ),
        "risk_route_c_than_steady_a": _paired_values(
            grouped,
            treatment=lambda world, difficulty, aptitude, _route: (world, difficulty, aptitude, "C"),
            control=lambda world, difficulty, aptitude, _route: (world, difficulty, aptitude, "A"),
        ),
        "low_aptitude_than_high": _paired_values(
            grouped,
            treatment=lambda world, difficulty, _aptitude, route: (world, difficulty, "low", route),
            control=lambda world, difficulty, _aptitude, route: (world, difficulty, "high", route),
            include=lambda _world, _difficulty, _aptitude, route: route == "A",
        ),
    }
    return [
        {
            "comparison": name,
            "negative_rate_difference": sum(values) / len(values),
            "paired_difference_ci95": _bootstrap_paired_ci(values),
            "pair_count": len(values),
        }
        for name, values in comparisons.items()
    ]


def _paired_values(
    grouped: dict[str, list[dict[str, Any]]],
    *,
    treatment: Callable[[str, str, str, str], tuple[str, str, str, str]],
    control: Callable[[str, str, str, str], tuple[str, str, str, str]],
    include: Callable[[str, str, str, str], bool] | None = None,
) -> list[int]:
    values: list[int] = []
    seen: set[tuple[tuple[str, str, str, str], tuple[str, str, str, str]]] = set()
    for world in WORLD_KEYS:
        for difficulty in DIFFICULTIES:
            for aptitude in APTITUDES:
                for route in ROUTES:
                    base = (world, difficulty, aptitude, route)
                    if include is not None and not include(*base):
                        continue
                    treated = treatment(*base)
                    controlled = control(*base)
                    pair = tuple(sorted((treated, controlled)))
                    if pair in seen:
                        continue
                    seen.add(pair)
                    treatment_cases = grouped["|".join(treated)]
                    control_cases = grouped["|".join(controlled)]
                    for left, right in zip(treatment_cases, control_cases, strict=True):
                        values.append(int(left["negative"]) - int(right["negative"]))
    return values


def _wilson_interval(successes: int, total: int) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    margin = z * ((proportion * (1 - proportion) / total + z * z / (4 * total * total)) ** 0.5)
    return [max(0.0, centre - margin / denominator), min(1.0, centre + margin / denominator)]


def _bootstrap_paired_ci(values: list[int], *, iterations: int = 2000) -> list[float]:
    if not values:
        return [0.0, 0.0]
    generator = random.Random(20260721)
    sample_size = len(values)
    means = sorted(
        sum(values[generator.randrange(sample_size)] for _ in range(sample_size)) / sample_size
        for _ in range(iterations)
    )
    lower = means[int((iterations - 1) * 0.025)]
    upper = means[int((iterations - 1) * 0.975)]
    return [lower, upper]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=200)
    parser.add_argument("--max-turns", type=int, default=90)
    parser.add_argument("--no-assert", action="store_true")
    args = parser.parse_args()
    result = run_matrix(seeds_per_group=args.seeds, max_turns=args.max_turns)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if not args.no_assert:
        assert_directional_risk(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
