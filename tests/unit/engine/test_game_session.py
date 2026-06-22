"""Tests for GameSession — new fields, delta application, serialization."""

from __future__ import annotations

import pytest

from agens_novel.session.game_session import GameSession
from agens_novel.game.constants import DEFAULT_ATTRIBUTES, DEFAULT_EQUIPMENT_SLOTS


class TestGameSessionInit:
    """Test default field initialization."""

    def test_default_values(self):
        s = GameSession()
        assert s.realm == "练气"
        assert s.realm_stage == 1
        assert s.spirit_root == ""
        assert s.spirit_root_grade == ""
        assert s.age == 16
        assert s.talent == ""
        assert s.family_background == ""
        assert s.difficulty == "普通"
        assert s.game_mode == "abcd"
        assert s.attributes == DEFAULT_ATTRIBUTES
        assert s.attributes["luck"] == 50
        assert s.last_choices == []
        assert s.experience == 0
        assert s.experience_to_next == 100
        assert s.breakthrough_flags == []
        assert s.gold == 0
        assert s.techniques == []
        assert s.inventory == []
        assert s.status_effects == []
        assert s.lifespan == 100
        assert s.equipment_slots == dict(DEFAULT_EQUIPMENT_SLOTS)
        assert s.game_started is False
        assert s.game_over is False


class TestGameSessionApplyDelta:
    """Test apply_delta for new fields."""

    def test_apply_spirit_root(self):
        s = GameSession()
        s.apply_delta({"character": {"spirit_root": "火灵根", "spirit_root_grade": "地"}})
        assert s.spirit_root == "火灵根"
        assert s.spirit_root_grade == "地"

    def test_apply_profile_fields(self):
        s = GameSession()
        s.apply_delta({
            "character": {
                "age": "+2",
                "talent": "剑心微明",
                "family_background": "寒门",
                "difficulty": "困难",
                "game_mode": "mid",
                "attributes": {"root_bone": 75, "luck": 101, "bad": True},
            }
        })
        assert s.age == 18
        assert s.talent == "剑心微明"
        assert s.family_background == "寒门"
        assert s.difficulty == "困难"
        assert s.game_mode == "abcd"
        assert s.attributes["root_bone"] == 75
        assert s.attributes["luck"] == 100
        assert "bad" not in s.attributes

    def test_apply_combat_start_is_ignored(self):
        """Game-mode v5: combat is event-based; a structured combat delta is dropped."""
        s = GameSession()
        combat = {"phase": "player_turn", "enemy": {"name": "妖兽"}}
        s.apply_delta({"character": {"combat": combat}})
        # No structured combat state on the session; the engine never reads it.
        assert s.combat is None

    def test_apply_equipment_slots(self):
        s = GameSession()
        s.apply_delta({"character": {"equipment_slots": {"weapon": {"name": "铁剑"}}}})
        assert s.equipment_slots["weapon"]["name"] == "铁剑"
        # Other slots should still be None
        assert s.equipment_slots["armor"] is None

    def test_apply_lifespan_positive_delta(self):
        s = GameSession()
        s.lifespan = 80
        s.apply_delta({"character": {"lifespan": "+20"}})
        assert s.lifespan == 100

    def test_apply_lifespan_negative_delta(self):
        s = GameSession()
        s.lifespan = 80
        s.apply_delta({"character": {"lifespan": "-30"}})
        assert s.lifespan == 50

    def test_apply_lifespan_absolute(self):
        s = GameSession()
        s.lifespan = 80
        s.apply_delta({"character": {"lifespan": 50}})
        assert s.lifespan == 50

    def test_apply_lifespan_floored_at_one(self):
        """lifespan is the game-mode death resource (no HP); floor at 1."""
        s = GameSession()
        s.lifespan = 10
        s.apply_delta({"character": {"lifespan": "-50"}})
        assert s.lifespan == 1  # floor guard, not zero

    def test_apply_experience_add(self):
        s = GameSession()
        s.experience = 50
        s.apply_delta({"character": {"experience": "+30"}})
        assert s.experience == 80

    def test_apply_gold_add(self):
        s = GameSession()
        s.gold = 10
        s.apply_delta({"character": {"gold": "+5"}})
        assert s.gold == 15

    def test_apply_techniques_add(self):
        s = GameSession()
        s.apply_delta({"character": {"techniques_add": [{"name": "火球术"}]}})
        assert len(s.techniques) == 1
        assert s.techniques[0]["name"] == "火球术"

    def test_apply_status_effects_add(self):
        s = GameSession()
        s.apply_delta({"character": {"status_effects_add": ["中毒"]}})
        assert "中毒" in s.status_effects

    def test_apply_status_effects_no_duplicate(self):
        s = GameSession()
        s.status_effects = ["中毒"]
        s.apply_delta({"character": {"status_effects_add": ["中毒"]}})
        assert s.status_effects.count("中毒") == 1

    def test_apply_meta_game_over(self):
        s = GameSession()
        s.apply_delta({"meta": {"game_over": True, "game_over_reason": "test"}})
        assert s.game_over is True
        assert s.error == "test"

    def test_apply_meta_status_effect_add(self):
        s = GameSession()
        s.apply_delta({"meta": {"status_effect_add": "走火入魔"}})
        assert "走火入魔" in s.status_effects

    def test_apply_realm_change(self):
        s = GameSession()
        s.apply_delta({"character": {"realm": "筑基"}})
        assert s.realm == "筑基"

    def test_apply_world_location(self):
        s = GameSession()
        s.apply_delta({"world": {"location": "青云山", "region": "东荒"}})
        assert s.location == "青云山"
        assert s.region == "东荒"

    def test_apply_npc_present(self):
        s = GameSession()
        s.apply_delta({"world": {"npcs_present_add": [{"name": "陈师兄"}]}})
        assert len(s.npcs_present) == 1

    def test_apply_quest_add(self):
        s = GameSession()
        s.apply_delta({"world": {"active_quests_add": [{"name": "入门修行"}]}})
        assert len(s.active_quests) == 1

    def test_apply_breakthrough_flags_add(self):
        s = GameSession()
        s.apply_delta({"character": {"breakthrough_flags_add": ["foundation_aid", "foundation_aid", 123]}})
        s.apply_delta({"character": {"breakthrough_flags_add": "golden_core_aid"}})
        assert s.breakthrough_flags == ["foundation_aid", "golden_core_aid"]


