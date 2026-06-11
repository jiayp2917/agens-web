"""State reducers: Append vs ReplaceList."""

from __future__ import annotations

from agens_novel.state.reducers import last_wins


def test_last_wins_replaces() -> None:
    assert last_wins(["a", "b"], ["c"]) == ["c"]


def test_last_wins_keeps_existing_when_none() -> None:
    assert last_wins(["a", "b"], []) == ["a", "b"]


def test_last_wins_handles_empty_existing() -> None:
    assert last_wins([], ["x"]) == ["x"]
