"""Tests for GameSession.to_save_dict / from_save_dict roundtrip."""

from __future__ import annotations

from agens_novel.session.game_session import GameSession


class TestSerializationRoundtrip:
    """Verify save/load roundtrip preserves all fields."""

    def test_full_roundtrip(self):
        s = GameSession()
        s.char_name = "测试角色"
        s.realm = "金丹"
        s.realm_stage = 3
        s.hp = 200
        s.hp_max = 200
        s.mp = 150
        s.mp_max = 150
        s.spirit_root = "火灵根"
        s.spirit_root_grade = "天级"
        s.experience = 500
        s.experience_to_next = 1000
        s.gold = 999
        s.techniques = [{"name": "火球术", "mp_cost": 10}]
        s.inventory = [{"name": "回血丹", "quantity": 3}]
        s.status_effects = ["中毒"]
        s.lifespan = 500
        s.equipment_slots = {"weapon": {"name": "灵剑"}}
        s.combat = {"phase": "player_turn", "enemy": {"name": "妖兽"}}
        s.location = "青云山"
        s.region = "东域"
        s.current_scene = "山洞"
        s.day_count = 15
        s.npcs_present = [{"name": "老道"}]
        s.active_quests = [{"name": "寻仙草"}]
        s.discovered_locations = ["山洞"]
        s.lore_facts = ["灵石可提炼"]
        s.turn_count = 42
        s.game_started = True
        s.game_over = False
        s.finale = False

        # Serialize → deserialize.
        data = s.to_save_dict()
        restored = GameSession.from_save_dict(data)

        assert restored.char_name == "测试角色"
        assert restored.realm == "金丹"
        assert restored.hp == 200
        assert restored.mp == 150
        assert restored.spirit_root == "火灵根"
        assert restored.gold == 999
        assert len(restored.techniques) == 1
        assert restored.techniques[0]["name"] == "火球术"
        assert restored.combat["phase"] == "player_turn"
        assert restored.turn_count == 42
        assert restored.location == "青云山"
        assert restored.day_count == 15
        assert len(restored.active_quests) == 1
        assert restored.finale is False