class TestGameSessionSerialization:
    """Test to_save_dict / from_save_dict round-trip."""

    def test_round_trip(self):
        s = GameSession()
        s.char_name = "许满"
        s.realm = "筑基"
        s.realm_stage = 3
        s.spirit_root = "火灵根"
        s.spirit_root_grade = "地"
        s.age = 17
        s.talent = "剑心微明"
        s.family_background = "寒门"
        s.difficulty = "困难"
        s.game_mode = "abcd"
        s.attributes = {key: 66 for key in DEFAULT_ATTRIBUTES}
        s.last_choices = ["探查异动", "通知同门"]
        s.experience = 500
        s.experience_to_next = 300
        s.breakthrough_flags = ["foundation_aid"]
        s.gold = 50
        s.techniques = [{"name": "火球术", "type": "术法"}]
        s.inventory = [{"name": "回血丹", "type": "丹药"}]
        s.status_effects = ["中毒"]
        s.lifespan = 95
        s.equipment_slots = {"weapon": {"name": "铁剑"}, "armor": None, "accessory": None}
        s.location = "青云山"
        s.region = "东荒"
        s.day_count = 5
        s.npcs_present = [{"name": "陈师兄"}]
        s.active_quests = [{"name": "入门修行"}]
        s.discovered_locations = ["青云山"]
        s.lore_facts = ["东荒三宗之一"]
        s.chat_history = [{"role": "user", "content": f"行动{i}"} for i in range(25)]
        s.game_started = True
        s.turn_count = 10

        # Save and load
        data = s.to_save_dict()
        s2 = GameSession.from_save_dict(data)

        assert s2.char_name == "许满"
        assert s2.realm == "筑基"
        assert s2.realm_stage == 3
        assert s2.spirit_root == "火灵根"
        assert s2.spirit_root_grade == "地"
        assert s2.age == 17
        assert s2.talent == "剑心微明"
        assert s2.family_background == "寒门"
        assert s2.difficulty == "困难"
        assert s2.game_mode == "abcd"
        assert s2.attributes == {key: 66 for key in DEFAULT_ATTRIBUTES}
        assert s2.last_choices == ["探查异动", "通知同门"]
        assert s2.experience == 500
        assert s2.experience_to_next == 300
        assert s2.breakthrough_flags == ["foundation_aid"]
        assert s2.gold == 50
        assert s2.techniques == [{"name": "火球术", "type": "术法"}]
        assert s2.inventory == [{"name": "回血丹", "type": "丹药"}]
        assert s2.status_effects == ["中毒"]
        assert s2.lifespan == 95
        assert s2.equipment_slots["weapon"]["name"] == "铁剑"
        assert s2.location == "青云山"
        assert s2.region == "东荒"
        assert s2.day_count == 5
        assert s2.game_started is True
        assert s2.turn_count == 10
        assert len(s2.chat_history) == 20
        assert s2.chat_history[0]["content"] == "行动5"

    def test_round_trip_preserves_no_legacy_fields(self):
        """Game-mode v5: no structured combat is serialized; legacy fields absent."""
        s = GameSession()
        s.game_started = True
        data = s.to_save_dict()
        assert "combat" not in data["character"]
        s2 = GameSession.from_save_dict(data)
        assert s2.combat is None

    def test_round_trip_default_equipment_slots(self):
        s = GameSession()
        data = s.to_save_dict()
        s2 = GameSession.from_save_dict(data)
        assert s2.equipment_slots == dict(DEFAULT_EQUIPMENT_SLOTS)

    def test_old_save_uses_profile_defaults(self):
        data = {
            "turn_count": 3,
            "game_started": True,
            "character": {"name": "旧角色", "realm": "练气"},
            "world": {},
        }
        s = GameSession.from_save_dict(data)
        assert s.char_name == "旧角色"
        assert s.age == 16
        assert s.attributes["luck"] == 50
        assert s.game_mode == "abcd"
        assert s.attributes == DEFAULT_ATTRIBUTES
        assert s.chat_history == []


