"""Tests for state reducers — apply_combat_delta and list reducers."""

from __future__ import annotations

import pytest

from agens_novel.state.reducers import apply_combat_delta, last_wins, Append, ReplaceList


class TestApplyCombatDelta:
    """Test apply_combat_delta reducer."""

    def test_new_combat_replaces_none(self):
        result = apply_combat_delta(None, {"phase": "player_turn"})
        assert result == {"phase": "player_turn"}

    def test_new_combat_replaces_existing(self):
        result = apply_combat_delta({"phase": "idle"}, {"phase": "player_turn"})
        assert result == {"phase": "player_turn"}

    def test_empty_new_keeps_existing(self):
        result = apply_combat_delta({"phase": "player_turn"}, {})
        assert result == {"phase": "player_turn"}

    def test_reset_clears_combat(self):
        result = apply_combat_delta({"phase": "player_turn", "enemy": {"hp": 50}}, {"_reset": True})
        assert result == {}

    def test_none_existing_empty_new(self):
        result = apply_combat_delta(None, {})
        assert result == {}


class TestLastWins:
    """Test last_wins reducer."""

    def test_new_replaces(self):
        result = last_wins(["old"], ["new"])
        assert result == ["new"]

    def test_empty_new_keeps_existing(self):
        result = last_wins(["old"], [])
        assert result == ["old"]

    def test_none_existing(self):
        result = last_wins(None, ["new"])
        assert result == ["new"]

    def test_both_empty(self):
        result = last_wins([], [])
        assert result == []
