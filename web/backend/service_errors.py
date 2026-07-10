from __future__ import annotations


class SessionVersionConflict(RuntimeError):
    """Raised when a session mutation is based on stale state."""


class DuplicateUsername(ValueError):
    """Raised when registration races with an existing username."""


class InvalidInvite(ValueError):
    """Raised when an invite cannot be consumed atomically."""
