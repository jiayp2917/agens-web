"""Tests for state reducers."""

from __future__ import annotations

from agens_novel.state.reducers import last_wins


def test_last_wins_replaces_with_non_empty_list() -> None:
    assert last_wins(["old"], ["new"]) == ["new"]


def test_last_wins_keeps_existing_on_empty_list() -> None:
    assert last_wins(["old"], []) == ["old"]


def test_last_wins_empty_existing_empty_new() -> None:
    assert last_wins([], []) == []


def test_last_wins_none_existing_empty_new() -> None:
    assert last_wins(None, []) == []
