"""Pre-registered canonical scenarios for local model comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CanonicalScenarioV1:
    """A fixed character, rule seed, story binding, and slot strategy."""

    key: str
    world_key: str
    run_seed: str
    profile: dict[str, Any]
    slots: tuple[str, ...]


_HIGH_ATTRIBUTES = {
    "root_bone": 8,
    "comprehension": 8,
    "luck": 6,
    "willpower": 3,
    "physique": 3,
    "soul": 2,
}
_MEDIUM_ATTRIBUTES = {
    "root_bone": 5,
    "comprehension": 5,
    "luck": 5,
    "willpower": 5,
    "physique": 5,
    "soul": 5,
}
_LOW_ATTRIBUTES = {
    "root_bone": 2,
    "comprehension": 2,
    "luck": 2,
    "willpower": 8,
    "physique": 8,
    "soul": 8,
}


def canonical_v3_scenarios() -> tuple[CanonicalScenarioV1, ...]:
    """Return the three fixed routes declared before any provider run."""
    return (
        CanonicalScenarioV1(
            key="high_steady",
            world_key="frontier",
            run_seed="v3-eval-frontier-high-steady-000",
            profile=_profile("验真青", "普通", _HIGH_ATTRIBUTES),
            slots=("A",) * 90,
        ),
        CanonicalScenarioV1(
            key="low_risk",
            world_key="frontier",
            run_seed="v3-eval-frontier-low-risk-000",
            profile=_profile("验真赤", "普通", _LOW_ATTRIBUTES),
            slots=("C",) * 90,
        ),
        CanonicalScenarioV1(
            key="middle_mixed",
            world_key="ocean",
            run_seed="v3-eval-ocean-middle-mixed-017",
            profile=_profile("验真澜", "普通", _MEDIUM_ATTRIBUTES),
            slots=tuple("B" if turn % 3 else "D" for turn in range(1, 91)),
        ),
    )


def _profile(name: str, difficulty: str, attributes: dict[str, int]) -> dict[str, Any]:
    return {
        "char_name": name,
        "talent": "苦修",
        "spirit_root": "火灵根",
        "spirit_root_grade": "地",
        "family_background": "散修遗孤",
        "difficulty": difficulty,
        "attributes": dict(attributes),
    }
