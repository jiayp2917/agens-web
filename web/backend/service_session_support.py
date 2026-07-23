"""Shared session identity and expiry helpers for web service use cases."""

from __future__ import annotations

import os
import time

GUEST_USER_PREFIX = "guest:"


def is_guest_user_id(user_id: str | None) -> bool:
    return bool(user_id and user_id.startswith(GUEST_USER_PREFIX))


def guest_expiry() -> float:
    try:
        ttl = int(os.environ.get("AGENS_GUEST_SESSION_TTL_SECONDS", "86400"))
    except ValueError:
        ttl = 86400
    return time.time() + max(300, ttl)
