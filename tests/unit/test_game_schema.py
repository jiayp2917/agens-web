"""Tests for game_schema TypedDict definitions — field completeness validation."""

from __future__ import annotations

import typing
import pytest

from agens_novel.state.game_schema import (
    Technique,
    InventoryItem,
    NpcInfo,
    QuestInfo,
    CombatActor,
    CombatState,
    CharacterState,
    WorldState,
    GameState,
)


class TestTechnique:
    """Validate Technique TypedDict fields."""

    def test_has_required_fields(self):
        # TypedDicts with total=False allow all fields to be optional
        annotations = Technique.__annotations__
        assert "name" in annotations
        assert "level" in annotations
        assert "type" in annotations
        assert "mp_cost" in annotations
        assert "element" in annotations


class TestInventoryItem:
    """Validate InventoryItem TypedDict fields."""

    def test_has_required_fields(self):
        annotations = InventoryItem.__annotations__
        assert "name" in annotations
        assert "quantity" in annotations
        assert "type" in annotations
        assert "rarity" in annotations
        assert "effects" in annotations
        assert "equipped" in annotations
        assert "slot" in annotations


class TestNpcInfo:
    """Validate NpcInfo TypedDict fields."""

    def test_has_required_fields(self):
        annotations = NpcInfo.__annotations__
        assert "name" in annotations
        assert "relation" in annotations
        assert "realm" in annotations
        assert "affinity" in annotations
        assert "personality" in annotations
        assert "can_trade" in annotations
        assert "can_teach" in annotations
        assert "exclusive_quest" in annotations


class TestQuestInfo:
    """Validate QuestInfo TypedDict fields."""

    def test_has_required_fields(self):
        annotations = QuestInfo.__annotations__
        assert "name" in annotations
        assert "description" in annotations
        assert "status" in annotations
        assert "type" in annotations
        assert "conditions" in annotations
        assert "rewards" in annotations
        assert "giver" in annotations


class TestCombatActor:
    """Validate CombatActor TypedDict fields."""

    def test_has_required_fields(self):
        annotations = CombatActor.__annotations__
        assert "name" in annotations
        assert "hp" in annotations
        assert "hp_max" in annotations
        assert "mp" in annotations
        assert "mp_max" in annotations
        assert "realm" in annotations
        assert "techniques" in annotations
        assert "consumables" in annotations
        assert "is_defending" in annotations


class TestCombatState:
    """Validate CombatState TypedDict fields."""

    def test_has_required_fields(self):
        annotations = CombatState.__annotations__
        assert "phase" in annotations
        assert "player" in annotations
        assert "enemy" in annotations
        assert "available_actions" in annotations
        assert "turn_count" in annotations
        assert "result" in annotations
        assert "narrative" in annotations


class TestCharacterState:
    """Validate CharacterState has all new fields."""

    def test_has_new_fields(self):
        annotations = CharacterState.__annotations__
        # New fields from the xianxia update
        assert "spirit_root" in annotations
        assert "spirit_root_grade" in annotations
        assert "equipment_slots" in annotations
        assert "combat" in annotations

    def test_has_all_core_fields(self):
        annotations = CharacterState.__annotations__
        core = {"name", "realm", "realm_stage", "hp", "hp_max", "mp", "mp_max",
                "techniques", "inventory", "experience", "experience_to_next",
                "gold", "status_effects", "lifespan"}
        assert core.issubset(set(annotations.keys()))


class TestWorldState:
    """Validate WorldState fields."""

    def test_has_npc_and_quest_fields(self):
        annotations = WorldState.__annotations__
        assert "npcs_present" in annotations
        assert "active_quests" in annotations
        assert "day_count" in annotations


class TestGameState:
    """Validate GameState top-level structure."""

    def test_has_meta_fields(self):
        annotations = GameState.__annotations__
        assert "turn_count" in annotations
        assert "game_started" in annotations
        assert "game_over" in annotations
        assert "game_over_reason" in annotations

    def test_has_character_and_world(self):
        annotations = GameState.__annotations__
        assert "character" in annotations
        assert "world" in annotations

    def test_has_agent_io_fields(self):
        annotations = GameState.__annotations__
        assert "narrative" in annotations
        assert "state_delta" in annotations
        assert "approved" in annotations
        assert "corrected_delta" in annotations
