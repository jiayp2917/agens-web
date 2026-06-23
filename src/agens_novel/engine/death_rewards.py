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

from ..game.constants import REALM_ORDER

log = logging.getLogger(__name__)


# ── Death categorization ─────────────────────────────────────────────────────

DEATH_BY_EVENT = "天命难违"
DEATH_BY_LIFESPAN = "寿元耗尽"
DEATH_BY_KARMA = "气运反噬"
DEATH_BY_PLAYER = "玩家结束本局"
DEATH_BY_FINALE = "飞升成仙"


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
    lifespan = max(0, getattr(session, "lifespan", 0))

    achievements: list[dict[str, str]] = []

    # Realm milestone achievements.
    try:
        realm_index = REALM_ORDER.index(realm)
    except ValueError:
        realm_index = 0
    if realm_index >= 1:
        achievements.append({
            "key": "foundation_established",
            "name": "筑基已成",
            "description": "本局角色突破至筑基境界。",
        })
    if realm_index >= 2:
        achievements.append({
            "key": "golden_core_forged",
            "name": "金丹凝成",
            "description": "本局角色凝出金丹。",
        })
    if realm_index >= 4:
        achievements.append({
            "key": "spirit_transformation",
            "name": "化神有成",
            "description": "本局角色踏入化神境界。",
        })

    # Stage milestone (练气层数).
    if realm == "练气" and realm_stage >= 6:
        achievements.append({
            "key": "qi_refinement_persistent",
            "name": "练气持恒",
            "description": "本局角色修至练气六层以上。",
        })

    # Longevity.
    if lifespan >= 80 and realm == "练气":
        achievements.append({
            "key": "long_lived_mortal",
            "name": "凡人长寿",
            "description": "本局角色以练气之身撑过八十载寿元。",
        })

    # Tenure (turn count).
    if turn_count >= 30:
        achievements.append({
            "key": "veteran_wanderer",
            "name": "历练已久",
            "description": "本局角色撑过三十回合红尘。",
        })

    # Inventory / techniques.
    if isinstance(inventory, list) and len(inventory) >= 5:
        achievements.append({
            "key": "well_stocked",
            "name": "行囊丰盈",
            "description": "本局收集到五种以上物品。",
        })
    if isinstance(techniques, list) and len(techniques) >= 3:
        achievements.append({
            "key": "polymath_cultivator",
            "name": "博学多艺",
            "description": "本局修习三种以上功法。",
        })

    # Exploration.
    if isinstance(discovered, list) and len(discovered) >= 5:
        achievements.append({
            "key": "explorer",
            "name": "足迹遍布",
            "description": "本局发现五处以上地点。",
        })

    # Ascension finale.
    if getattr(session, "finale", False):
        achievements.append({
            "key": "ascended",
            "name": "飞升证道",
            "description": "本局角色破界飞升，修真之路圆满。",
        })

    return achievements


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
    - attribute_points: added to the user's attribute pool (max single stat = 99)
    - extra_lifespan: added to the starting lifespan
    - legacy_talent: added to a `legacy_talents` list in the profile
    - opening_title: added to an `opening_titles` list in the profile
    """
    out = dict(profile)
    if not bonuses:
        return out

    attrs = dict(out.get("attributes", {}) or {})
    legacy_talents = list(out.get("legacy_talents", []) or [])
    opening_titles = list(out.get("opening_titles", []) or [])
    extra_lifespan = int(out.get("extra_lifespan", 0) or 0)

    for bonus in bonuses:
        btype = str(bonus.get("bonus_type") or "")
        bvalue = bonus.get("bonus_value")
        if btype == "attribute_points":
            # Add points distributed proportionally to the lowest stat.
            pool = int(bvalue or 0)
            distributed = 0
            while distributed < pool and attrs:
                lowest_key = min(attrs, key=lambda k: attrs.get(k, 0))
                if attrs[lowest_key] >= 99:
                    break
                attrs[lowest_key] = min(99, attrs[lowest_key] + 1)
                distributed += 1
        elif btype == "extra_lifespan":
            extra_lifespan += int(bvalue or 0)
        elif btype == "legacy_talent":
            if bvalue and str(bvalue) not in legacy_talents:
                legacy_talents.append(str(bvalue))
        elif btype == "opening_title":
            if bvalue and str(bvalue) not in opening_titles:
                opening_titles.append(str(bvalue))

    out["attributes"] = attrs
    out["legacy_talents"] = legacy_talents
    out["opening_titles"] = opening_titles
    if extra_lifespan:
        out["extra_lifespan"] = extra_lifespan
    return out


def consume_legacy_bonus(bonus: dict[str, Any]) -> bool:
    """Decrement a legacy bonus's runs_remaining. Returns True if still active."""
    remaining = int(bonus.get("runs_remaining", 1) or 1)
    if remaining <= 1:
        return False
    bonus["runs_remaining"] = remaining - 1
    return True


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
    return f"{char_name}的修真之路暂告一段落。"