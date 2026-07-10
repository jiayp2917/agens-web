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
from .event_catalog import event_summary, select_chronicle_event, stage_feedback_due

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

_CHOICE_CATEGORY_MAP: dict[str, str] = {
    "A": "稳妥",
    "B": "机遇",
    "C": "风险",
    "D": "气运",
}

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
    raw = text.strip()
    if not raw:
        return "机遇"
    # Direct A/B/C/D letter
    upper = raw.upper()
    if upper in _CHOICE_CATEGORY_MAP and len(raw) == 1:
        return _CHOICE_CATEGORY_MAP[upper]
    # Text starting with A/B/C/D marker
    for letter, category in _CHOICE_CATEGORY_MAP.items():
        if raw.startswith(letter) or raw.startswith(letter.lower()):
            return category
    for category in _CHOICE_CATEGORY_MAP.values():
        if (
            raw.startswith(category)
            or raw.startswith(f"【{category}】")
            or raw.startswith(f"{category}:")
            or raw.startswith(f"{category}：")
        ):
            return category
    # Default for free-text actions
    return "机遇"


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
    category = classify_choice(choice_text)
    difficulty = (difficulty_config or {}).get("name") or session.difficulty or "普通"

    realm = session.realm or "练气"
    elapsed_years = _elapsed_years(realm, category, difficulty)
    char_delta = _attribute_changes(category)
    char_delta["age"] = f"+{elapsed_years}"
    new_age = session.age + elapsed_years
    remaining_lifespan, game_over_reason = _settle_lifespan(session, realm, new_age, char_delta)
    game_over = bool(game_over_reason)
    event = select_chronicle_event(session, category, new_age)
    turn_summary = _turn_summary(
        session.age, new_age, category, elapsed_years, remaining_lifespan, event, game_over_reason
    )
    world_delta = _stage_feedback_delta(session, event)

    # ── Build state_delta ──
    state_delta: dict[str, Any] = {
        "character": char_delta,
        "world": world_delta,
        "meta": {
            "elapsed_years": elapsed_years,
            "choice_category": category,
            "event_id": event.get("id", ""),
            "event_type": event.get("event_type", ""),
            "event_lore": event.get("lore", ""),
            "stage_goal": event.get("stage_goal", ""),
            "allowed_delta_types": event.get("allowed_delta_types", []),
            "turn_summary": turn_summary,
        },
    }

    if game_over:
        state_delta["meta"]["game_over"] = True
        state_delta["meta"]["game_over_reason"] = game_over_reason

    return state_delta


def _elapsed_years(realm: str, category: str, difficulty: str) -> int:
    year_min, year_max = _REALM_YEAR_RANGES.get(realm, (1, 3))
    difficulty_multiplier = {"简单": 0.7, "困难": 1.3}.get(difficulty, 1.0)
    base_years = random.randint(year_min, year_max)
    return max(1, int(base_years * _RISK_YEAR_MULTIPLIER.get(category, 1.0) * difficulty_multiplier))


def _attribute_changes(category: str) -> dict[str, Any]:
    impact = _CHOICE_ATTRIBUTE_IMPACT.get(category, _CHOICE_ATTRIBUTE_IMPACT["机遇"])
    changes = {
        attr: change
        for attr, (low, high) in impact.get("attributes", {}).items()
        if (change := random.randint(low, high)) != 0
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


def _turn_summary(
    start_age: int,
    end_age: int,
    category: str,
    elapsed_years: int,
    remaining_lifespan: int,
    event: dict[str, Any],
    game_over_reason: str,
) -> str:
    summary = (
        f"本回合类别：{category}；时间流逝：{elapsed_years}年；"
        f"角色年龄：{start_age}→{end_age}岁；剩余寿元：{max(0, remaining_lifespan)}年。"
    )
    if event_text := event_summary(event):
        summary += f" {event_text}"
    if game_over_reason:
        summary += f" 结局：{game_over_reason}"
    return summary


def get_realm_lifespan(realm: str) -> int:
    """Return the base lifespan for a given realm."""
    return REALM_LIFESPANS.get(realm, 100)


def _stage_feedback_delta(session: Any, event: dict[str, Any]) -> dict[str, Any]:
    """Emit lightweight chronicle/world feedback every few turns."""
    if not event or not stage_feedback_due(session):
        return {}
    lore = str(event.get("lore") or "").strip()
    return {"lore_add": [lore]} if lore else {}


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
