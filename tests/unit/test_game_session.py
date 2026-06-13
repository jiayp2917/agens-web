"""Tests for GameSession — new fields, delta application, serialization."""

from __future__ import annotations

import pytest

from agens_novel.repl.game_session import GameSession
from agens_novel.game.constants import DEFAULT_ATTRIBUTES, DEFAULT_EQUIPMENT_SLOTS


class TestGameSessionInit:
    """Test default field initialization."""

    def test_default_values(self):
        s = GameSession()
        assert s.realm == "练气"
        assert s.realm_stage == 1
        assert s.hp == 100
        assert s.hp_max == 100
        assert s.mp == 50
        assert s.mp_max == 50
        assert s.spirit_root == ""
        assert s.spirit_root_grade == ""
        assert s.age == 16
        assert s.talent == ""
        assert s.family_background == ""
        assert s.luck == "中上"
        assert s.difficulty == "普通"
        assert s.game_mode == "high"
        assert s.attributes == DEFAULT_ATTRIBUTES
        assert s.last_choices == []
        assert s.experience == 0
        assert s.experience_to_next == 100
        assert s.gold == 0
        assert s.techniques == []
        assert s.inventory == []
        assert s.status_effects == []
        assert s.lifespan == 100
        assert s.combat is None
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
                "luck": "平稳",
                "difficulty": "困难",
                "game_mode": "mid",
                "attributes": {"root_bone": 75, "luck": 101, "bad": True},
            }
        })
        assert s.age == 18
        assert s.talent == "剑心微明"
        assert s.family_background == "寒门"
        assert s.luck == "平稳"
        assert s.difficulty == "困难"
        assert s.game_mode == "mid"
        assert s.attributes["root_bone"] == 75
        assert s.attributes["luck"] == 100
        assert "bad" not in s.attributes

    def test_apply_combat_start(self):
        s = GameSession()
        combat = {"phase": "player_turn", "enemy": {"name": "妖兽"}}
        s.apply_delta({"character": {"combat": combat}})
        assert s.combat is not None
        assert s.combat["phase"] == "player_turn"

    def test_apply_combat_update(self):
        s = GameSession()
        s.combat = {"phase": "player_turn", "enemy": {"hp": 80}}
        s.apply_delta({"character": {"combat": {"enemy": {"hp": 50}}}})
        assert s.combat["enemy"]["hp"] == 50

    def test_apply_combat_clear(self):
        s = GameSession()
        s.combat = {"phase": "player_turn"}
        s.apply_delta({"character": {"combat": None}})
        assert s.combat is None

    def test_apply_combat_empty_dict_clears(self):
        s = GameSession()
        s.combat = {"phase": "player_turn"}
        s.apply_delta({"character": {"combat": {}}})
        assert s.combat is None

    def test_apply_equipment_slots(self):
        s = GameSession()
        s.apply_delta({"character": {"equipment_slots": {"weapon": {"name": "铁剑"}}}})
        assert s.equipment_slots["weapon"]["name"] == "铁剑"
        # Other slots should still be None
        assert s.equipment_slots["armor"] is None

    def test_apply_hp_positive_delta(self):
        s = GameSession()
        s.hp = 80
        s.apply_delta({"character": {"hp": "+20"}})
        assert s.hp == 100

    def test_apply_hp_negative_delta(self):
        s = GameSession()
        s.hp = 80
        s.apply_delta({"character": {"hp": "-30"}})
        assert s.hp == 50

    def test_apply_hp_absolute(self):
        s = GameSession()
        s.hp = 80
        s.apply_delta({"character": {"hp": 50}})
        assert s.hp == 50

    def test_apply_hp_clamped_to_max(self):
        s = GameSession()
        s.hp = 90
        s.apply_delta({"character": {"hp": "+30"}})
        assert s.hp == 100  # clamped to hp_max

    def test_apply_hp_not_below_zero(self):
        s = GameSession()
        s.hp = 10
        s.apply_delta({"character": {"hp": "-50"}})
        assert s.hp == 0

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


