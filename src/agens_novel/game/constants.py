"""Game constants for the xianxia cultivation simulator.

Defines realm progression, spirit root types, rarity levels, and equipment
slot configuration.  All constants are module-level for easy import.
"""

from __future__ import annotations

from typing import Any

from .fate_content import entries_for
from .spirit_roots import spirit_root_rule_rows

# ─────────────────────────────────────────────────────────────────────────────
# Gameplay / character creation constants
# ─────────────────────────────────────────────────────────────────────────────

TALENT_OPTIONS: list[str] = [
    "平平无奇",
    "草木亲和",
    "剑心微明",
    "惊雷骨",
    "天命道胎",
] + [entry.name for entry in entries_for("talent")]

FAMILY_BACKGROUNDS: list[str] = [
    "农家",
    "寒门",
    "小族",
    "宗门旁支",
    "隐世仙族",
] + [entry.name for entry in entries_for("family")]

DIFFICULTY_OPTIONS: list[str] = ["简单", "普通", "困难"]

LUCK_LEVELS: list[str] = ["低迷", "平稳", "中上", "起伏", "天眷"]

ATTRIBUTE_KEYS: list[str] = ["root_bone", "comprehension", "luck", "willpower", "physique", "soul"]

ATTRIBUTE_LABELS: dict[str, str] = {
    "root_bone": "根骨",
    "comprehension": "悟性",
    "luck": "气运",
    "willpower": "心性",
    "physique": "体魄",
    "soul": "神魂",
}

ATTRIBUTE_MIN: int = 0
ATTRIBUTE_MAX: int = 10
ATTRIBUTE_DEFAULT: int = 5
ATTRIBUTE_TOTAL: int = 30

DEFAULT_ATTRIBUTES: dict[str, int] = {key: ATTRIBUTE_DEFAULT for key in ATTRIBUTE_KEYS}


def clamp_attribute_value(value: Any, *, default: int = ATTRIBUTE_DEFAULT) -> int:
    """Clamp a v5 gameplay attribute to the public 0-10 scale."""
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(ATTRIBUTE_MIN, min(ATTRIBUTE_MAX, number))


