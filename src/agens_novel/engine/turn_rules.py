"""Turn rule engine — authoritative numeric settlement per turn.

Model *only* polishes narrative and choice text. The rule engine decides:
- elapsed_years
- attribute changes
- lifespan/death checks
- breakthrough / death / opportunity outcomes
"""

from __future__ import annotations

import random
from typing import Any

from ..game.constants import REALM_LIFESPANS
from ..game.realm import breakthrough_blocking_effects, golden_breakthrough_flags
from ..rule_rng import RuleRng, rule_rng_for_session
from .event_catalog import event_summary, select_chronicle_event, stage_feedback_due
from .rule_contracts import SLOT_TO_CATEGORY, ChoiceIntentV1, RuleTurnOutcomeV1
from .story_catalog import story_turn_delta

# ── Realm → base years per turn ─────────────────────────────────────────────
# Higher realms mean longer time spans for each pivotal decision.

_REALM_YEAR_RANGES: dict[str, tuple[int, int]] = {
    "练气": (1, 3),
    "筑基": (1, 5),
    "金丹": (3, 10),
    "元婴": (5, 20),
    "化神": (10, 50),
    "合体": (20, 100),
    "大乘": (50, 200),
    "渡劫": (100, 500),
    "飞升": (0, 0),  # terminal
}

# ── Choice category → risk multiplier for elapsed years ─────────────────────

_CHOICE_CATEGORY_MAP: dict[str, str] = dict(SLOT_TO_CATEGORY)

_RISK_YEAR_MULTIPLIER: dict[str, float] = {
    "稳妥": 0.8,
    "机遇": 1.0,
    "风险": 1.5,
    "气运": 1.0,
}

# ── Choice → attribute impact ───────────────────────────────────────────────

_CHOICE_ATTRIBUTE_IMPACT: dict[str, dict[str, Any]] = {
    "稳妥": {
        "attributes": {"willpower": (0, 2), "comprehension": (0, 1)},
        "breakthrough_chance": 0.1,
    },
    "机遇": {
        "attributes": {"luck": (0, 2), "comprehension": (0, 2)},
        "breakthrough_chance": 0.05,
    },
    "风险": {
        "attributes": {"physique": (-2, 2), "willpower": (0, 3)},
        "breakthrough_chance": 0.15,
        "death_risk": 0.05,
    },
    "气运": {
        "attributes": {"luck": (-3, 5)},
        "breakthrough_chance": 0.08,
        "luck_driven": True,
    },
}


def classify_choice(text: str) -> str:
    """Map a player choice text to a category label (稳妥/机遇/风险/气运).

    Falls back to '机遇' for free-text actions that don't match A/B/C/D.
    """
    return choice_intent(text).category


def choice_intent(text: str) -> ChoiceIntentV1:
    """Return the fixed A/B/C/D semantics for a player-visible action."""
    raw = str(text or "").strip()
    if not raw:
        return ChoiceIntentV1("B", "机遇", raw)
    # Direct A/B/C/D letter
    upper = raw.upper()
    if upper in _CHOICE_CATEGORY_MAP and len(raw) == 1:
        return ChoiceIntentV1(upper, _CHOICE_CATEGORY_MAP[upper], raw)
    # Text starting with A/B/C/D marker
    for letter, category in _CHOICE_CATEGORY_MAP.items():
        if raw.startswith(letter) or raw.startswith(letter.lower()):
            return ChoiceIntentV1(letter, category, raw)
    for category in _CHOICE_CATEGORY_MAP.values():
        if (
            raw.startswith(category)
            or raw.startswith(f"【{category}】")
            or raw.startswith(f"{category}:")
            or raw.startswith(f"{category}：")
        ):
            slot = next(letter for letter, value in _CHOICE_CATEGORY_MAP.items() if value == category)
            return ChoiceIntentV1(slot, category, raw)
    # Default for free-text actions
    return ChoiceIntentV1("B", "机遇", raw)


