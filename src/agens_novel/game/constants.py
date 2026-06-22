"""Game constants for the xianxia cultivation simulator.

Defines realm progression, spirit root types, rarity levels, and equipment
slot configuration.  All constants are module-level for easy import.
"""

from __future__ import annotations

from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Gameplay / character creation constants
# ─────────────────────────────────────────────────────────────────────────────


# Kept only as a legacy save-field value. The UI now has one mode:
# A/B/C model choices plus D typed input.
DEFAULT_GAME_MODE = "abcd"

TALENT_OPTIONS: list[str] = [
    "平平无奇",
    "草木亲和",
    "剑心微明",
    "惊雷骨",
    "天命道胎",
]

FAMILY_BACKGROUNDS: list[str] = [
    "农家",
    "寒门",
    "小族",
    "宗门旁支",
    "隐世仙族",
]

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

DEFAULT_ATTRIBUTES: dict[str, int] = {key: 50 for key in ATTRIBUTE_KEYS}

SPECIAL_START_CODE = "2917"
SPECIAL_START_NAME = "阿清"
SPECIAL_START_ATTRIBUTES: dict[str, int] = {key: 99 for key in ATTRIBUTE_KEYS}

# ─────────────────────────────────────────────────────────────────────────────
# Realm system
# ─────────────────────────────────────────────────────────────────────────────

# 9 realms: first 5 fully implemented, last 4 reserved for future expansion.
REALM_ORDER: list[str] = [
    "练气", "筑基", "金丹", "元婴", "化神",     # 首版实现
    "合体", "大乘", "渡劫", "飞升",             # 预留
]

# Realm configuration: each realm's stage count, breakthrough thresholds, etc.
REALM_CONFIGS: dict[str, dict[str, Any]] = {
    "练气": {
        "name": "练气",
        "stages": 9,
        "experience_required": 100,
        "insight_required": 30,
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
        "stages": 4,
        "experience_required": 300,
        "insight_required": 60,
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
        "stages": 4,
        "experience_required": 600,
        "insight_required": 100,
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
        "stages": 4,
        "experience_required": 1200,
        "insight_required": 150,
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
        "stages": 4,
        "experience_required": 2500,
        "insight_required": 200,
        "breakthrough_requirements": [
            {"key": "unity_law_aid", "label": "天地法则感悟或合体道基"},
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
        "stages": 4,
        "experience_required": 5000,
        "insight_required": 260,
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
        "stages": 4,
        "experience_required": 10000,
        "insight_required": 330,
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
        "stages": 4,
        "experience_required": 20000,
        "insight_required": 400,
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
        "stages": 1,
        "experience_required": 999999,
        "insight_required": 0,
        "breakthrough_requirements": [],
        "breakthrough_base_rate": 0.00,
        "spirit_root_bonus": {},
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Spirit roots (8 types)
# ─────────────────────────────────────────────────────────────────────────────

SPIRIT_ROOTS: list[dict[str, Any]] = [
    # 五行灵根 (地灵根)
    {"name": "金灵根", "element": "金", "grade": "地", "cultivation_bonus": 1.2, "breakthrough_bonus": 0.05},
    {"name": "木灵根", "element": "木", "grade": "地", "cultivation_bonus": 1.2, "breakthrough_bonus": 0.05},
    {"name": "水灵根", "element": "水", "grade": "地", "cultivation_bonus": 1.2, "breakthrough_bonus": 0.05},
    {"name": "火灵根", "element": "火", "grade": "地", "cultivation_bonus": 1.2, "breakthrough_bonus": 0.05},
    {"name": "土灵根", "element": "土", "grade": "地", "cultivation_bonus": 1.2, "breakthrough_bonus": 0.05},
    # 异灵根 (天灵根)
    {"name": "冰灵根", "element": "冰", "grade": "天", "cultivation_bonus": 1.5, "breakthrough_bonus": 0.10},
    {"name": "雷灵根", "element": "雷", "grade": "天", "cultivation_bonus": 1.5, "breakthrough_bonus": 0.10},
    {"name": "风灵根", "element": "风", "grade": "天", "cultivation_bonus": 1.5, "breakthrough_bonus": 0.10},
]

# Quick lookup by name.
SPIRIT_ROOT_MAP: dict[str, dict[str, Any]] = {sr["name"]: sr for sr in SPIRIT_ROOTS}

# Spirit root grade names for display.
SPIRIT_ROOT_GRADES: list[str] = ["天", "地", "玄", "黄"]

# ─────────────────────────────────────────────────────────────────────────────
# Rarity levels
# ─────────────────────────────────────────────────────────────────────────────

# ── Catalog rarity tiers (白绿蓝紫橙红) for talents, family backgrounds, spirit roots ──
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

RARITY_ORDER: list[str] = ["凡品", "良品", "上品", "极品", "仙品"]

RARITY_MULTIPLIER: dict[str, float] = {
    "凡品": 1.0,
    "良品": 1.3,
    "上品": 1.6,
    "极品": 2.0,
    "仙品": 3.0,
}

# ─────────────────────────────────────────────────────────────────────────────
# Equipment slots
# ─────────────────────────────────────────────────────────────────────────────

EQUIPMENT_SLOTS: list[str] = ["weapon", "armor", "accessory"]

# Default empty equipment slots dict.
DEFAULT_EQUIPMENT_SLOTS: dict[str, Any] = {slot: None for slot in EQUIPMENT_SLOTS}

# ─────────────────────────────────────────────────────────────────────────────
# Combat constants
# ─────────────────────────────────────────────────────────────────────────────

COMBAT_ACTIONS: list[str] = ["attack", "technique", "item", "defend", "flee"]

COMBAT_PHASES: list[str] = ["idle", "player_turn", "enemy_turn", "resolve", "victory", "defeat"]

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
