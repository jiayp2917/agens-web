"""Pure policies for ordinary-action deltas."""

from __future__ import annotations

import re
from typing import Any

from ..game.realm import RealmSystem
from ..session.game_session import GameSession
from .choices import dedupe_strings

INSIGHT_BASE_GAIN = 8
INCONSISTENT_NARRATIVE_NOTICE = "天道记录以状态栏为准：本回合叙事声明的收获缺少结构化记录，行动结果暂不生效。"


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

_CLAIM_RULES: tuple[tuple[tuple[str, ...], tuple[tuple[str, str], ...]], ...] = (
    (
        ("练气", "筑基", "金丹", "元婴", "化神", "合体", "大乘", "渡劫", "飞升", "突破成功", "升至", "晋入", "踏入"),
        (("character", "realm"), ("character", "realm_stage"), ("character", "experience")),
    ),
    (
        ("获得", "拾得", "捡到", "购买", "奖励", "收下", "得到"),
        (("character", "inventory_add"), ("character", "inventory"), ("character", "gold")),
    ),
    (
        ("习得", "学会", "领悟功法", "传授功法", "参悟出"),
        (("character", "techniques_add"), ("character", "techniques")),
    ),
    (
        ("发现地点", "发现秘境", "发现洞府", "发现遗迹", "新地点", "新地图", "抵达", "来到"),
        (("world", "discovered_add"), ("world", "location"), ("world", "current_scene")),
    ),
    (
        ("接取", "领取任务", "委托", "任务"),
        (("world", "active_quests_add"), ("world", "active_quests")),
    ),
)


def parse_delta_int(value: Any) -> int:
    """Parse an integer or signed string delta value."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


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


def apply_insight_rule(text: str, delta: dict[str, Any]) -> dict[str, Any]:
    """Enforce the insight gate on an action's state delta."""
    if not isinstance(delta, dict):
        return delta
    char = delta.get("character")
    char = dict(char) if isinstance(char, dict) else {}
    llm_insight = parse_delta_int(char.get("insight", 0))

    if is_pure_cultivation(text):
        char.pop("insight", None)
    else:
        total = INSIGHT_BASE_GAIN + max(0, llm_insight)
        char["insight"] = f"+{total}"

    delta["character"] = char
    return delta


def apply_cultivation_limit(
    delta: dict[str, Any],
    *,
    is_cultivation: bool,
    session: GameSession,
    realm_system: RealmSystem,
) -> dict[str, Any]:
    """Cap pure-cultivation XP so one meditation turn cannot skip the journey."""
    if not is_cultivation or not isinstance(delta, dict):
        return delta
    char = delta.get("character")
    if not isinstance(char, dict) or "experience" not in char:
        return delta
    cfg = realm_system.get_realm_config(session.realm)
    cap = max(5, min(session.experience_to_next, (cfg.experience_required if cfg else 100)))
    gained = parse_delta_int(char.get("experience", 0))
    if gained > cap:
        char = dict(char)
        char["experience"] = f"+{cap}"
        delta["character"] = char
    return delta


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
        return True, ""
    if not isinstance(delta, dict):
        return False, INCONSISTENT_NARRATIVE_NOTICE

    text = re.sub(r"\s+", "", narrative)
    for keywords, required_paths in _CLAIM_RULES:
        if not any(keyword in text for keyword in keywords):
            continue
        if any(_has_path(delta, section, key) for section, key in required_paths):
            continue
        return False, INCONSISTENT_NARRATIVE_NOTICE
    return True, ""


def _has_path(delta: dict[str, Any], section: str, key: str) -> bool:
    part = delta.get(section)
    return isinstance(part, dict) and key in part