def normalize_attribute_value(value: Any, *, default: int = ATTRIBUTE_DEFAULT) -> int:
    """Normalize new 0-10 values and legacy 0-100 values to the v5 scale."""
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= ATTRIBUTE_MAX:
        return clamp_attribute_value(number, default=default)
    legacy = max(0, min(100, number))
    return clamp_attribute_value((legacy + 5) // 10, default=default)

# ─────────────────────────────────────────────────────────────────────────────
# Realm system
# ─────────────────────────────────────────────────────────────────────────────

# 9 realms: first 5 fully implemented, last 4 reserved for future expansion.
REALM_ORDER: list[str] = [
    "练气", "筑基", "金丹", "元婴", "化神",     # 首版实现
    "合体", "大乘", "渡劫", "飞升",             # 预留
]

REALM_LIFESPANS: dict[str, int] = {
    "练气": 100,
    "筑基": 200,
    "金丹": 500,
    "元婴": 1000,
    "化神": 2000,
    "合体": 4000,
    "大乘": 5000,
    "渡劫": 6000,
    "飞升": 9999,
}

REALM_LIFESPAN_RANGES: dict[str, tuple[int, int]] = {
    "练气": (80, 120),
    "筑基": (160, 240),
    "金丹": (400, 600),
    "元婴": (800, 1200),
    "化神": (1600, 2400),
    "合体": (3200, 4800),
    "大乘": (4200, 5800),
    "渡劫": (5200, 6800),
    "飞升": (9999, 9999),
}

# Realm configuration: each realm's stage count and breakthrough gates.
REALM_CONFIGS: dict[str, dict[str, Any]] = {
    "练气": {
        "name": "练气",
        "lifespan": REALM_LIFESPANS["练气"],
        "stages": 9,
        "breakthrough_requirements": [
            {"key": "foundation_aid", "label": "筑基丹、师门护持或筑基机缘"},
        ],
        "breakthrough_base_rate": 0.80,
        "spirit_root_bonus": {
            "天": 0.10,
            "地": 0.05,
        },
    },
    "筑基": {
        "name": "筑基",
        "lifespan": REALM_LIFESPANS["筑基"],
        "stages": 4,
        "breakthrough_requirements": [
            {"key": "golden_core_aid", "label": "结金丹、凝丹机缘或金丹法门"},
        ],
        "breakthrough_base_rate": 0.60,
        "spirit_root_bonus": {
            "天": 0.10,
            "地": 0.05,
        },
    },
    "金丹": {
        "name": "金丹",
        "lifespan": REALM_LIFESPANS["金丹"],
        "stages": 4,
        "breakthrough_requirements": [
            {"key": "nascent_soul_aid", "label": "化婴丹、生死顿悟或元婴护法"},
        ],
        "breakthrough_base_rate": 0.45,
        "spirit_root_bonus": {
            "天": 0.10,
            "地": 0.05,
        },
    },
    "元婴": {
        "name": "元婴",
        "lifespan": REALM_LIFESPANS["元婴"],
        "stages": 4,
        "breakthrough_requirements": [
            {"key": "spirit_transformation_aid", "label": "神魂试炼、心魔明悟或化神契机"},
        ],
        "breakthrough_base_rate": 0.30,
        "spirit_root_bonus": {
            "天": 0.10,
            "地": 0.05,
        },
    },
    "化神": {
        "name": "化神",
        "lifespan": REALM_LIFESPANS["化神"],
        "stages": 4,
        "breakthrough_requirements": [
            {"key": "unity_law_aid", "label": "天地法则契机或合体道基"},
        ],
        "breakthrough_base_rate": 0.20,
        "spirit_root_bonus": {
            "天": 0.10,
            "地": 0.05,
        },
    },
    # ── Reserved realms (data only, no gameplay logic yet) ──
    "合体": {
        "name": "合体",
        "lifespan": REALM_LIFESPANS["合体"],
        "stages": 4,
        "breakthrough_requirements": [
            {"key": "mahayana_vow_aid", "label": "宏愿因果、宗门气运或大乘道果"},
        ],
        "breakthrough_base_rate": 0.15,
        "spirit_root_bonus": {
            "天": 0.10,
            "地": 0.05,
        },
    },
    "大乘": {
        "name": "大乘",
        "lifespan": REALM_LIFESPANS["大乘"],
        "stages": 4,
        "breakthrough_requirements": [
            {"key": "tribulation_preparation", "label": "雷劫情报、避劫阵基或渡劫场地"},
        ],
        "breakthrough_base_rate": 0.10,
        "spirit_root_bonus": {
            "天": 0.10,
            "地": 0.05,
        },
    },
    "渡劫": {
        "name": "渡劫",
        "lifespan": REALM_LIFESPANS["渡劫"],
        "stages": 4,
        "breakthrough_requirements": [
            {"key": "tribulation_elixir", "label": "渡劫丹或同等续命丹药"},
            {"key": "ascension_protection", "label": "护身法宝、雷劫阵法或替劫符箓"},
        ],
        "breakthrough_base_rate": 0.05,
        "spirit_root_bonus": {
            "天": 0.10,
            "地": 0.05,
        },
    },
    "飞升": {
        "name": "飞升",
        "lifespan": REALM_LIFESPANS["飞升"],
        "stages": 1,
        "breakthrough_requirements": [],
        "breakthrough_base_rate": 0.00,
        "spirit_root_bonus": {},
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Spirit roots
# ─────────────────────────────────────────────────────────────────────────────

SPIRIT_ROOTS: list[dict[str, Any]] = spirit_root_rule_rows()

# Quick lookup by name.
SPIRIT_ROOT_MAP: dict[str, dict[str, Any]] = {sr["name"]: sr for sr in SPIRIT_ROOTS}

# Spirit root grade names for display.
SPIRIT_ROOT_GRADES: list[str] = ["天", "地", "玄", "黄"]

# ─────────────────────────────────────────────────────────────────────────────
# Catalog rarity tiers (白绿蓝紫橙红) for talents, family backgrounds, spirit roots
# ─────────────────────────────────────────────────────────────────────────────

# Random pool always includes 白绿蓝; 红 requires 1 run to appear in random.
# Self-select: ≤蓝 always; 紫 after 1 run; 橙 after 1 飞升; 红 after 2 飞升.
# Weights sum to 200 for normalization.

CATALOG_RARITY_TIERS: list[dict[str, Any]] = [
    {"key": "白", "label": "白色", "weight": 90, "select_requires_runs": 0, "select_requires_ascensions": 0, "random_requires_runs": 0},
    {"key": "绿", "label": "绿色", "weight": 60, "select_requires_runs": 0, "select_requires_ascensions": 0, "random_requires_runs": 0},
    {"key": "蓝", "label": "蓝色", "weight": 30, "select_requires_runs": 0, "select_requires_ascensions": 0, "random_requires_runs": 0},
    {"key": "紫", "label": "紫色", "weight": 14, "select_requires_runs": 1, "select_requires_ascensions": 0, "random_requires_runs": 0},
    {"key": "橙", "label": "橙色", "weight": 5, "select_requires_runs": 0, "select_requires_ascensions": 1, "random_requires_runs": 0},
    {"key": "红", "label": "红色", "weight": 1, "select_requires_runs": 0, "select_requires_ascensions": 2, "random_requires_runs": 1},
]


def rarity_unlocked_for(runs_completed: int, ascension_count: int, *,
                        for_random: bool = False) -> list[str]:
    """Return the rarity keys the player may select (or roll) given progress.

    Spec §11 unlock gates:
    - 紫 requires 1 completed run (select) / — (random).
    - 橙 requires 1 ascension.
    - 红 requires 2 ascensions + 1 run for the random pool.
    """
    unlocked: list[str] = []
    for tier in CATALOG_RARITY_TIERS:
        need_runs = tier["random_requires_runs"] if for_random else tier["select_requires_runs"]
        need_asc = tier["select_requires_ascensions"]
        if runs_completed >= need_runs and ascension_count >= need_asc:
            unlocked.append(tier["key"])
    return unlocked


def realm_lifespan_range(realm: str) -> tuple[int, int]:
    """Return the allowed lifespan cap range for a realm."""
    return REALM_LIFESPAN_RANGES.get(realm, (80, 120))


def stage_label_for_realm(realm: str, stage: int) -> str:
    """Display only Qi Refining as numbered layers; later realms use phases."""
    try:
        value = int(stage)
    except (TypeError, ValueError):
        value = 1
    if realm == "练气":
        value = max(1, min(9, value))
        return f"{value}层"
    if realm == "飞升":
        return ""
    labels = ("初期", "中期", "后期", "圆满")
    return labels[max(1, min(4, value)) - 1]


def format_realm_name(realm: str, stage: int) -> str:
    """Return the public realm label used by backend and frontend."""
    label = stage_label_for_realm(realm, stage)
    return f"{realm}{label}" if label else realm


def compute_starting_lifespan(
    realm: str,
    *,
    attributes: dict[str, int] | None = None,
    talent: str = "",
    difficulty: str = "",
    extra_lifespan: int = 0,
) -> int:
    """Compute a character-specific lifespan cap within the realm range."""
    low, high = realm_lifespan_range(realm)
    attrs = attributes or {}
    physique = normalize_attribute_value(attrs.get("physique", ATTRIBUTE_DEFAULT))
    root_bone = normalize_attribute_value(attrs.get("root_bone", ATTRIBUTE_DEFAULT))
    span = high - low
    score = (physique + root_bone) / (ATTRIBUTE_MAX * 2)
    cap = low + round(span * score)
    if "天命" in talent or "长生" in talent:
        cap += max(5, span // 8)
    if difficulty == "困难":
        cap -= max(3, span // 12)
    elif difficulty == "简单":
        cap += max(3, span // 12)
    cap += int(extra_lifespan or 0)
    return max(1, min(high + max(0, int(extra_lifespan or 0)), cap))


def compute_breakthrough_lifespan(
    next_realm: str,
    current_lifespan: int,
    *,
    attributes: dict[str, int] | None = None,
    talent: str = "",
    difficulty: str = "",
) -> int:
    """Return the new lifespan cap after a successful breakthrough."""
    cap = compute_starting_lifespan(
        next_realm,
        attributes=attributes,
        talent=talent,
        difficulty=difficulty,
    )
    return max(int(current_lifespan or 1), cap)

# ─────────────────────────────────────────────────────────────────────────────
# Equipment slots
# ─────────────────────────────────────────────────────────────────────────────

EQUIPMENT_SLOTS: list[str] = ["weapon", "armor", "accessory"]

# Default empty equipment slots dict.
DEFAULT_EQUIPMENT_SLOTS: dict[str, Any] = {slot: None for slot in EQUIPMENT_SLOTS}

# NPC affinity defaults
NPC_AFFINITY_NEUTRAL: int = 0
NPC_AFFINITY_FRIENDLY: int = 30
NPC_AFFINITY_HOSTILE: int = -30

# Quest types
QUEST_TYPES: list[str] = ["主线", "支线", "日常", "隐藏"]

# Item types
ITEM_TYPES: list[str] = ["武器", "防具", "丹药", "材料", "其他"]

# Technique types
TECHNIQUE_TYPES: list[str] = ["内功", "外功", "术法", "身法"]
