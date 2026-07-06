"""Death-rewards persistence and lookup extracted from WebGameService.

Owns the DB read/write for run achievements, account rewards, and legacy
bonuses. WebGameService keeps the ``death_summary`` orchestration because it
depends on the live runner resolver; this module handles the stateless rows.
"""

from __future__ import annotations

from typing import Any

from agens_novel.engine.death_rewards import bonuses_to_legacy
from agens_novel.session.game_session import GameSession

from .database import WebDatabaseProtocol

_GUEST_PREFIX = "guest:"


class DeathRewardsService:
    """Read persisted achievements/rewards and write new death-reward rows."""

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
        headline_parts = [a.get("achievement_name") for a in achievements[:3] if a.get("achievement_name")]
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

    def persist(
        self,
        session: GameSession,
        user_id: str,
        session_id: str,
        summary: dict[str, Any],
    ) -> None:
        """Write achievements, account rewards, and legacy bonuses to the DB."""
        existing_rewards = [
            reward
            for reward in self.db.list_account_rewards(user_id)
            if reward.get("source_session_id") == session_id
        ]
        if self.db.list_run_achievements(user_id, session_id) or existing_rewards:
            return
        self.db.record_game_run(
            user_id=user_id,
            run_id=session_id,
            session_id=session_id,
            char_name=session.char_name,
            realm=session.realm,
            death_cause=str(summary.get("death_cause") or ""),
            ascended=bool(session.finale),
            turn_count=int(session.turn_count or 0),
        )
        for achievement in summary.get("achievements", []) or []:
            self.db.save_run_achievement(
                user_id=user_id,
                session_id=session_id,
                achievement_key=str(achievement.get("key") or ""),
                achievement_name=str(achievement.get("name") or ""),
                description=str(achievement.get("description") or ""),
                death_cause=str(summary.get("death_cause") or ""),
            )
        for reward in summary.get("rewards", []) or []:
            self.db.save_account_reward(
                user_id=user_id,
                reward_type=str(reward.get("type") or ""),
                reward_value=str(reward.get("value") or ""),
                label=str(reward.get("label") or ""),
                source_session_id=session_id,
            )
        for bonus in bonuses_to_legacy(summary.get("rewards", []) or []):
            self.db.save_legacy_bonus(
                user_id=user_id,
                bonus_type=str(bonus.get("bonus_type") or ""),
                bonus_value=str(bonus.get("bonus_value") or ""),
                label=str(bonus.get("label") or ""),
                source_session_id=session_id,
                runs_remaining=int(bonus.get("runs_remaining") or 1),
            )

    def legacy_bonuses(self, user_id: str) -> list[dict[str, Any]]:
        if not user_id or user_id.startswith(_GUEST_PREFIX):
            return []
        return self.db.list_legacy_bonuses(user_id)
