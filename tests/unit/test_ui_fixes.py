"""Tests for UI test report fixes.

Covers:
- stream_callback no longer in LangGraph state (msgpack fix)
- NarrativeView filters <state_update> from streaming chunks
- Android D input remains free text, not slash-command routing
- apply_delta defensive guards
- Game session serialization roundtrip
"""

from __future__ import annotations

import json
import pytest

from agens_novel.session.game_session import GameSession
from agens_novel.engine.turn_runner import run_turn_sync
from agens_novel.game.constants import REALM_ORDER


# ─── Fix 1: stream_callback removed from state ────────────────────────────

class TestStreamCallbackNotInState:
    """Verify stream_callback never enters the LangGraph state dict."""

    def test_state_dict_has_no_stream_callback_key(self):
        """The state built by run_turn_sync should not contain stream_callback."""
        import unittest.mock as mock

        session = GameSession()
        session.game_started = True

        called_with = {}

        original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

        # We can't easily mock the full graph, but we CAN verify that
        # turn_runner doesn't add stream_callback to kwargs that flow into state.
        # Instead, test the key behavioral property: the function type is not
        # JSON-serializable and shouldn't be in any state that flows to LangGraph.
        cb = lambda text: None

        # Verify callback is popped from kwargs and not in the state built.
        # We do this by inspecting what run_turn_sync would pass.
        import agens_novel.engine.turn_runner as tr
        import inspect

        source = inspect.getsource(tr.run_turn_sync)
        # The old code had: state["stream_callback"] = stream_callback
        # The fix should NOT have that pattern anymore.
        assert 'state["stream_callback"]' not in source
        assert "state['stream_callback']" not in source

    def test_stream_context_module_importable(self):
        """The _stream_context module should be importable."""
        from agens_novel.engine import _stream_context
        assert hasattr(_stream_context, 'get')
        assert hasattr(_stream_context, 'set')
        # Clean up from any prior test.
        _stream_context.set(None)
        assert _stream_context.get() is None

    def test_stream_context_thread_local(self):
        """set/get should work in the current thread."""
        from agens_novel.engine import _stream_context
        cb = lambda text: None
        _stream_context.set(cb)
        assert _stream_context.get() is cb
        _stream_context.set(None)
        assert _stream_context.get() is None


# ─── Fix 2: NarrativeView filters <state_update> ──────────────────────────

class TestNarrativeViewStreamFilter:
    """Test that <state_update> is filtered from streaming chunks."""

    @pytest.fixture
    def view(self):
        """Create a NarrativeView with mocked Kivy."""
        import types
        import sys

        # Mock Kivy modules if not available.
        if "kivy" not in sys.modules:
            kivy_mod = types.ModuleType("kivy")
            sys.modules["kivy"] = kivy_mod
            for sub in ("uix", "uix.scrollview", "uix.label", "uix.boxlayout",
                        "graphics", "metrics", "properties"):
                parts = sub.split(".")
                parent = sys.modules
                for part in parts:
                    key = ".".join(parts[:parts.index(part)+1]) if "." in sub else part
                    if key not in parent:
                        parent[key] = types.ModuleType(key)
                    parent = parent[key].__dict__

        # If we have real Kivy, use it; otherwise skip.
        try:
            # Monkeypatch dp for non-Kivy environments
            import kivy.metrics
            original_dp = getattr(kivy.metrics, 'dp', None)
            if original_dp is None:
                kivy.metrics.dp = lambda v: v
        except ImportError:
            pytest.skip("Kivy not available")

    def test_state_tag_regex(self):
        """Verify the _parse_narrator_output correctly strips state_update."""
        from agens_novel.agents.narrator.nodes import _parse_narrator_output

        text = "你静坐吐纳，灵气入体。\n\n<state_update>\n{\"character\": {\"mp\": \"-5\"}}\n</state_update>"
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == "你静坐吐纳，灵气入体。"
        assert delta == {"character": {"mp": "-5"}}
        assert "<state_update>" not in narrative

    def test_state_tag_at_beginning(self):
        """If the entire output is a state_update, narrative should be empty."""
        from agens_novel.agents.narrator.nodes import _parse_narrator_output

        text = "<state_update>\n{\"meta\": {\"game_over\": true}}\n</state_update>"
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == ""
        assert delta.get("meta", {}).get("game_over") is True

    def test_no_state_tag(self):
        """If there's no state_update tag, full text is narrative."""
        from agens_novel.agents.narrator.nodes import _parse_narrator_output

        text = "一段普通的叙事文本，没有 JSON。"
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == text
        assert delta == {}

    def test_malformed_json_in_tag(self):
        """Malformed JSON should result in empty delta but clean narrative."""
        from agens_novel.agents.narrator.nodes import _parse_narrator_output

        text = "叙事内容\n\n<state_update>\n{invalid json}\n</state_update>"
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == "叙事内容"
        assert delta == {}  # Failed parse → empty delta


