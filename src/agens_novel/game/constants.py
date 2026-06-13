"""Game constants for the xianxia cultivation simulator.

Defines realm progression, spirit root types, rarity levels, and equipment
slot configuration.  All constants are module-level for easy import.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Gameplay mode / character creation constants
# ─────────────────────────────────────────────────────────────────────────────


class GameMode(StrEnum):
    """Mobile play-mode options used by the Android UI."""

    HIGH = "high"
    MID = "mid"
    LOW = "low"


GAME_MODE_LABELS: dict[str, str] = {
    GameMode.HIGH.value: "高自由度",
    GameMode.MID.value: "中自由度",
    GameMode.LOW.value: "低自由度",
}

DEFAULT_GAME_MODE = GameMode.HIGH.value

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

ATTRIBUTE_KEYS: list[str] = ["root_bone", "comprehension", "luck", "willpower", "physique", "spiritual_sense"]

ATTRIBUTE_LABELS: dict[str, str] = {
    "root_bone": "根骨",
    "comprehension": "悟性",
    "luck": "气运",
    "willpower": "心性",
    "physique": "体魄",
    "spiritual_sense": "神识",
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
        "breakthrough_base_rate": 0.80,
        "hp_base": 100,
        "mp_base": 50,
        "spirit_root_bonus": {
            "天": 0.10,
            "地": 0.05,
        },
    },
    "筑基": {
        "name": "筑基",
        "stages": 4,
        "experience_required": 300,
        "breakthrough_base_rate": 0.60,
        "hp_base": 200,
        "mp_base": 100,
        "spirit_root_bonus": {
            "天": 0.10,
            "地": 0.05,
        },
    },
    "金丹": {
        "name": "金丹",
        "stages": 4,
        "experience_required": 600,
        "breakthrough_base_rate": 0.45,
        "hp_base": 400,
        "mp_base": 200,
        "spirit_root_bonus": {
            "天": 0.10,
            "地": 0.05,
        },
    },
    "元婴": {
        "name": "元婴",
        "stages": 4,
        "experience_required": 1200,
        "breakthrough_base_rate": 0.30,
        "hp_base": 800,
        "mp_base": 400,
        "spirit_root_bonus": {
            "天": 0.10,
            "地": 0.05,
        },
    },
    "化神": {
        "name": "化神",
        "stages": 4,
        "experience_required": 2500,
        "breakthrough_base_rate": 0.20,
        "hp_base": 1600,
        "mp_base": 800,
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
        "breakthrough_base_rate": 0.15,
        "hp_base": 3200,
        "mp_base": 1600,
        "spirit_root_bonus": {
            "天": 0.10,
            "地": 0.05,
        },
    },
    "大乘": {
        "name": "大乘",
        "stages": 4,
        "experience_required": 10000,
        "breakthrough_base_rate": 0.10,
        "hp_base": 6400,
        "mp_base": 3200,
        "spirit_root_bonus": {
            "天": 0.10,
            "地": 0.05,
        },
    },
    "渡劫": {
        "name": "渡劫",
        "stages": 4,
        "experience_required": 20000,
        "breakthrough_base_rate": 0.05,
        "hp_base": 12800,
        "mp_base": 6400,
        "spirit_root_bonus": {
            "天": 0.10,
            "地": 0.05,
        },
    },
    "飞升": {
        "name": "飞升",
        "stages": 1,
        "experience_required": 999999,
        "breakthrough_base_rate": 0.00,
        "hp_base": 99999,
        "mp_base": 99999,
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