class TestGameSessionSerialization:
    """Test to_save_dict / from_save_dict round-trip."""

    def test_round_trip(self):
        s = GameSession()
        s.char_name = "许满"
        s.realm = "筑基"
        s.realm_stage = 3
        s.hp = 150
        s.hp_max = 200
        s.mp = 80
        s.mp_max = 100
        s.spirit_root = "火灵根"
        s.spirit_root_grade = "地"
        s.age = 17
        s.talent = "剑心微明"
        s.family_background = "寒门"
        s.luck = "中上"
        s.difficulty = "困难"
        s.game_mode = "mid"
        s.attributes = {key: 66 for key in DEFAULT_ATTRIBUTES}
        s.last_choices = ["探查异动", "通知同门"]
        s.experience = 500
        s.experience_to_next = 300
        s.gold = 50
        s.techniques = [{"name": "火球术", "type": "术法"}]
        s.inventory = [{"name": "回血丹", "type": "丹药"}]
        s.status_effects = ["中毒"]
        s.lifespan = 95
        s.equipment_slots = {"weapon": {"name": "铁剑"}, "armor": None, "accessory": None}
        s.combat = {"phase": "player_turn", "enemy": {"name": "妖兽"}}
        s.location = "青云山"
        s.region = "东荒"
        s.day_count = 5
        s.npcs_present = [{"name": "陈师兄"}]
        s.active_quests = [{"name": "入门修行"}]
        s.discovered_locations = ["青云山"]
        s.lore_facts = ["东荒三宗之一"]
        s.game_started = True
        s.turn_count = 10

        # Save and load
        data = s.to_save_dict()
        s2 = GameSession.from_save_dict(data)

        assert s2.char_name == "许满"
        assert s2.realm == "筑基"
        assert s2.realm_stage == 3
        assert s2.hp == 150
        assert s2.hp_max == 200
        assert s2.mp == 80
        assert s2.mp_max == 100
        assert s2.spirit_root == "火灵根"
        assert s2.spirit_root_grade == "地"
        assert s2.age == 17
        assert s2.talent == "剑心微明"
        assert s2.family_background == "寒门"
        assert s2.luck == "中上"
        assert s2.difficulty == "困难"
        assert s2.game_mode == "mid"
        assert s2.attributes == {key: 66 for key in DEFAULT_ATTRIBUTES}
        assert s2.last_choices == ["探查异动", "通知同门"]
        assert s2.experience == 500
        assert s2.experience_to_next == 300
        assert s2.gold == 50
        assert s2.techniques == [{"name": "火球术", "type": "术法"}]
        assert s2.inventory == [{"name": "回血丹", "type": "丹药"}]
        assert s2.status_effects == ["中毒"]
        assert s2.lifespan == 95
        assert s2.equipment_slots["weapon"]["name"] == "铁剑"
        assert s2.combat["phase"] == "player_turn"
        assert s2.location == "青云山"
        assert s2.region == "东荒"
        assert s2.day_count == 5
        assert s2.game_started is True
        assert s2.turn_count == 10

    def test_round_trip_preserves_none_combat(self):
        s = GameSession()
        s.game_started = True
        data = s.to_save_dict()
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
        assert s.luck == "中上"
        assert s.game_mode == "high"
        assert s.attributes == DEFAULT_ATTRIBUTES


class TestGameSessionReset:
    """Test reset clears all new fields."""

    def test_reset_clears_all(self):
        s = GameSession()
        s.char_name = "许满"
        s.realm = "筑基"
        s.spirit_root = "火灵根"
        s.spirit_root_grade = "地"
        s.combat = {"phase": "player_turn"}
        s.equipment_slots = {"weapon": {"name": "铁剑"}, "armor": None, "accessory": None}
        s.game_started = True
        s.game_over = True
        s.hp = 0
        s.error = "dead"

        s.reset()

        assert s.char_name == ""
        assert s.realm == "练气"
        assert s.spirit_root == ""
        assert s.spirit_root_grade == ""
        assert s.combat is None
        assert s.equipment_slots == dict(DEFAULT_EQUIPMENT_SLOTS)
        assert s.game_started is False
        assert s.game_over is False
        assert s.hp == 100
        assert s.error == ""


class TestGameSessionAsGameState:
    """Test as_game_state() output format."""

    def test_includes_new_fields(self):
        s = GameSession()
        s.spirit_root = "冰灵根"
        s.spirit_root_grade = "天"
        s.equipment_slots = {"weapon": None, "armor": None, "accessory": None}
        s.combat = None

        gs = s.as_game_state()

        assert gs["character"]["spirit_root"] == "冰灵根"
        assert gs["character"]["spirit_root_grade"] == "天"
        assert gs["character"]["equipment_slots"] == {"weapon": None, "armor": None, "accessory": None}
        assert gs["character"]["combat"] is None
