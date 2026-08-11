"""Deterministic randomness for rule-owned game outcomes.

LLM calls, retries, and Judge reviews must never consume rule randomness.  A
turn therefore derives every draw from the persisted run seed, rule counter,
and a stable stream name instead of sharing process-global ``random`` state.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuleRng:
    """Stateless deterministic draws for one persisted rule counter."""

    run_seed: str
    counter: int

    def random(self, stream: str) -> float:
        """Return a stable value in ``[0.0, 1.0)`` for a named stream."""
        payload = f"{self.run_seed}|{self.counter}|{stream}".encode()
        value = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
        return value / float(2**64)

    def randint(self, lower: int, upper: int, stream: str) -> int:
        """Return an inclusive deterministic integer for a named stream."""
        if lower > upper:
            raise ValueError("lower must not exceed upper")
        return lower + int(self.random(stream) * (upper - lower + 1))


def new_run_seed() -> str:
    """Create a non-secret, persisted seed for a new local game run."""
    validation_seed = os.environ.get("AGENS_VALIDATION_SEED", "").strip()
    if validation_seed:
        return validation_seed
    return secrets.token_hex(16)


def new_run_validation_mode() -> str:
    """Capture validation-only rule behavior when a new run is created.

    The environment variable is intentionally read only at run creation.  Its
    resulting mode is stored in the session so save/load and rule-only replay
    do not depend on the environment of the process doing the replay.
    """
    return "golden_route" if os.environ.get("AGENS_VALIDATION_SEED", "").strip() else ""


def rule_rng_for_session(session: Any) -> RuleRng | None:
    """Return the persisted RNG for a session, or ``None`` for legacy saves.

    Unseeded snapshots predate deterministic rules.  Callers retain their
    legacy behavior only for those snapshots; every new or subsequently loaded
    run receives a persisted seed before it can be advanced.
    """
    seed = str(getattr(session, "run_seed", "") or "").strip()
    if not seed:
        return None
    raw_counter = getattr(session, "rule_rng_counter", 0)
    counter = raw_counter if isinstance(raw_counter, int) and not isinstance(raw_counter, bool) else 0
    return RuleRng(seed, max(0, counter))
