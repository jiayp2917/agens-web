"""Summary helpers for web game sessions."""

from __future__ import annotations

from typing import Any

from agens_novel.engine.death_rewards import (
    build_run_summary,
    categorize_death,
    compute_rewards,
    evaluate_achievements,
)
from agens_novel.session.game_session import GameSession


def build_death_summary(session: GameSession) -> dict[str, Any] | None:
    """Evaluate achievements + rewards for a finished run."""
    if not session.game_over:
        return None
    death_cause = categorize_death(session)
    achievements = evaluate_achievements(session)
    rewards = compute_rewards(achievements, session)
    return build_run_summary(session, achievements, rewards, death_cause)