def settle_turn(
    choice_text: str,
    session: Any,  # GameSession
    difficulty_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute authoritative numeric outcomes for one turn.

    Returns a state_delta dict compatible with GameSession.apply_delta().
    The caller should apply this delta to the session AFTER the model
    generates narrative (so narrative matches the rule outcome).

    Returns:
        dict with keys:
            character: state changes (age, attributes, etc.)
            world: world state changes (current_scene, lore_add, etc.)
            meta: game_over, game_over_reason, elapsed_years
            turn_summary: human-readable summary for model prompt
    """
    return settle_turn_outcome(choice_text, session, difficulty_config).state_delta


def settle_turn_outcome(
    choice_text: str,
    session: Any,
    difficulty_config: dict[str, Any] | None = None,
) -> RuleTurnOutcomeV1:
    """Generate a rule-owned outcome before Narrator or Judge is invoked."""
    intent = choice_intent(choice_text)
    category = intent.category
    difficulty = (difficulty_config or {}).get("name") or session.difficulty or "普通"
    rng = rule_rng_for_session(session)

    realm = session.realm or "练气"
    elapsed_years = _elapsed_years(realm, category, difficulty, rng)
    char_delta = _attribute_changes(category, rng)
    char_delta["age"] = f"+{elapsed_years}"
    recovered_effects = _steady_recovery_effects(session, category)
    if recovered_effects:
        char_delta["status_effects_remove"] = recovered_effects
    preparation_flags = [
        flag
        for flag in golden_breakthrough_flags(session)
        if flag not in getattr(session, "breakthrough_flags", [])
    ]
    if preparation_flags:
        char_delta["breakthrough_flags_add"] = preparation_flags
    new_age = session.age + elapsed_years
    remaining_lifespan, game_over_reason = _settle_lifespan(session, realm, new_age, char_delta)
    risk_death_reason = _risk_death_reason(session, category, difficulty, new_age, rng)
    if risk_death_reason:
        game_over_reason = risk_death_reason
    event = select_chronicle_event(session, category, new_age)
    if event.get("id") == "steady-merit-recognition":
        char_delta["title_add"] = ["外门勤修弟子"]
    story = story_turn_delta(session, category, event, new_age, game_over_reason)
    if not game_over_reason and story.get("story_status") in {"resolved", "failed"}:
        story_update = story.get("story_update")
        ending = (
            str(story_update.get("ending") or "").strip() if isinstance(story_update, dict) else ""
        )
        game_over_reason = ending or str(story.get("story_beat") or "主线尘埃落定。").strip()
    game_over = bool(game_over_reason)
    turn_summary = _turn_summary(
        session.age,
        new_age,
        category,
        elapsed_years,
        remaining_lifespan,
        recovered_effects,
        event,
        story,
        preparation_flags,
        game_over_reason,
    )
    world_delta = _stage_feedback_delta(session, event, story)
    if preparation_flags:
        world_delta.setdefault("lore_add", []).append(
            f"{realm}阶段的长期积累已经兑现，下一境界所需的护持与机缘已齐备。"
        )

    # ── Build state_delta ──
    state_delta: dict[str, Any] = {
        "character": char_delta,
        "world": world_delta,
        "meta": {
            "elapsed_years": elapsed_years,
            "choice_slot": intent.slot,
            "choice_category": category,
            "event_id": event.get("id", ""),
            "event_type": event.get("event_type", ""),
            "event_lore": event.get("lore", ""),
            "stage_goal": event.get("stage_goal", ""),
            "allowed_delta_types": event.get("allowed_delta_types", []),
            "story_phase": story.get("story_phase", ""),
            "story_goal": story.get("story_goal", ""),
            "story_beat": story.get("story_beat", ""),
            "story_status": story.get("story_status", ""),
            "breakthrough_preparation": preparation_flags,
            "turn_summary": turn_summary,
            "risk_death": bool(risk_death_reason),
        },
    }

    if game_over:
        state_delta["meta"]["game_over"] = True
        state_delta["meta"]["game_over_reason"] = game_over_reason

    return RuleTurnOutcomeV1(intent, state_delta, turn_summary)


def _elapsed_years(
    realm: str, category: str, difficulty: str, rng: RuleRng | None
) -> int:
    year_min, year_max = _REALM_YEAR_RANGES.get(realm, (1, 3))
    difficulty_multiplier = {"简单": 0.7, "困难": 1.3}.get(difficulty, 1.0)
    base_years = (
        rng.randint(year_min, year_max, "elapsed_years")
        if rng is not None
        else random.randint(year_min, year_max)
    )
    return max(
        1, int(base_years * _RISK_YEAR_MULTIPLIER.get(category, 1.0) * difficulty_multiplier)
    )


def _attribute_changes(category: str, rng: RuleRng | None) -> dict[str, Any]:
    impact = _CHOICE_ATTRIBUTE_IMPACT.get(category, _CHOICE_ATTRIBUTE_IMPACT["机遇"])
    changes = {
        attr: change
        for attr, (low, high) in impact.get("attributes", {}).items()
        if (
            change := (
                rng.randint(low, high, f"attribute:{attr}")
                if rng is not None
                else random.randint(low, high)
            )
        )
        != 0
    }
    return {"attributes": changes} if changes else {}


def _settle_lifespan(
    session: Any, realm: str, new_age: int, char_delta: dict[str, Any]
) -> tuple[int, str]:
    lifespan_cap = int(getattr(session, "lifespan", 0) or get_realm_lifespan(realm))
    remaining = lifespan_cap - new_age
    if remaining <= 0 and session.realm != "飞升":
        return remaining, "寿元耗尽，坐化而去。"
    pressure = _low_realm_age_pressure(session, new_age)
    if not pressure:
        return remaining, ""
    lifespan_delta = int(pressure.get("lifespan_delta") or 0)
    if lifespan_delta:
        char_delta["lifespan"] = f"{lifespan_delta:+d}"
        remaining = max(1, lifespan_cap + lifespan_delta) - new_age
    if pressure.get("status_effect"):
        char_delta["status_effects_add"] = [pressure["status_effect"]]
    reason = str(pressure.get("game_over_reason") or "寿元耗尽，坐化而去。")
    return (remaining, reason) if remaining <= 0 else (remaining, "")


def _risk_death_reason(
    session: Any,
    category: str,
    difficulty: str,
    new_age: int,
    rng: RuleRng | None,
) -> str:
    """Resolve seeded v3 adversity without changing legacy snapshots."""
    if rng is None or int(getattr(session, "story_version", 0) or 0) != 3:
        return ""
    attributes = getattr(session, "attributes", {})
    aptitude = (
        sum(int(attributes.get(key) or 0) for key in ("root_bone", "comprehension", "luck"))
        if isinstance(attributes, dict)
        else 0
    )
    risk_route = category == "风险"
    chance = 0.008 if risk_route else 0.0
    if difficulty == "困难":
        chance += 0.012 if risk_route else 0.003
    chance += max(0, 12 - aptitude) * 0.004
    lifespan = max(1, int(getattr(session, "lifespan", 100) or 100))
    age_pressure = max(0.0, new_age / lifespan - 0.65)
    chance += age_pressure * (0.02 if risk_route else 0.006)
    if chance <= 0:
        return ""
    if rng.random("risk_death") >= min(0.12, chance):
        return ""
    if risk_route:
        return "险境失手，伤势未及挽回而身死道消。"
    return "时局艰险，旧患叠加而身死道消。"


def _turn_summary(
    start_age: int,
    end_age: int,
    category: str,
    elapsed_years: int,
    remaining_lifespan: int,
    recovered_effects: list[str],
    event: dict[str, Any],
    story: dict[str, Any],
    preparation_flags: list[str],
    game_over_reason: str,
) -> str:
    summary = (
        f"本回合类别：{category}；时间流逝：{elapsed_years}年；"
        f"角色年龄：{start_age}→{end_age}岁；剩余寿元：{max(0, remaining_lifespan)}年。"
    )
    if recovered_effects:
        summary += f" 稳妥调息已解除：{'、'.join(recovered_effects)}。"
    if event_text := event_summary(event):
        summary += f" {event_text}"
    story_phase = str(story.get("story_phase") or "").strip()
    story_goal = str(story.get("story_goal") or "").strip()
    story_beat = str(story.get("story_beat") or "").strip()
    if story_phase and story_goal:
        summary += f" 主线阶段：{story_phase}；当前目标：{story_goal}。"
    if story_beat:
        summary += f" 本轮主线兑现：{story_beat}"
    if preparation_flags:
        summary += " 本轮阶段事件已兑现下一境界所需的护持与机缘。"
    if game_over_reason:
        summary += f" 结局：{game_over_reason}"
    return summary


def _steady_recovery_effects(session: Any, category: str) -> list[str]:
    """A steady ordinary turn deterministically clears breakthrough backlash."""
    if category != "稳妥":
        return []
    return breakthrough_blocking_effects(getattr(session, "status_effects", []))


def get_realm_lifespan(realm: str) -> int:
    """Return the base lifespan for a given realm."""
    return REALM_LIFESPANS.get(realm, 100)


def _stage_feedback_delta(
    session: Any, event: dict[str, Any], story: dict[str, Any]
) -> dict[str, Any]:
    """Emit lightweight chronicle/world feedback every few turns."""
    world_delta: dict[str, Any] = {}
    story_update = story.get("story_update")
    if isinstance(story_update, dict):
        world_delta["story_update"] = story_update
    story_terminal = str(story.get("story_status") or "") in {"failed", "resolved"}
    if not event or (not stage_feedback_due(session) and not story_terminal):
        return world_delta
    lore = [
        str(item).strip()
        for item in (event.get("lore"), story.get("story_beat"))
        if str(item or "").strip()
    ]
    if lore:
        world_delta["lore_add"] = list(dict.fromkeys(lore))
    return world_delta


def _low_realm_age_pressure(session: Any, new_age: int) -> dict[str, Any]:
    """Apply aging pressure when a Qi Refining run stalls for decades."""
    if getattr(session, "realm", "练气") != "练气":
        return {}
    stage = int(getattr(session, "realm_stage", 1) or 1)
    if new_age >= 90 and stage < 9:
        return {
            "lifespan_delta": -15,
            "status_effect": "病衰",
            "game_over_reason": "年岁已高，根基未成，病衰坐化。",
        }
    if new_age >= 70 and stage < 9:
        return {"lifespan_delta": -8, "status_effect": "气血衰败"}
    if new_age >= 50 and stage < 6:
        return {"lifespan_delta": -4, "status_effect": "瓶颈衰相"}
    return {}
