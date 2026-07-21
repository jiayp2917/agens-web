"""Versioned contracts between input slots and authoritative turn rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SLOT_TO_CATEGORY = {
    "A": "稳妥",
    "B": "机遇",
    "C": "风险",
    "D": "气运",
}


@dataclass(frozen=True)
class ChoiceIntentV1:
    """The immutable rule meaning of one A/B/C/D player selection."""

    slot: str
    category: str
    action_text: str


@dataclass(frozen=True)
class RuleTurnOutcomeV1:
    """One rule-owned outcome generated before a Narrator invocation."""

    intent: ChoiceIntentV1
    state_delta: dict[str, Any]
    turn_summary: str

