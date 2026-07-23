"""Tests for GameSession — new fields, delta application, serialization."""

from __future__ import annotations

from agens_novel.game.constants import DEFAULT_ATTRIBUTES, DEFAULT_EQUIPMENT_SLOTS
from agens_novel.session.game_session import GameSession


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
        s.attributes = {key: 7 for key in DEFAULT_ATTRIBUTES}
        s.last_choices = ["探查异动", "通知同门"]
        s.breakthrough_flags = ["foundation_aid"]
        s.techniques = [{"name": "火球术", "type": "术法"}]
        s.inventory = [{"name": "回血丹", "type": "丹药"}]
        s.legacy_talents = ["游历之眼"]
        s.titles = ["外门魁首"]
        s.relationships = [{"name": "陈师兄", "relation": "盟友", "affinity": 12}]
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
        s.story_key = "alliance-old-oath"
        s.story_version = 1
        s.story_state = {"phase_key": "turning", "stage_goal": "查清旧契"}
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
        assert not hasattr(s2, "game_mode")
        assert s2.attributes == {key: 7 for key in DEFAULT_ATTRIBUTES}
        assert s2.last_choices == ["探查异动", "通知同门"]
        assert s2.breakthrough_flags == ["foundation_aid"]
        assert s2.techniques == [{"name": "火球术", "type": "术法"}]
        assert s2.inventory == [{"name": "回血丹", "type": "丹药"}]
        assert s2.legacy_talents == ["游历之眼"]
        assert s2.titles == ["外门魁首"]
        assert s2.relationships == [{"name": "陈师兄", "relation": "盟友", "affinity": 12}]
        assert s2.status_effects == ["中毒"]
        assert s2.lifespan == 95
        assert s2.equipment_slots["weapon"]["name"] == "铁剑"
        assert s2.location == "青云山"
        assert s2.region == "东荒"
        assert s2.day_count == 5
        assert s2.story_key == "alliance-old-oath"
        assert s2.story_version == 1
        assert s2.story_state == {"phase_key": "turning", "stage_goal": "查清旧契"}
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
        assert not hasattr(s2, "combat")
        for legacy in (
            "hp",
            "hp_max",
            "mp",
            "mp_max",
            "game_mode",
            "experience",
            "experience_to_next",
            "insight",
            "gold",
        ):
            assert legacy not in data["character"]
            assert not hasattr(s2, legacy)

    def test_round_trip_default_equipment_slots(self):
        s = GameSession()
        data = s.to_save_dict()
        s2 = GameSession.from_save_dict(data)
        assert s2.equipment_slots == dict(DEFAULT_EQUIPMENT_SLOTS)

    def test_realm_turn_count_roundtrip(self):
        session = GameSession(realm_turn_count=7)

        restored = GameSession.from_save_dict(session.to_save_dict())

        assert restored.realm_turn_count == 7

    def test_old_save_uses_profile_defaults(self):
        data = {
            "turn_count": 3,
            "game_started": True,
            "character": {
                "name": "旧角色",
                "realm": "练气",
                "hp": 1,
                "hp_max": 1,
                "mp": 1,
                "mp_max": 1,
                "combat": {"phase": "player_turn"},
                "game_mode": "legacy",
            },
            "world": {},
        }
        s = GameSession.from_save_dict(data)
        assert s.char_name == "旧角色"
        assert s.age == 16
        assert s.attributes["luck"] == 5
        for legacy in ("game_mode", "hp", "hp_max", "mp", "mp_max", "combat"):
            assert not hasattr(s, legacy)
        assert s.attributes == DEFAULT_ATTRIBUTES
        assert s.chat_history == []
        assert s.story_key == ""
        assert s.story_version == 0
        assert s.story_state == {}
        assert s.realm_turn_count == 0

    def test_old_0_100_scale_save_attributes_are_migrated_to_0_10(self):
        data = {
            "turn_count": 1,
            "game_started": True,
            "character": {
                "name": "旧尺度角色",
                "attributes": {
                    "root_bone": 66,
                    "comprehension": 50,
                    "luck": 99,
                    "willpower": 0,
                    "physique": 11,
                    "soul": True,
                },
            },
            "world": {},
        }
        s = GameSession.from_save_dict(data)
        assert s.attributes == {
            "root_bone": 7,
            "comprehension": 5,
            "luck": 10,
            "willpower": 0,
            "physique": 1,
            "soul": 5,
        }

    def test_remaining_lifespan_is_cap_minus_age(self):
        s = GameSession()
        s.realm = "练气"
        s.lifespan = 100
        s.age = 18
        assert s.remaining_lifespan == 82

    def test_record_turn_projects_semantic_context_without_legacy_tags(self):
        s = GameSession()
        s.turn_count = 1
        s.story_key = "border-vein-crisis"
        s.story_version = 3
        s.story_state = {"recent_motifs": ["frontier-record-1"]}
        s.last_choices = ["稳固根基", "寻访机缘", "踏入险地", "静候气运"]

        s.record_turn(
            "稳固根基",
            "其人在外门静修一年。",
            {
                "character": {"age": "+1"},
                "world": {"lore_add": ["外门课业有了新记载。"]},
                "meta": {
                    "choice_slot": "A",
                    "choice_category": "稳妥",
                    "event_id": "steady-root-ledger",
                    "story_beat": "外门课业有了新记载。",
                    "turn_summary": "稳妥路线推进了一年。",
                },
            },
        )

        assistant = s.chat_history[-1]
        assert assistant["role"] == "assistant"
        assert assistant["content"] == "其人在外门静修一年。"
        assert "<state_update>" not in assistant["content"]
        context = assistant["accepted_turn_context"]
        assert context["contract_version"] == "accepted-turn-context-v1"
        assert context["choices"] == s.last_choices
        assert context["choice_slot"] == "A"
        assert context["choice_category"] == "稳妥"
        assert context["event_id"] == "steady-root-ledger"
        assert context["motif"] == "frontier-record-1"
        assert "character" not in context
        assert "world" not in context

    def test_recent_narrative_hashes_round_trip_without_storing_plaintext(self):
        s = GameSession()
        narrative = "山门外的风声已传入洞府。"
        s.record_turn("稳固根基", narrative, {})

        saved = s.to_save_dict()
        restored = GameSession.from_save_dict(saved)

        assert saved["recent_narrative_hashes"]
        assert narrative not in saved["recent_narrative_hashes"]
        assert restored.has_recent_narrative(narrative)
