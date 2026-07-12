"""Death rewards evaluation (P4).

After a run ends, this module evaluates the player's final state and produces:
- a list of achievements unlocked this run
- a list of persistent rewards granted to the account
- a compact run summary for the ending UI
- legacy bonuses that apply to the player's NEXT character

For guest sessions the same evaluation runs but DB-backed bonuses are
skipped at the service layer — guests see the summary but receive no
persistent rewards.
"""

from __future__ import annotations

import logging
from typing import Any

from ..game.constants import (
    ATTRIBUTE_MAX,
    REALM_ORDER,
    clamp_attribute_value,
    normalize_attribute_value,
)

log = logging.getLogger(__name__)


# ── Death categorization ─────────────────────────────────────────────────────

DEATH_BY_EVENT = "天命难违"
DEATH_BY_LIFESPAN = "寿元耗尽"
DEATH_BY_KARMA = "气运反噬"
DEATH_BY_PLAYER = "玩家结束本局"
DEATH_BY_FINALE = "飞升成仙"
END_BY_STORY = "主线收束"


def categorize_death(session: Any) -> str:
    """Classify how the run ended based on the final session state.

    Game-mode death causes (per §6):
    - finale > event_death/karma_death > lifespan > player
    - event_death: 斗法、禁地、心魔、天劫 etc.
    - karma_death: D气运 path extreme failure
    - No HP check — death events are decided by the rule engine.
    """
    if getattr(session, "finale", False):
        return DEATH_BY_FINALE
    if not getattr(session, "game_over", False):
        return ""
    story_state = getattr(session, "story_state", None)
    if isinstance(story_state, dict) and story_state.get("status") in {"resolved", "failed"}:
        return END_BY_STORY
    error = getattr(session, "error", "") or ""
    lifespan = getattr(session, "lifespan", 1)
    # Karma death: D气运 extreme failure.
    if "气运" in error or "karma" in error.lower():
        return DEATH_BY_KARMA
    # Event death: 斗法、禁地、心魔、天劫 etc.
    event_keywords = ("斗法", "禁地", "心魔", "天劫", "重伤", "走火入魔", "雷劫", "道消")
    if any(kw in error for kw in event_keywords):
        return DEATH_BY_EVENT
    if lifespan <= 0:
        return DEATH_BY_LIFESPAN
    if error == "玩家结束本局":
        return DEATH_BY_PLAYER
    return DEATH_BY_PLAYER


# ── Achievement evaluation ──────────────────────────────────────────────────

def evaluate_achievements(session: Any) -> list[dict[str, str]]:
    """Return a list of achievements unlocked during this run.

    Each achievement is a dict with keys: key, name, description.
    Achievement keys are stable identifiers — used as DB primary values.
    """
    realm = getattr(session, "realm", "练气")
    realm_stage = getattr(session, "realm_stage", 1)
    turn_count = getattr(session, "turn_count", 0)
    inventory = getattr(session, "inventory", []) or []
    techniques = getattr(session, "techniques", []) or []
    discovered = getattr(session, "discovered_locations", []) or []
    age = max(0, getattr(session, "age", 0))

    try:
        realm_index = REALM_ORDER.index(realm)
    except ValueError:
        realm_index = 0
    rules = (
        (realm_index >= 1, "foundation_established", "筑基已成", "本局角色突破至筑基境界。"),
        (realm_index >= 2, "golden_core_forged", "金丹凝成", "本局角色凝出金丹。"),
        (realm_index >= 4, "spirit_transformation", "化神有成", "本局角色踏入化神境界。"),
        (realm == "练气" and realm_stage >= 6, "qi_refinement_persistent", "练气持恒", "本局角色修至练气六层以上。"),
        (age >= 80 and realm == "练气", "long_lived_mortal", "凡人长寿", "本局角色以练气之身撑过八十载寿元。"),
        (turn_count >= 30, "veteran_wanderer", "历练已久", "本局角色撑过三十回合红尘。"),
        (isinstance(inventory, list) and len(inventory) >= 5, "well_stocked", "行囊丰盈", "本局收集到五种以上物品。"),
        (isinstance(techniques, list) and len(techniques) >= 3, "polymath_cultivator", "博学多艺", "本局修习三种以上功法。"),
        (isinstance(discovered, list) and len(discovered) >= 5, "explorer", "足迹遍布", "本局发现五处以上地点。"),
        (bool(getattr(session, "finale", False)), "ascended", "飞升证道", "本局角色破界飞升，修真之路圆满。"),
    )
    return [
        {"key": key, "name": name, "description": description}
        for matched, key, name, description in rules
        if matched
    ]


# ── Reward evaluation ───────────────────────────────────────────────────────

def compute_rewards(
    achievements: list[dict[str, str]],
    session: Any,
) -> list[dict[str, Any]]:
    """Translate this run's achievements into persistent rewards.

    Reward dict shape:
        type: bonus_type identifier ("attribute_points", "legacy_talent",
              "opening_title", "extra_lifespan")
        value: numeric/string value attached to the bonus
        label: short human-readable description for the UI
    """
    realm = getattr(session, "realm", "练气")
    try:
        realm_index = REALM_ORDER.index(realm)
    except ValueError:
        realm_index = 0

    rewards: list[dict[str, Any]] = []

    # Every registered run grants at least one attribute point.
    base_points = 1
    if realm_index >= 1:
        base_points += 1
    if realm_index >= 2:
        base_points += 1
    if getattr(session, "finale", False):
        base_points += 3

    rewards.append({
        "type": "attribute_points",
        "value": base_points,
        "label": f"下局可分配额外属性点 +{base_points}",
    })

    # Achievement-specific rewards.
    keys = {ach.get("key") for ach in achievements}
    if "ascended" in keys:
        rewards.append({
            "type": "opening_title",
            "value": "飞升者",
            "label": "下局可使用开局称号「飞升者」",
        })
        rewards.append({
            "type": "extra_lifespan",
            "value": 20,
            "label": "下局起始寿元 +20",
        })
    elif "golden_core_forged" in keys:
        rewards.append({
            "type": "extra_lifespan",
            "value": 10,
            "label": "下局起始寿元 +10",
        })
    elif "foundation_established" in keys:
        rewards.append({
            "type": "extra_lifespan",
            "value": 5,
            "label": "下局起始寿元 +5",
        })

    if "explorer" in keys:
        rewards.append({
            "type": "legacy_talent",
            "value": "游历之眼",
            "label": "下局天赋池新增「游历之眼」",
        })

    return rewards