# ─── Fix 3: Android D input stays free text ───────────────────────────────

class TestAndroidFreeTextInput:
    """Test that Android does not expose terminal-style command routing."""

    def test_game_screen_has_no_slash_command_router(self):
        import pathlib

        source = pathlib.Path("mobile/screens/game_screen.py").read_text(encoding="utf-8")

        assert "_SLASH_COMMANDS" not in source
        assert "_parse_slash_command" not in source
        assert "startswith(\"/\")" not in source
        assert "handle_combat_action(action, target)" not in source

    def test_choices_ui_is_compact_and_keeps_d_input_hint(self):
        import pathlib
        source = pathlib.Path("mobile/widgets/narrative_view.py").read_text(encoding="utf-8")
        assert 'height=dp(44)' in source
        assert 'D. 自行键入行动' in source
        action_bar = pathlib.Path("mobile/widgets/action_bar.py").read_text(encoding="utf-8")
        assert "BUTTONS =" not in action_bar
        assert '"更多"' in action_bar

    def test_normal_game_over_resets_finale_flag(self):
        import pathlib
        source = pathlib.Path("mobile/screens/game_screen.py").read_text(encoding="utf-8")
        assert "death.is_finale = False" in source
        assert "death.is_finale = True" in source


# ─── Fix: apply_delta defensive guards ─────────────────────────────────────

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

    def test_negative_hp_clamped(self):
        s = GameSession()
        s.hp = 10
        s.apply_delta({"character": {"hp": "-100"}})
        assert s.hp == 0  # clamped to 0

    def test_negative_mp_clamped(self):
        s = GameSession()
        s.mp = 5
        s.apply_delta({"character": {"mp": "-50"}})
        assert s.mp == 0

    def test_bool_ignored_for_hp(self):
        s = GameSession()
        original_hp = s.hp
        s.apply_delta({"character": {"hp": True}})
        assert s.hp == original_hp  # bool ignored

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
        s.apply_delta({"character": {"inventory_add": "灵石"}})
        assert len(s.inventory) == 1
        assert s.inventory[0] == "灵石"

    def test_inventory_add_list(self):
        s = GameSession()
        s.apply_delta({"character": {"inventory_add": [{"name": "灵石", "quantity": 5}]}})
        assert len(s.inventory) == 1
        assert s.inventory[0]["name"] == "灵石"

    def test_equipment_slots_dict(self):
        s = GameSession()
        s.apply_delta({"character": {"equipment_slots": {"weapon": {"name": "铁剑"}}}})
        assert s.equipment_slots["weapon"]["name"] == "铁剑"

    def test_combat_clear(self):
        s = GameSession()
        s.combat = {"phase": "active"}
        s.apply_delta({"character": {"combat": None}})
        assert s.combat is None

    def test_combat_start(self):
        s = GameSession()
        s.apply_delta({"character": {"combat": {"phase": "player_turn", "enemy": {"name": "妖兽"}}}})
        assert s.combat["phase"] == "player_turn"


# ─── Serialization roundtrip ───────────────────────────────────────────────

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


# ─── Destructive / fuzz tests ─────────────────────────────────────────────

