"""Death-reward repository extracted from PostgresWebDatabase.

Holds the public-API run-achievement, account-reward and legacy-bonus SQL.
``PostgresWebDatabase`` delegates the public reward methods here; its API
(``WebDatabaseProtocol``) and on-disk schema are unchanged. The terminal
settlement path (``_finalize_terminal``) keeps its own inline writes to the
same tables because they must run inside the session-mutation transaction
with ``ON CONFLICT DO NOTHING`` idempotency.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .database_common import now_ts


class RewardsRepository:
    """Persist run achievements, account rewards and legacy bonuses."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def save_run_achievement(
        self,
        user_id: str,
        session_id: str,
        achievement_key: str,
        achievement_name: str,
        description: str,
        death_cause: str,
    ) -> dict[str, Any]:
        achievement_id = str(uuid.uuid4())
        now = now_ts()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO run_achievements
                        (id, user_id, session_id, achievement_key, achievement_name,
                         description, death_cause, achieved_at)
                    VALUES
                        (:id, :user_id, :session_id, :achievement_key, :achievement_name,
                         :description, :death_cause, :achieved_at)
                    """
                ),
                {
                    "id": achievement_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "achievement_key": achievement_key,
                    "achievement_name": achievement_name,
                    "description": description,
                    "death_cause": death_cause,
                    "achieved_at": now,
                },
            )
        return {
            "id": achievement_id,
            "user_id": user_id,
            "session_id": session_id,
            "achievement_key": achievement_key,
            "achievement_name": achievement_name,
            "description": description,
            "death_cause": death_cause,
            "achieved_at": now,
        }

    def list_run_achievements(self, user_id: str, session_id: str = "") -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            if session_id:
                rows = conn.execute(
                    text(
                        """
                        SELECT * FROM run_achievements
                        WHERE user_id = :user_id AND session_id = :session_id
                        ORDER BY achieved_at
                        """
                    ),
                    {"user_id": user_id, "session_id": session_id},
                ).mappings().all()
            else:
                rows = conn.execute(
                    text(
                        """
                        SELECT * FROM run_achievements
                        WHERE user_id = :user_id
                        ORDER BY achieved_at DESC
                        """
                    ),
                    {"user_id": user_id},
                ).mappings().all()
        return [dict(row) for row in rows]

    def save_account_reward(
        self,
        user_id: str,
        reward_type: str,
        reward_value: str,
        label: str,
        source_session_id: str,
    ) -> dict[str, Any]:
        reward_id = str(uuid.uuid4())
        now = now_ts()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO account_rewards
                        (id, user_id, reward_type, reward_value, label,
                         source_session_id, granted_at)
                    VALUES
                        (:id, :user_id, :reward_type, :reward_value, :label,
                         :source_session_id, :granted_at)
                    """
                ),
                {
                    "id": reward_id,
                    "user_id": user_id,
                    "reward_type": reward_type,
                    "reward_value": str(reward_value),
                    "label": label,
                    "source_session_id": source_session_id,
                    "granted_at": now,
                },
            )
        return {
            "id": reward_id,
            "user_id": user_id,
            "reward_type": reward_type,
            "reward_value": str(reward_value),
            "label": label,
            "source_session_id": source_session_id,
            "granted_at": now,
        }

    def list_account_rewards(self, user_id: str) -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM account_rewards
                    WHERE user_id = :user_id
                    ORDER BY granted_at DESC
                    """
                ),
                {"user_id": user_id},
            ).mappings().all()
        return [dict(row) for row in rows]

    def save_legacy_bonus(
        self,
        user_id: str,
        bonus_type: str,
        bonus_value: str,
        label: str,
        source_session_id: str,
        runs_remaining: int = 1,
    ) -> dict[str, Any]:
        bonus_id = str(uuid.uuid4())
        now = now_ts()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO legacy_bonuses
                        (id, user_id, bonus_type, bonus_value, label,
                         runs_remaining, source_session_id, granted_at)
                    VALUES
                        (:id, :user_id, :bonus_type, :bonus_value, :label,
                         :runs_remaining, :source_session_id, :granted_at)
                    """
                ),
                {
                    "id": bonus_id,
                    "user_id": user_id,
                    "bonus_type": bonus_type,
                    "bonus_value": str(bonus_value),
                    "label": label,
                    "runs_remaining": int(runs_remaining),
                    "source_session_id": source_session_id,
                    "granted_at": now,
                },
            )
        return {
            "id": bonus_id,
            "user_id": user_id,
            "bonus_type": bonus_type,
            "bonus_value": str(bonus_value),
            "label": label,
            "runs_remaining": int(runs_remaining),
            "source_session_id": source_session_id,
            "granted_at": now,
        }

    def list_legacy_bonuses(self, user_id: str) -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM legacy_bonuses
                    WHERE user_id = :user_id AND runs_remaining > 0
                    ORDER BY granted_at
                    """
                ),
                {"user_id": user_id},
            ).mappings().all()
        return [dict(row) for row in rows]

    def consume_legacy_bonuses(self, user_id: str) -> int:
        """Decrement runs_remaining for all bonuses owned by the user."""
        consumed = 0
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, runs_remaining FROM legacy_bonuses
                    WHERE user_id = :user_id AND runs_remaining > 0
                    """
                ),
                {"user_id": user_id},
            ).mappings().all()
            for row in rows:
                remaining = int(row["runs_remaining"]) - 1
                if remaining <= 0:
                    conn.execute(
                        text("UPDATE legacy_bonuses SET runs_remaining = 0 WHERE id = :id"),
                        {"id": row["id"]},
                    )
                    consumed += 1
                else:
                    conn.execute(
                        text(
                            "UPDATE legacy_bonuses SET runs_remaining = :r WHERE id = :id"
                        ),
                        {"r": remaining, "id": row["id"]},
                    )
        return consumed
