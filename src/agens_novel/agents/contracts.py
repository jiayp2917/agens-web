"""Versioned, provider-neutral agent result contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..engine.choices import normalize_choices


@dataclass(frozen=True)
class NarratorEnvelopeV1:
    """Player-visible prose plus exactly one label for every fixed slot."""

    narrative: str
    choices: tuple[str, str, str, str]

    @classmethod
    def from_values(cls, narrative: Any, choices: Any) -> NarratorEnvelopeV1 | None:
        text = str(narrative or "").strip()
        normalized = normalize_choices(choices)
        if not text or len(normalized) != 4:
            return None
        return cls(text, (normalized[0], normalized[1], normalized[2], normalized[3]))


@dataclass(frozen=True)
class WorldOpeningEnvelopeV1:
    """Opening flavor constrained to a preselected world/story binding."""

    opening_narrative: str
    chronicle_0_16: tuple[str, ...]
    initial_situation_16: str
    choices: tuple[str, str, str, str]

    @classmethod
    def from_payload(cls, payload: Any) -> WorldOpeningEnvelopeV1 | None:
        if not isinstance(payload, dict):
            return None
        opening = str(payload.get("opening_narrative") or "").strip()
        situation = str(
            payload.get("initial_situation_16") or payload.get("initial_situation") or ""
        ).strip()
        chronicle_value = payload.get("chronicle_0_16")
        chronicle = tuple(
            str(item).strip()
            for item in chronicle_value
            if str(item).strip()
        ) if isinstance(chronicle_value, list) else ()
        normalized = normalize_choices(payload.get("choices"))
        if not opening or not situation or len(chronicle) < 1 or len(normalized) != 4:
            return None
        return cls(
            opening,
            chronicle,
            situation,
            (normalized[0], normalized[1], normalized[2], normalized[3]),
        )


@dataclass(frozen=True)
class JudgeDecisionV1:
    """A diagnostic verdict; it intentionally carries no state delta."""

    approved: bool
    issue_codes: tuple[str, ...]
    rewrite_required: bool

    @classmethod
    def from_payload(cls, payload: Any) -> JudgeDecisionV1:
        data = payload if isinstance(payload, dict) else {}
        approved = data.get("approved") is True
        raw_codes = data.get("issue_codes")
        issue_codes = tuple(
            str(code).strip()
            for code in raw_codes
            if str(code).strip()
        ) if isinstance(raw_codes, list) else ()
        return cls(approved, issue_codes, bool(data.get("rewrite_required")))
