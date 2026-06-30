"""Pure policies for ordinary-action deltas."""

from __future__ import annotations

import re
from typing import Any

from ..session.game_session import GameSession
from .choices import dedupe_strings

INCONSISTENT_NARRATIVE_NOTICE = "narrative/state mismatch: authoritative state change was missing structured data"
PLAYER_NARRATIVE_MISMATCH_NOTICE = "本回合以基础规则结算，传闻与收获尚未入册。"


_MEDITATION_KEYWORDS: tuple[str, ...] = (
    "闭关", "打坐", "吐纳", "静坐", "冥想", "静修", "参禅", "盘膝",
    "闭目", "运功", "运转", "吐故纳新", "吸纳", "静心", "修炼", "修行",
    "入定", "凝神", "冥思",
)

_ACTIVITY_KEYWORDS: tuple[str, ...] = (
    "剑法", "剑诀", "剑术", "刀法", "拳法", "掌法", "法术", "术法",
    "战斗", "杀敌", "攻击", "防御", "施展", "催动", "历练", "探索",
    "寻宝", "寻药", "买药", "购买", "交易", "谈话", "询问", "请教",
    "救人", "帮助", "炼丹", "炼器", "制符", "破阵", "师父", "师兄",
    "师姐", "长老", "掌门", "外出", "出门", "离开", "行走", "入城",
    "进入", "任务", "秘境", "坊市", "参悟", "悟道",
    "战", "斗", "敌", "妖", "兽", "寻", "药", "宝", "丹", "阵", "符",
)

_BREAKTHROUGH_FLAG_TRIGGERS: tuple[str, ...] = (
    "历练", "探索", "秘境", "机缘", "请教", "任务", "战斗", "切磋",
    "寻药", "炼丹", "炼器", "制符", "阵法", "法宝", "顿悟", "悟道",
    "雷劫", "渡劫", "护法", "护持", "丹", "药", "阵", "符", "宝",
)

_REALM_BREAKTHROUGH_FLAGS: dict[str, tuple[str, ...]] = {
    "练气": ("foundation_aid",),
    "筑基": ("golden_core_aid",),
    "金丹": ("nascent_soul_aid",),
    "元婴": ("spirit_transformation_aid",),
    "化神": ("unity_law_aid",),
    "合体": ("mahayana_vow_aid",),
    "大乘": ("tribulation_preparation",),
    "渡劫": ("tribulation_elixir", "ascension_protection"),
}

_CLAIM_RULES: tuple[tuple[tuple[re.Pattern[str], ...], tuple[tuple[str, str], ...]], ...] = (
    (
        (
            re.compile(r"(?:成功)?(?:突破|晋入|升至|迈入)(?:练气|筑基|金丹|元婴|化神|合体|大乘|渡劫|飞升)"),
            re.compile(r"踏入(?:练气|筑基|金丹|元婴|化神|合体|大乘|渡劫|飞升)"),
            re.compile(r"(?:修为|境界).{0,8}(?:提升|突破|精进|晋升)"),
            re.compile(r"(?:结成|凝成)金丹|元婴出窍|化神成功|飞升成仙"),
        ),
        (("character", "realm"), ("character", "realm_stage"), ("meta", "breakthrough_result")),
    ),
    (
        (
            re.compile(r"(?:奖励|发放|交给)(?:你|玩家|弟子)[^，。；\n]{0,24}"),
        ),
        (("character", "inventory_add"), ("character", "inventory")),
    ),
    (
        (
            re.compile(r"(?:你|玩家|弟子)?(?:习得|学会|参悟出)[^，。；\n]{0,24}"),
            re.compile(r"(?:领悟|传授)(?:了|你)?[^，。；\n]{0,24}(?:功法|术|诀|心法|剑法|法门)"),
        ),
        (("character", "techniques_add"), ("character", "techniques")),
    ),
    (
        (
            re.compile(r"发现(?:了)?(?:地点|秘境|洞府|遗迹|新地点|新地图|一处|一座)[^，。；\n]{0,24}"),
            re.compile(r"(?:抵达|来到)[^，。；\n]{0,24}(?:广场|殿|山门|药谷|秘境|洞府|遗迹|坊市|药圃)"),
        ),
        (("world", "discovered_add"), ("world", "location"), ("world", "current_scene")),
    ),
    (
        (
            re.compile(r"(?<!想)(?:接取|领取|接受|登记)(?:了|下)?[^，。；\n]{0,30}(?:任务|委托|悬赏)"),
        ),
        (("world", "active_quests_add"), ("world", "active_quests")),
    ),
)


