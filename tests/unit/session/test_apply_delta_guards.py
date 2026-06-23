"""Tests for GameSession.apply_delta defensive guards.

These tests ensure that ``apply_delta`` rejects malformed or out-of-whitelist
values gracefully, keeping the session object in a consistent state.
"""

from __future__ import annotations

from agens_novel.session.game_session import GameSession


class TestApplyDeltaDefensive:
    """Test apply_delta handles malformed input gracefully."""

    def test_realm_whitelist_valid(self):
        s = GameSession()
        s.apply_delta({"character": {"realm": "金丹"}})
        assert s.realm == "金丹"

    def test_realm_whitelist_invalid(self):
        s = GameSession()
        s.apply_delta({"character": {"realm": "超级赛亚人"}})
        assert s.realm == "练气"  # unchanged

    def test_realm_whitelist_flying(self):
        """飞升 should be accepted (it's in REALM_ORDER)."""
        s = GameSession()
        s.apply_delta({"character": {"realm": "飞升"}})
        assert s.realm == "飞升"

    def test_techniques_add_none(self):
        s = GameSession()
        s.apply_delta({"character": {"techniques_add": None}})
        assert s.techniques == []  # no crash

    def test_inventory_add_none(self):
        s = GameSession()
        s.apply_delta({"character": {"inventory_add": None}})
        assert s.inventory == []

    def test_status_effects_must_be_list(self):
        s = GameSession()
        s.apply_delta({"character": {"status_effects": "不是列表"}})
        assert s.status_effects == []  # unchanged

    def test_status_effects_add_none(self):
        s = GameSession()
        s.apply_delta({"character": {"status_effects_add": None}})
        assert s.status_effects == []

    def test_negative_lifespan_floored(self):
        """Game-mode v5: lifespan (not HP) is the death resource; floored at 1."""
        s = GameSession()
        s.lifespan = 10
        s.apply_delta({"character": {"lifespan": "-100"}})
        assert s.lifespan == 1  # floor guard at 1, not 0

    def test_gold_delta_is_ignored(self):
        s = GameSession()
        s.apply_delta({"character": {"gold": "-50"}})
        assert not hasattr(s, "gold")

    def test_legacy_gold_attribute_is_not_available(self):
        s = GameSession()
        assert not hasattr(s, "gold")

    def test_finale_flag(self):
        s = GameSession()
        s.apply_delta({"meta": {"finale": True}})
        assert s.finale is True

    def test_game_over_must_be_bool(self):
        s = GameSession()
        s.apply_delta({"meta": {"game_over": "yes"}})
        assert s.game_over is False  # string rejected

    def test_npcs_present_add_none(self):
        s = GameSession()
        s.apply_delta({"world": {"npcs_present_add": None}})
        assert s.npcs_present == []

    def test_lore_add_none(self):
        s = GameSession()
        s.apply_delta({"world": {"lore_add": None}})
        assert s.lore_facts == []

    def test_discovered_add_none(self):
        s = GameSession()
        s.apply_delta({"world": {"discovered_add": None}})
        assert s.discovered_locations == []

    def test_active_quests_add_none(self):
        s = GameSession()
        s.apply_delta({"world": {"active_quests_add": None}})
        assert s.active_quests == []

    def test_inventory_add_string(self):
        """Single string should be wrapped, not iterated as 5 chars."""
        s = GameSession()
        s.apply_delta({"character": {"inventory_add": "筑基药引"}})
        assert len(s.inventory) == 1
        assert s.inventory[0] == "筑基药引"

    def test_inventory_add_list(self):
        s = GameSession()
        s.apply_delta({"character": {"inventory_add": [{"name": "筑基药引", "quantity": 1}]}})
        assert len(s.inventory) == 1
        assert s.inventory[0]["name"] == "筑基药引"

    def test_equipment_slots_dict(self):
        s = GameSession()
        s.apply_delta({"character": {"equipment_slots": {"weapon": {"name": "铁剑"}}}})
        assert s.equipment_slots["weapon"]["name"] == "铁剑"

    def test_combat_clear_ignored(self):
        """Game-mode v5: structured combat is event-based; combat delta is dropped."""
        s = GameSession()
        s.apply_delta({"character": {"combat": None}})
        assert not hasattr(s, "combat")

    def test_combat_start_ignored(self):
        """A structured combat delta does not create structured combat state."""
        s = GameSession()
        s.apply_delta({"character": {"combat": {"phase": "player_turn", "enemy": {"name": "妖兽"}}}})
        assert not hasattr(s, "combat")
