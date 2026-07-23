"""Shared rule-outcome helper for focused gameplay-quality tests."""

from __future__ import annotations

from agens_novel.engine.rule_contracts import ChoiceIntentV1, RuleTurnOutcomeV1


def rule_outcome(rule_delta: dict) -> RuleTurnOutcomeV1:
    meta = rule_delta.get("meta") if isinstance(rule_delta, dict) else {}
    category = str(meta.get("choice_category") or "稳妥") if isinstance(meta, dict) else "稳妥"
    slot = {"稳妥": "A", "机遇": "B", "风险": "C", "气运": "D"}.get(category, "A")
    summary = str(meta.get("turn_summary") or "") if isinstance(meta, dict) else ""
    return RuleTurnOutcomeV1(ChoiceIntentV1(slot, category, ""), rule_delta, summary)
