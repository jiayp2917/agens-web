"""Helpers for keeping model chat history bounded."""

from __future__ import annotations

from typing import Any


def compact_chat_history(history: list[dict[str, Any]], *, max_entries: int = 20) -> list[dict[str, Any]]:
    """Keep opening context plus the most recent entries within ``max_entries``."""
    if len(history) <= max_entries:
        return history
    if max_entries <= 0:
        return []
    first = history[0]
    recent_count = max(0, max_entries - 1)
    recent = history[-recent_count:] if recent_count else []
    return [first, *recent]
