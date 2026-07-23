"""Small string helpers that do not depend on game state or engine flows."""

from __future__ import annotations

from typing import Any


def dedupe_strings(values: list[Any]) -> list[str]:
    """Return unique non-empty strings while preserving order."""
    out: list[str] = []
    for value in values:
        text = value.strip() if isinstance(value, str) else ""
        if text and text not in out:
            out.append(text)
    return out
