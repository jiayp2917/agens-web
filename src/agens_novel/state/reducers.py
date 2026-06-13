"""Reducer functions for LangGraph Annotated state fields."""

from __future__ import annotations

from operator import add
from typing import Annotated


def last_wins(existing: list, new: list) -> list:
    """Reducer that returns only the latest value (replaces, doesn't append).

    Useful for "current X" fields where history is irrelevant.

    Semantics:
      * If new is a non-empty list → return new (replace).
      * If new is an empty list   → keep existing (do not clobber).
    """
    if new:
        return new
    return existing or []


# Convenience: Annotated alias used in state schemas.
Append = Annotated[list, add]
ReplaceList = Annotated[list, last_wins]


def apply_combat_delta(existing: dict | None, new: dict) -> dict:
    """Reducer for combat state: replaces entirely when new is provided.

    If new is an empty dict, keeps existing. If new contains a special
    key ``_reset`` set to True, returns an empty dict (clears combat).
    """
    if new.get("_reset"):
        return {}
    if new:
        return new
    return existing or {}
