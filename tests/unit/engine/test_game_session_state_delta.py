"""Tests for GameSession — new fields, delta application, serialization."""

from __future__ import annotations

from agens_novel.game.constants import DEFAULT_ATTRIBUTES, DEFAULT_EQUIPMENT_SLOTS
from agens_novel.session.game_session import GameSession


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
        for legacy in (
            "game_mode",
            "hp",
            "hp_max",
            "mp",
            "mp_max",
            "combat",
            "experience",
            "experience_to_next",
            "insight",
            "gold",
        ):
            assert not hasattr(s, legacy)
        assert s.attributes == DEFAULT_ATTRIBUTES
        assert s.attributes["luck"] == 5
        assert s.last_choices == []
        assert s.breakthrough_flags == []
        assert s.techniques == []
        assert s.inventory == []
        assert s.legacy_talents == []
        assert s.titles == []
        assert s.relationships == []
        assert s.status_effects == []
        assert s.lifespan == 100
        assert s.equipment_slots == dict(DEFAULT_EQUIPMENT_SLOTS)
        assert s.game_started is False
        assert s.realm_turn_count == 0
        assert s.game_over is False


class TestGameSessionApplyDelta:
    """Test apply_delta for new fields."""

    def test_apply_spirit_root(self):
        s = GameSession()
        s.apply_delta({"character": {"spirit_root": "火灵根", "spirit_root_grade": "地"}})
        assert s.spirit_root == "火灵根"
        assert s.spirit_root_grade == "地"

    def test_apply_delta_ignores_none_nested_sections(self):
        s = GameSession()

        s.apply_delta({"character": None, "world": None, "meta": None})

        assert s.realm == "练气"
        assert s.age == 16
        assert s.location == ""
        assert s.game_over is False

    def test_apply_delta_ignores_non_dict_nested_sections(self):
        s = GameSession()
        s.apply_delta(
            {
                "character": ["bad"],
                "world": "bad",
                "meta": 123,
            }
        )

        assert s.realm == "练气"
        assert s.location == ""
        assert s.game_over is False

    def test_apply_profile_fields(self):
        s = GameSession()
        s.apply_delta(
            {
                "character": {
                    "age": "+2",
                    "talent": "剑心微明",
                    "family_background": "寒门",
                    "difficulty": "困难",
                    "game_mode": "mid",
                    "attributes": {"root_bone": 2, "luck": "+51", "bad": True},
                }
            }
        )
        assert s.age == 18
        assert s.talent == "剑心微明"
        assert s.family_background == "寒门"
        assert s.difficulty == "困难"
        assert not hasattr(s, "game_mode")
        assert s.attributes["root_bone"] == 7
        assert s.attributes["luck"] == 10
        assert "bad" not in s.attributes

    def test_apply_combat_start_is_ignored(self):
        """Game-mode v5: combat is event-based; a structured combat delta is dropped."""
        s = GameSession()
        combat = {"phase": "player_turn", "enemy": {"name": "妖兽"}}
        s.apply_delta({"character": {"combat": combat}})
        # No structured combat state on the session; the engine never reads it.
        assert not hasattr(s, "combat")

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

    def test_apply_experience_is_ignored(self):
        s = GameSession()
        s.apply_delta({"character": {"experience": "+30"}})
        assert not hasattr(s, "experience")

    def test_apply_gold_is_ignored(self):
        s = GameSession()
        s.apply_delta({"character": {"gold": "+5"}})
        assert not hasattr(s, "gold")

    def test_apply_techniques_add(self):
        s = GameSession()
        s.apply_delta({"character": {"techniques_add": [{"name": "火球术"}]}})
        assert len(s.techniques) == 1
        assert s.techniques[0]["name"] == "火球术"

    def test_apply_status_effects_add(self):
        s = GameSession()
        s.apply_delta({"character": {"status_effects_add": ["中毒"]}})
        assert "中毒" in s.status_effects

    def test_apply_titles_and_relationships_as_durable_character_state(self):
        s = GameSession()

        s.apply_delta(
            {
                "character": {
                    "title_add": ["外门魁首", "外门魁首"],
                    "relationship_add": [
                        {"name": "陈师兄", "relation": "同门", "affinity": 5},
                    ],
                }
            }
        )
        s.apply_delta(
            {
                "character": {
                    "relationship_add": [
                        {"name": "陈师兄", "relation": "盟友", "affinity": 15},
                    ],
                }
            }
        )

        assert s.titles == ["外门魁首"]
        assert s.relationships == [{"name": "陈师兄", "relation": "盟友", "affinity": 15}]

    def test_npc_presence_does_not_create_a_durable_relationship(self):
        s = GameSession()

        s.apply_delta({"world": {"npcs_present_add": [{"name": "赵执事", "relation": "引路人"}]}})

        assert s.npcs_present == [{"name": "赵执事", "relation": "引路人"}]
        assert s.relationships == []

    def test_scene_npc_does_not_override_explicit_relationship(self):
        s = GameSession()

        s.apply_delta(
            {
                "character": {
                    "relationship_add": [{"name": "陈师兄", "relation": "盟友", "affinity": 10}]
                },
                "world": {"npcs_present_add": [{"name": "陈师兄", "relation": "同门"}]},
            }
        )

        assert s.relationships == [{"name": "陈师兄", "relation": "盟友", "affinity": 10}]

    def test_apply_status_effects_no_duplicate(self):
        s = GameSession()
        s.status_effects = ["中毒"]
        s.apply_delta({"character": {"status_effects_add": ["中毒"]}})
        assert s.status_effects.count("中毒") == 1

    def test_apply_status_effects_remove_matches_string_and_structured_names(self):
        s = GameSession()
        unrelated = {"name": "旧伤", "severity": "轻"}
        s.status_effects = ["走火入魔", {"name": "修为未复"}, unrelated]

        s.apply_delta({"character": {"status_effects_remove": ["走火入魔", {"name": "修为未复"}]}})

        assert s.status_effects == [unrelated]

    def test_apply_status_effect_remove_then_add_keeps_new_effect(self):
        s = GameSession()
        s.status_effects = ["走火入魔"]

        s.apply_delta(
            {
                "character": {
                    "status_effects_remove": ["走火入魔"],
                    "status_effects_add": ["走火入魔"],
                }
            }
        )

        assert s.status_effects == ["走火入魔"]

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
        s.apply_delta(
            {"character": {"breakthrough_flags_add": ["foundation_aid", "foundation_aid", 123]}}
        )
        s.apply_delta({"character": {"breakthrough_flags_add": "golden_core_aid"}})
        assert s.breakthrough_flags == ["foundation_aid", "golden_core_aid"]


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
        assert gs["character"]["equipment_slots"] == {
            "weapon": None,
            "armor": None,
            "accessory": None,
        }
        # Game-mode v5: no structured combat field in game state.
        assert "combat" not in gs["character"]
