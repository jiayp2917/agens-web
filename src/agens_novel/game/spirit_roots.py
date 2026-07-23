"""Canonical spirit-root registry shared by rules and catalog seeding."""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .fate_content import entries_for

_LEGACY_SPIRIT_ROOTS: tuple[dict[str, Any], ...] = (
    {
        "key": "metal",
        "name": "金灵根",
        "element": "金",
        "grade": "地",
        "cultivation_bonus": 1.2,
        "breakthrough_bonus": 0.05,
        "cultivation_tendency": "杀伐之道",
        "event_tags": ["剑意", "兵戈", "锋芒"],
    },
    {
        "key": "wood",
        "name": "木灵根",
        "element": "木",
        "grade": "地",
        "cultivation_bonus": 1.2,
        "breakthrough_bonus": 0.05,
        "cultivation_tendency": "生生之道",
        "event_tags": ["灵植", "生机", "丹道"],
    },
    {
        "key": "water",
        "name": "水灵根",
        "element": "水",
        "grade": "地",
        "cultivation_bonus": 1.2,
        "breakthrough_bonus": 0.05,
        "cultivation_tendency": "柔韧之道",
        "event_tags": ["幻术", "变化", "治愈"],
    },
    {
        "key": "fire",
        "name": "火灵根",
        "element": "火",
        "grade": "地",
        "cultivation_bonus": 1.2,
        "breakthrough_bonus": 0.05,
        "cultivation_tendency": "焚天之道",
        "event_tags": ["丹火", "炼器", "焚灭"],
    },
    {
        "key": "earth",
        "name": "土灵根",
        "element": "土",
        "grade": "地",
        "cultivation_bonus": 1.2,
        "breakthrough_bonus": 0.05,
        "cultivation_tendency": "厚德之道",
        "event_tags": ["防御", "地脉", "稳固"],
    },
    {
        "key": "ice",
        "name": "冰灵根",
        "element": "冰",
        "grade": "天",
        "cultivation_bonus": 1.5,
        "breakthrough_bonus": 0.10,
        "cultivation_tendency": "极寒之道",
        "event_tags": ["极寒", "封印", "静心"],
    },
    {
        "key": "thunder",
        "name": "雷灵根",
        "element": "雷",
        "grade": "天",
        "cultivation_bonus": 1.5,
        "breakthrough_bonus": 0.10,
        "cultivation_tendency": "天威之道",
        "event_tags": ["天劫", "破邪", "极速"],
    },
    {
        "key": "wind",
        "name": "风灵根",
        "element": "风",
        "grade": "天",
        "cultivation_bonus": 1.5,
        "breakthrough_bonus": 0.10,
        "cultivation_tendency": "逍遥之道",
        "event_tags": ["逍遥", "疾行", "无形"],
    },
    {
        "key": "yin-yang",
        "name": "阴阳灵根",
        "element": "阴阳",
        "grade": "天",
        "cultivation_bonus": 1.8,
        "breakthrough_bonus": 0.12,
        "cultivation_tendency": "太极之道",
        "event_tags": ["阴阳", "轮回", "天道"],
    },
    {
        "key": "chaos",
        "name": "混沌灵根",
        "element": "混沌",
        "grade": "天",
        "cultivation_bonus": 2.0,
        "breakthrough_bonus": 0.15,
        "cultivation_tendency": "混元之道",
        "event_tags": ["混沌", "起源", "无上"],
    },
)


def _fate_root_rows() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "key": entry.key,
            "catalog_id": entry.stable_id,
            "name": entry.name,
            "rarity": entry.rarity,
            "description": entry.description,
            "element": entry.element,
            "grade": entry.grade,
            "cultivation_bonus": entry.cultivation_bonus,
            "breakthrough_bonus": entry.breakthrough_bonus,
            "cultivation_tendency": entry.advantage,
            "event_tags": list(entry.tags),
            "fate_root": True,
        }
        for entry in entries_for("root")
    )


def _build_registry() -> tuple[dict[str, Any], ...]:
    rows = tuple(dict(row) for row in _LEGACY_SPIRIT_ROOTS) + _fate_root_rows()
    names = [str(row["name"]) for row in rows]
    if len(names) != len(set(names)):
        raise RuntimeError("spirit-root registry contains duplicate names")
    return rows


SPIRIT_ROOT_REGISTRY: tuple[dict[str, Any], ...] = _build_registry()


def spirit_root_rule_rows() -> list[dict[str, Any]]:
    """Project the registry into the rule-system fields."""
    fields = ("name", "element", "grade", "cultivation_bonus", "breakthrough_bonus")
    return [{field: row[field] for field in fields} for row in SPIRIT_ROOT_REGISTRY]


def spirit_root_catalog_rows() -> list[dict[str, Any]]:
    """Project the registry into ``catalog_spirit_roots`` seed rows."""
    rows: list[dict[str, Any]] = []
    for row in SPIRIT_ROOT_REGISTRY:
        catalog_row = {
            "id": str(
                row.get("catalog_id")
                or uuid5(NAMESPACE_URL, f"agens-web:spirit-root:{row['key']}")
            ),
            "name": row["name"],
            "element": row["element"],
            "grade": row["grade"],
            "cultivation_bonus": row["cultivation_bonus"],
            "breakthrough_bonus": row["breakthrough_bonus"],
            "cultivation_tendency": row["cultivation_tendency"],
            "event_tags": list(row["event_tags"]),
        }
        if row.get("rarity"):
            catalog_row["rarity"] = row["rarity"]
        if row.get("description"):
            catalog_row["description"] = row["description"]
        rows.append(catalog_row)
    return rows


def fate_spirit_root_rule_rows() -> list[dict[str, Any]]:
    """Keep the legacy v3 fate-content projection available to callers."""
    fields = ("name", "element", "grade", "cultivation_bonus", "breakthrough_bonus")
    return [
        {field: row[field] for field in fields}
        for row in SPIRIT_ROOT_REGISTRY
        if row.get("fate_root")
    ]


def fate_spirit_root_catalog_rows() -> list[dict[str, Any]]:
    """Keep the legacy v3 fate-content catalog projection available to callers."""
    return [
        row
        for row in spirit_root_catalog_rows()
        if any(
            registered["name"] == row["name"] and registered.get("fate_root")
            for registered in SPIRIT_ROOT_REGISTRY
        )
    ]
