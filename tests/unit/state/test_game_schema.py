"""Tests for v5 game_schema TypedDict definitions."""

from __future__ import annotations

from agens_novel.state.game_schema import (
    CharacterState,
    GameState,
    InventoryItem,
    NpcInfo,
    QuestInfo,
    Technique,
    WorldState,
)


class TestTechnique:
    def test_has_required_fields(self):
        annotations = Technique.__annotations__
        assert {"name", "level", "type", "element"}.issubset(annotations)
        assert "mp_cost" not in annotations


class TestInventoryItem:
    def test_has_required_fields(self):
        annotations = InventoryItem.__annotations__
        assert {"name", "quantity", "type", "rarity", "effects", "equipped", "slot"}.issubset(annotations)


class TestNpcInfo:
    def test_has_required_fields(self):
        annotations = NpcInfo.__annotations__
        assert {
            "name",
            "relation",
            "realm",
            "affinity",
            "personality",
            "can_trade",
            "can_teach",
            "exclusive_quest",
        }.issubset(annotations)


class TestQuestInfo:
    def test_has_required_fields(self):
        annotations = QuestInfo.__annotations__
        assert {"name", "description", "status", "type", "conditions", "rewards", "giver"}.issubset(annotations)


class TestCharacterState:
    def test_has_v5_core_fields(self):
        annotations = CharacterState.__annotations__
        core = {
            "name",
            "realm",
            "realm_stage",
            "spirit_root",
            "spirit_root_grade",
            "age",
            "talent",
            "family_background",
            "difficulty",
            "attributes",
            "breakthrough_flags",
            "techniques",
            "inventory",
            "status_effects",
            "lifespan",
            "remaining_lifespan",
            "equipment_slots",
        }
        assert core.issubset(annotations)

    def test_has_no_legacy_hp_mp_or_combat(self):
        annotations = CharacterState.__annotations__
        for legacy in ("hp", "hp_max", "mp", "mp_max", "combat", "experience", "experience_to_next", "insight", "gold"):
            assert legacy not in annotations


class TestWorldState:
    def test_has_world_fields(self):
        annotations = WorldState.__annotations__
        assert {
            "current_scene",
            "location",
            "region",
            "npcs_present",
            "active_quests",
            "discovered_locations",
            "lore_facts",
            "turn_events",
            "day_count",
        }.issubset(annotations)


class TestGameState:
    def test_has_meta_fields(self):
        annotations = GameState.__annotations__
        assert {"turn_count", "game_started", "game_over", "game_over_reason"}.issubset(annotations)

    def test_has_character_and_world(self):
        annotations = GameState.__annotations__
        assert "character" in annotations
        assert "world" in annotations

    def test_has_agent_io_fields(self):
        annotations = GameState.__annotations__
        assert {"narrative", "state_delta", "approved", "corrected_delta"}.issubset(annotations)
