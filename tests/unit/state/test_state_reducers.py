"""Tests for state reducers: last_wins and apply_combat_delta."""

from __future__ import annotations

from agens_novel.state.reducers import apply_combat_delta, last_wins


# ─── last_wins ────────────────────────────────────────────────────────────


def test_last_wins_replaces() -> None:
    """New non-empty list replaces the existing list."""
    assert last_wins(["a", "b"], ["c"]) == ["c"]


def test_last_wins_keeps_existing_when_none() -> None:
    """Empty new list keeps the existing list unchanged."""
    assert last_wins(["a", "b"], []) == ["a", "b"]


def test_last_wins_handles_empty_existing() -> None:
    """Empty existing list with non-empty new list returns the new list."""
    assert last_wins([], ["x"]) == ["x"]


def test_last_wins_new_replaces() -> None:
    """Last-wins semantics: new value fully replaces old."""
    assert last_wins(["old"], ["new"]) == ["new"]


def test_last_wins_empty_new_keeps_existing() -> None:
    """Empty new list keeps the old list."""
    assert last_wins(["old"], []) == ["old"]


def test_last_wins_none_existing() -> None:
    """None existing list with non-empty new list returns the new list."""
    assert last_wins(None, ["new"]) == ["new"]


def test_last_wins_both_empty() -> None:
    """Two empty lists return an empty list."""
    assert last_wins([], []) == []


# ─── apply_combat_delta ──────────────────────────────────────────────────


def test_apply_combat_delta_replaces_none() -> None:
    """apply_combat_delta with None existing returns the new combat dict."""
    assert apply_combat_delta(None, {"phase": "player_turn"}) == {"phase": "player_turn"}


def test_apply_combat_delta_replaces_existing() -> None:
    """apply_combat_delta with non-empty new dict replaces the old dict."""
    assert apply_combat_delta({"phase": "idle"}, {"phase": "player_turn"}) == {
        "phase": "player_turn"
    }


def test_apply_combat_delta_empty_new_keeps_existing() -> None:
    """apply_combat_delta with empty new dict keeps the existing dict."""
    assert apply_combat_delta({"phase": "player_turn"}, {}) == {"phase": "player_turn"}


def test_apply_combat_delta_reset_clears_combat() -> None:
    """apply_combat_delta with _reset=True clears the combat state."""
    assert apply_combat_delta(
        {"phase": "player_turn", "enemy": {"hp": 50}}, {"_reset": True}
    ) == {}


def test_apply_combat_delta_none_existing_empty_new() -> None:
    """apply_combat_delta with None existing and empty new returns empty dict."""
    assert apply_combat_delta(None, {}) == {}