class TestGameSessionReset:
    """Test reset clears all new fields."""

    def test_reset_clears_all(self):
        s = GameSession()
        s.char_name = "许满"
        s.realm = "筑基"
        s.spirit_root = "火灵根"
        s.spirit_root_grade = "地"
        s.equipment_slots = {"weapon": {"name": "铁剑"}, "armor": None, "accessory": None}
        s.game_started = True
        s.game_over = True
        s.error = "dead"

        s.reset()

        assert s.char_name == ""
        assert s.realm == "练气"
        assert s.spirit_root == ""
        assert s.spirit_root_grade == ""
        assert s.equipment_slots == dict(DEFAULT_EQUIPMENT_SLOTS)
        assert s.game_started is False
        assert s.game_over is False
        assert s.error == ""


class TestGameSessionAsGameState:
    """Test as_game_state() output format."""

    def test_includes_new_fields(self):
        s = GameSession()
        s.spirit_root = "冰灵根"
        s.spirit_root_grade = "天"
        s.equipment_slots = {"weapon": None, "armor": None, "accessory": None}

        gs = s.as_game_state()

        assert gs["character"]["spirit_root"] == "冰灵根"
        assert gs["character"]["spirit_root_grade"] == "天"
        assert gs["character"]["equipment_slots"] == {"weapon": None, "armor": None, "accessory": None}
        # Game-mode v5: no structured combat field in game state.
        assert "combat" not in gs["character"]
