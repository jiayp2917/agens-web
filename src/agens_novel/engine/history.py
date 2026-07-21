"""Helpers for bounded, semantic narrator history."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

ACCEPTED_TURN_CONTEXT_VERSION = "accepted-turn-context-v1"


@dataclass(frozen=True)
class AcceptedTurnContextV1:
    """The non-authoritative continuity facts retained for one accepted turn."""

    choice_slot: str
    event_id: str
    motif: str
    rule_consequence_summary: str
    story_key: str
    story_version: int
    phase_beat: str
    contract_version: str
    choices: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["choices"] = list(self.choices)
        return data


def accepted_turn_context(
    session: Any,
    state_delta: dict[str, Any],
    choices: list[str],
) -> dict[str, Any]:
    """Project rule-owned continuity facts without retaining a full delta."""
    meta_value = state_delta.get("meta") if isinstance(state_delta, dict) else {}
    meta = meta_value if isinstance(meta_value, dict) else {}
    story_state = getattr(session, "story_state", {})
    state = story_state if isinstance(story_state, dict) else {}
    motifs = state.get("recent_motifs")
    motif = str(motifs[-1] or "") if isinstance(motifs, list) and motifs else ""
    normalized_choices = tuple(str(choice).strip() for choice in choices[:4] if str(choice).strip())
    return AcceptedTurnContextV1(
        choice_slot=str(meta.get("choice_slot") or "").strip(),
        event_id=str(meta.get("event_id") or "").strip(),
        motif=motif,
        rule_consequence_summary=str(meta.get("turn_summary") or "").strip(),
        story_key=str(getattr(session, "story_key", "") or "").strip(),
        story_version=_non_negative_int(getattr(session, "story_version", 0)),
        phase_beat=str(meta.get("story_beat") or "").strip(),
        contract_version=ACCEPTED_TURN_CONTEXT_VERSION,
        choices=normalized_choices,
    ).as_dict()


def render_history_entry(entry: dict[str, Any]) -> str:
    """Render one stored entry into provider-neutral prompt text.

    Pre-existing entries without ``accepted_turn_context`` retain their exact
    content so legacy tagged saves remain readable.
    """
    content = str(entry.get("content") or "").strip()
    raw_context = entry.get("accepted_turn_context")
    if not isinstance(raw_context, dict):
        return content
    context = _accepted_context(raw_context)
    if context is None:
        return content
    choice_text = "；".join(
        f"{slot}：{choice}"
        for slot, choice in zip(("A", "B", "C", "D"), context.choices, strict=False)
    )
    facts = [
        f"槽位{context.choice_slot}" if context.choice_slot else "",
        f"事件{context.event_id}" if context.event_id else "",
        f"主题{context.motif}" if context.motif else "",
        f"阶段{context.phase_beat}" if context.phase_beat else "",
        context.rule_consequence_summary,
        choice_text,
    ]
    summary = "；".join(item for item in facts if item)
    return f"{content}\n已接受回合：{summary}".strip()


def _accepted_context(value: dict[str, Any]) -> AcceptedTurnContextV1 | None:
    if value.get("contract_version") != ACCEPTED_TURN_CONTEXT_VERSION:
        return None
    choices_value = value.get("choices")
    choices = (
        tuple(str(choice).strip() for choice in choices_value if str(choice).strip())
        if isinstance(choices_value, (list, tuple))
        else ()
    )
    return AcceptedTurnContextV1(
        choice_slot=str(value.get("choice_slot") or "").strip(),
        event_id=str(value.get("event_id") or "").strip(),
        motif=str(value.get("motif") or "").strip(),
        rule_consequence_summary=str(value.get("rule_consequence_summary") or "").strip(),
        story_key=str(value.get("story_key") or "").strip(),
        story_version=_non_negative_int(value.get("story_version")),
        phase_beat=str(value.get("phase_beat") or "").strip(),
        contract_version=ACCEPTED_TURN_CONTEXT_VERSION,
        choices=choices,
    )


def _non_negative_int(value: Any) -> int:
    return max(0, value) if isinstance(value, int) and not isinstance(value, bool) else 0


def compact_chat_history(history: list[dict[str, Any]], *, max_entries: int = 20) -> list[dict[str, Any]]:
    """Keep opening context plus the most recent entries within ``max_entries``."""
    if len(history) <= max_entries:
        return history
    if max_entries <= 0:
        return []
    first = history[0]
    recent_count = max(0, max_entries - 1)
    recent = history[-recent_count:] if recent_count else []
    return [first, *recent]
