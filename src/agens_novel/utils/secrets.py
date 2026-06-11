"""Secret masking utilities — used in repr, logging, and CLI display."""

from __future__ import annotations


def mask(value: str | None) -> str:
    """Return a short masked preview of a secret value."""
    if not value:
        return "<unset>"
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}***{value[-4:]}"