def is_pure_cultivation(text: str) -> bool:
    """Return True if the typed action is pure meditation/cultivation."""
    compact = "".join(text.strip().lower().split())
    if not compact:
        return False
    has_meditation = any(kw in compact for kw in _MEDITATION_KEYWORDS)
    if not has_meditation:
        return False
    has_activity = any(kw in compact for kw in _ACTIVITY_KEYWORDS)
    return not has_activity


def apply_breakthrough_flag_rule(
    text: str,
    delta: dict[str, Any],
    *,
    is_cultivation: bool,
    session: GameSession,
) -> dict[str, Any]:
    """Let meaningful deeds earn lightweight breakthrough preparation flags."""
    if is_cultivation or not isinstance(delta, dict):
        return delta
    compact = "".join(text.strip().lower().split())
    if not any(keyword in compact for keyword in _BREAKTHROUGH_FLAG_TRIGGERS):
        return delta
    flags = list(_REALM_BREAKTHROUGH_FLAGS.get(session.realm, ()))
    if not flags:
        return delta

    if session.realm == "渡劫":
        if any(word in compact for word in ("丹", "药", "寻药", "炼丹", "续命")):
            flags = ["tribulation_elixir"]
        elif any(word in compact for word in ("法宝", "阵", "符", "护身", "炼器", "制符", "阵法")):
            flags = ["ascension_protection"]

    char = delta.get("character")
    char = dict(char) if isinstance(char, dict) else {}
    existing = char.get("breakthrough_flags_add")
    merged: list[str] = []
    if isinstance(existing, str):
        merged.append(existing)
    elif isinstance(existing, list):
        merged.extend(item for item in existing if isinstance(item, str))
    merged.extend(flags)
    char["breakthrough_flags_add"] = dedupe_strings(merged)
    delta["character"] = char
    return delta


def validate_narrative_delta_consistency(narrative: str, delta: dict[str, Any]) -> tuple[bool, str]:
    """Detect obvious narrative claims that lack matching structured delta."""
    if not narrative.strip():
        if _has_visible_outcome_delta(delta):
            return False, INCONSISTENT_NARRATIVE_NOTICE
        return True, ""
    if not isinstance(delta, dict):
        return False, INCONSISTENT_NARRATIVE_NOTICE

    text = re.sub(r"\s+", "", narrative)
    for patterns, required_paths in _CLAIM_RULES:
        if not any(pattern.search(text) for pattern in patterns):
            continue
        if any(_has_path(delta, section, key) for section, key in required_paths):
            continue
        return False, INCONSISTENT_NARRATIVE_NOTICE
    return True, ""


def merge_rule_delta(
    model_delta: dict[str, Any], rule_delta: dict[str, Any]
) -> dict[str, Any]:
    """Merge authoritative rule-engine delta on top of model-generated delta.

    Rule engine owns: age, lifespan, game_over, game_over_reason, elapsed_years.
    Model owns: narrative text, choices, world enrichments (lore, npcs, quests).
    """
    if not isinstance(model_delta, dict):
        model_delta = {}
    if not isinstance(rule_delta, dict):
        return model_delta

    merged = dict(model_delta)

    # ── Character: rule engine authoritative for age, lifespan, and attributes.
    rule_char = rule_delta.get("character", {})
    if isinstance(rule_char, dict) and rule_char:
        merged_char = dict(merged.get("character", {}))

        for key in ("age", "lifespan"):
            if key in rule_char:
                merged_char[key] = rule_char[key]

        if "attributes" in rule_char:
            merged_char["attributes"] = rule_char["attributes"]
        merged["character"] = merged_char

    # ── Meta: rule engine authoritative for game-over and turn info ──
    rule_meta = rule_delta.get("meta", {})
    if isinstance(rule_meta, dict) and rule_meta:
        merged_meta = dict(merged.get("meta", {}))
        for key in ("game_over", "game_over_reason", "elapsed_years", "choice_category"):
            if key in rule_meta:
                merged_meta[key] = rule_meta[key]
        merged["meta"] = merged_meta

    return merged


def _has_path(delta: dict[str, Any], section: str, key: str) -> bool:
    part = delta.get(section)
    return isinstance(part, dict) and key in part


def _has_visible_outcome_delta(delta: dict[str, Any]) -> bool:
    """Return True when model delta grants visible outcomes without narration."""
    if not isinstance(delta, dict):
        return False
    visible_paths = (
        ("character", "inventory_add"),
        ("character", "techniques_add"),
        ("character", "status_effects_add"),
        ("world", "active_quests_add"),
        ("world", "discovered_add"),
        ("world", "npcs_present_add"),
        ("world", "lore_add"),
    )
    return any(_has_path(delta, section, key) for section, key in visible_paths)
