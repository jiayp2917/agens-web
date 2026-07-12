"""Catalog semantics should reach the engine without a second content source."""

from __future__ import annotations

from typing import Any

from web.backend.service import WebGameService


class _CatalogDb:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.rows = {
            "catalog_talents": [{
                "name": "星痕感应",
                "description": "能察觉常人忽略的天象变化。",
                "tags": ["机缘", "神魂"],
                "attribute_mods": {"soul": 1},
            }],
            "catalog_family_backgrounds": [{
                "name": "旧族旁门",
                "description": "出身没落旧族，仍背负一份无人认领的旧契。",
                "story_tags": ["世家", "传承"],
                "initial_risks": ["旧契追索"],
            }],
            "catalog_spirit_roots": [{
                "name": "潮汐灵根",
                "grade": "天",
                "cultivation_tendency": "观潮炼神",
                "event_tags": ["神魂", "变化"],
            }],
            "catalog_difficulties": [{
                "name": "普通",
                "description": "风险和收益均衡。",
                "risk_multiplier": 1.0,
            }],
        }

    def list_catalog(self, table: str) -> list[dict[str, Any]]:
        self.calls.append(table)
        return list(self.rows.get(table, []))


def test_normalize_profile_attaches_selected_catalog_semantics_once() -> None:
    db = _CatalogDb()
    service = WebGameService(db)  # type: ignore[arg-type]

    normalized = service._normalize_profile({
        "talent": "星痕感应",
        "family_background": "旧族旁门",
        "spirit_root": "潮汐灵根",
        "difficulty": "普通",
        "attributes": {key: 5 for key in (
            "root_bone", "comprehension", "luck", "willpower", "physique", "soul"
        )},
    })

    assert normalized["spirit_root_grade"] == "天"
    assert normalized["profile_semantics"]["talent"]["tags"] == ["机缘", "神魂"]
    assert normalized["profile_semantics"]["family_background"]["initial_risks"] == ["旧契追索"]
    assert db.calls == [
        "catalog_talents",
        "catalog_family_backgrounds",
        "catalog_spirit_roots",
        "catalog_difficulties",
    ]
