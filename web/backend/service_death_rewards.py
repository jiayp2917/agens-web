"""Death-rewards persistence and lookup extracted from WebGameService.

Owns the DB read/write for run achievements, account rewards, and legacy
bonuses. WebGameService keeps the ``death_summary`` orchestration because it
depends on the live runner resolver; this module handles the stateless rows.
"""

from __future__ import annotations

from typing import Any

from .database import WebDatabaseProtocol

_GUEST_PREFIX = "guest:"


class DeathRewardsService:
    """Read persisted achievements, rewards, and legacy bonuses."""

    def __init__(self, db: WebDatabaseProtocol) -> None:
        self.db = db

    def stored_summary(self, session_id: str, user_id: str) -> dict[str, Any]:
        achievements = self.db.list_run_achievements(user_id, session_id)
        rewards = [
            r
            for r in self.db.list_account_rewards(user_id)
            if r.get("source_session_id") == session_id
        ]
        if not achievements and not rewards:
            return {"session_id": session_id, "is_guest": False, "summary": {}}
        death_cause = achievements[0].get("death_cause", "") if achievements else ""
        headline_parts = [
            str(a["achievement_name"])
            for a in achievements[:3]
            if a.get("achievement_name")
        ]
        headline = "、".join(headline_parts) if headline_parts else ""
        return {
            "session_id": session_id,
            "is_guest": False,
            "summary": {
                "death_cause": death_cause,
                "achievements": [
                    {
                        "key": a.get("achievement_key", ""),
                        "name": a.get("achievement_name", ""),
                        "description": a.get("description", ""),
                    }
                    for a in achievements
                ],
                "rewards": [
                    {
                        "type": r.get("reward_type", ""),
                        "value": r.get("reward_value", ""),
                        "label": r.get("label", ""),
                    }
                    for r in rewards
                ],
                "headline": headline,
            },
        }

    def legacy_bonuses(self, user_id: str) -> list[dict[str, Any]]:
        if not user_id or user_id.startswith(_GUEST_PREFIX):
            return []
        return self.db.list_legacy_bonuses(user_id)
