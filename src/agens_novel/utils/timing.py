"""Time helpers."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow_iso() -> str:
    """ISO-8601 UTC timestamp (e.g. 2026-06-11T08:30:00Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utcnow_compact() -> str:
    """Filesystem-friendly UTC timestamp (e.g. 2026-06-11T08-30-00Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