# ── Legacy bonus representation ─────────────────────────────────────────────

def bonuses_to_legacy(rewards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert raw reward dicts into legacy_bonus rows for the rewards bridge.

    Each row carries the bonus type, the value to apply, and a
    runs_remaining counter (defaults to 1 — the bonus is consumed on
    the next character creation).
    """
    rows: list[dict[str, Any]] = []
    for reward in rewards:
        rows.append({
            "bonus_type": str(reward.get("type") or ""),
            "bonus_value": reward.get("value"),
            "label": str(reward.get("label") or ""),
            "runs_remaining": 1,
        })
    return rows


def apply_legacy_bonuses(
    profile: dict[str, Any],
    bonuses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply active legacy bonuses to a freshly-built character profile.

    Mutates a copy of profile in place and returns it.
    - attribute_points: added to the user's attribute pool (max single stat = 10)
    - extra_lifespan: added to the starting lifespan
    - legacy_talent: added to a `legacy_talents` list in the profile
    - opening_title: added to an `opening_titles` list in the profile
    """
    out = dict(profile)
    if not bonuses:
        return out

    attrs = {
        str(key): normalize_attribute_value(value)
        for key, value in dict(out.get("attributes", {}) or {}).items()
    }
    legacy_talents = list(out.get("legacy_talents", []) or [])
    opening_titles = list(out.get("opening_titles", []) or [])
    extra_lifespan = int(out.get("extra_lifespan", 0) or 0)

    for bonus in bonuses:
        btype = str(bonus.get("bonus_type") or "")
        bvalue = bonus.get("bonus_value")
        if btype == "attribute_points":
            _distribute_attribute_points(attrs, int(bvalue or 0))
        elif btype == "extra_lifespan":
            extra_lifespan += int(bvalue or 0)
        elif btype == "legacy_talent":
            _append_unique_bonus(legacy_talents, bvalue)
        elif btype == "opening_title":
            _append_unique_bonus(opening_titles, bvalue)

    out["attributes"] = attrs
    out["legacy_talents"] = legacy_talents
    out["opening_titles"] = opening_titles
    if extra_lifespan:
        out["extra_lifespan"] = extra_lifespan
    return out


def _distribute_attribute_points(attrs: dict[str, int], pool: int) -> None:
    distributed = 0
    while distributed < pool and attrs:
        lowest_key = min(attrs, key=lambda key: attrs.get(key, 0))
        if attrs[lowest_key] >= ATTRIBUTE_MAX:
            break
        attrs[lowest_key] = clamp_attribute_value(attrs[lowest_key] + 1)
        distributed += 1


def _append_unique_bonus(target: list[Any], value: Any) -> None:
    normalized = str(value) if value else ""
    if normalized and normalized not in target:
        target.append(normalized)


# ── Run summary ─────────────────────────────────────────────────────────────

def build_run_summary(
    session: Any,
    achievements: list[dict[str, str]],
    rewards: list[dict[str, Any]],
    death_cause: str,
) -> dict[str, Any]:
    """Assemble a compact ending summary for the UI."""
    realm = getattr(session, "realm", "练气")
    realm_stage = getattr(session, "realm_stage", 1)
    turn_count = getattr(session, "turn_count", 0)
    age = getattr(session, "age", 0)
    inventory_count = len(getattr(session, "inventory", []) or [])
    technique_count = len(getattr(session, "techniques", []) or [])
    discovered_count = len(getattr(session, "discovered_locations", []) or [])

    return {
        "death_cause": death_cause,
        "final_realm": realm,
        "final_stage": realm_stage,
        "turn_count": turn_count,
        "final_age": age,
        "inventory_count": inventory_count,
        "technique_count": technique_count,
        "discovered_count": discovered_count,
        "achievements": list(achievements),
        "rewards": list(rewards),
        "headline": _summary_headline(session, death_cause),
    }


def _summary_headline(session: Any, death_cause: str) -> str:
    """Return a single-sentence summary line for the ending UI."""
    char_name = getattr(session, "char_name", "") or "无名"
    realm = getattr(session, "realm", "练气")
    if death_cause == DEATH_BY_FINALE:
        return f"{char_name}破界飞升，修真之路圆满。"
    if death_cause == DEATH_BY_EVENT:
        return f"{char_name}遭逢劫数，{realm}之路止步于此。"
    if death_cause == DEATH_BY_KARMA:
        return f"{char_name}气运反噬，{realm}修为化为因果。"
    if death_cause == DEATH_BY_LIFESPAN:
        return f"{char_name}寿元耗尽，坐化而去，{realm}修为归于尘土。"
    if death_cause == DEATH_BY_PLAYER:
        return f"{char_name}主动退场，{realm}修为暂时封存。"
    if death_cause == END_BY_STORY:
        return f"{char_name}走完本局主线，{realm}之路留下定论。"
    return f"{char_name}的修真之路暂告一段落。"
