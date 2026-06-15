"""Destructive / fuzz-style tests for GameSession.apply_delta.

These tests probe ``apply_delta`` with extreme and malformed inputs to
verify it never raises and never leaves the session in a corrupt state.

Marked as ``destructive`` so they can be deselected in fast CI runs.
"""

from __future__ import annotations

import pytest

from agens_novel.game.constants import REALM_ORDER
from agens_novel.session.game_session import GameSession

pytestmark = pytest.mark.destructive


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