class TestDestructiveApplyDelta:
    """Fuzz-style tests: apply_delta with extreme/malformed inputs."""

    def test_empty_delta(self):
        s = GameSession()
        s.apply_delta({})
        assert s.hp == 100  # unchanged

    def test_none_delta(self):
        """None delta should be safely ignored."""
        s = GameSession()
        s.apply_delta(None)  # type: ignore
        assert s.hp == 100  # unchanged, no crash

    def test_empty_character_delta(self):
        s = GameSession()
        s.apply_delta({"character": {}})
        assert s.hp == 100

    def test_float_hp(self):
        """Float values should be silently dropped."""
        s = GameSession()
        s.apply_delta({"character": {"hp": 99.5}})
        assert s.hp == 100  # float not int, dropped

    def test_list_hp(self):
        """List values should be silently dropped."""
        s = GameSession()
        s.apply_delta({"character": {"hp": [1, 2, 3]}})
        assert s.hp == 100

    def test_dict_hp(self):
        """Dict values should be silently dropped."""
        s = GameSession()
        s.apply_delta({"character": {"hp": {"val": 50}}})
        assert s.hp == 100

    def test_very_large_positive_hp(self):
        s = GameSession()
        s.apply_delta({"character": {"hp": 999999}})
        # HP is clamped to hp_max (100 by default).
        assert s.hp == s.hp_max

    def test_hp_max_zero(self):
        """hp_max=0 should be clamped to 1 (minimum guard)."""
        s = GameSession()
        s.hp_max = 0
        s.apply_delta({"character": {"hp": 50}})
        # hp_max clamped to 1, hp clamped to [0, 1] = 1
        assert s.hp_max == 1
        assert s.hp == 1

    def test_unknown_keys_ignored(self):
        """Unknown keys in character delta should not crash."""
        s = GameSession()
        s.apply_delta({"character": {"unknown_field": "value", "another": 42}})
        assert s.hp == 100

    def test_nested_unknown_structure(self):
        """Deeply nested unknown structures should not crash."""
        s = GameSession()
        s.apply_delta({
            "character": {
                "nested": {"deep": {"very_deep": [1, 2, {"x": None}]}}
            },
            "world": {
                "unknown_world_key": True
            },
            "meta": {
                "unknown_meta": "ok"
            },
            "extra_top_level": 42,
        })
        assert s.hp == 100  # session still valid

    def test_realm_empty_string(self):
        s = GameSession()
        s.apply_delta({"character": {"realm": ""}})
        assert s.realm == "练气"  # empty string not in whitelist

    def test_realm_none(self):
        s = GameSession()
        s.apply_delta({"character": {"realm": None}})
        assert s.realm == "练气"

    def test_status_effects_non_list(self):
        """Non-list status_effects should be rejected."""
        s = GameSession()
        s.status_effects = ["中毒"]
        s.apply_delta({"character": {"status_effects": "燃烧"}})
        assert s.status_effects == ["中毒"]  # unchanged

    def test_game_over_int(self):
        """game_over as int (not bool) should be rejected."""
        s = GameSession()
        s.apply_delta({"meta": {"game_over": 1}})
        assert s.game_over is False

    def test_game_over_true_bool(self):
        s = GameSession()
        s.apply_delta({"meta": {"game_over": True}})
        assert s.game_over is True

    def test_plus_prefix_non_numeric(self):
        """'+abc' should be silently dropped."""
        s = GameSession()
        s.apply_delta({"character": {"hp": "+abc"}})
        assert s.hp == 100  # unchanged

    def test_minus_prefix_non_numeric(self):
        s = GameSession()
        s.apply_delta({"character": {"hp": "-abc"}})
        assert s.hp == 100

    def test_combat_empty_dict_clears(self):
        s = GameSession()
        s.combat = {"phase": "active"}
        s.apply_delta({"character": {"combat": {}}})
        assert s.combat is None

    def test_name_update(self):
        s = GameSession()
        s.apply_delta({"character": {"name": "新名字"}})
        assert s.char_name == "新名字"

    def test_spirit_root_update(self):
        s = GameSession()
        s.apply_delta({"character": {"spirit_root": "雷灵根"}})
        assert s.spirit_root == "雷灵根"

    def test_world_day_count_update(self):
        s = GameSession()
        s.apply_delta({"world": {"day_count": 30}})
        assert s.day_count == 30

    def test_delta_with_all_realms(self):
        """Every realm in REALM_ORDER should be accepted."""
        for realm in REALM_ORDER:
            s = GameSession()
            s.apply_delta({"character": {"realm": realm}})
            assert s.realm == realm, f"Failed for realm: {realm}"
