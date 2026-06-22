"""add game-mode v5 run, turn, and progress tables"""

from __future__ import annotations

from alembic import op

revision = "20260622_0003"
down_revision = "20260621_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS game_runs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            session_id TEXT NOT NULL DEFAULT '',
            char_name TEXT NOT NULL DEFAULT '',
            realm TEXT NOT NULL DEFAULT '',
            death_cause TEXT NOT NULL DEFAULT '',
            ascended BOOLEAN NOT NULL DEFAULT FALSE,
            turn_count INTEGER NOT NULL DEFAULT 0,
            finished_at DOUBLE PRECISION NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS game_turns (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            turn_no INTEGER NOT NULL,
            start_age INTEGER NOT NULL,
            elapsed_years INTEGER NOT NULL,
            end_age INTEGER NOT NULL,
            lifespan INTEGER NOT NULL,
            remaining_lifespan INTEGER NOT NULL,
            choice_taken TEXT,
            choices JSONB NOT NULL DEFAULT '[]'::jsonb,
            state_delta JSONB NOT NULL DEFAULT '{}'::jsonb,
            state_after JSONB NOT NULL DEFAULT '{}'::jsonb,
            calendar_summary TEXT NOT NULL DEFAULT '',
            narrative TEXT NOT NULL DEFAULT '',
            event_kind TEXT NOT NULL DEFAULT 'event',
            end_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(run_id, turn_no)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS player_progress (
            user_id TEXT PRIMARY KEY REFERENCES users(id),
            runs_completed INTEGER NOT NULL DEFAULT 0,
            ascension_count INTEGER NOT NULL DEFAULT 0,
            updated_at DOUBLE PRECISION NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.drop_table("player_progress", if_exists=True)
    op.drop_table("game_turns", if_exists=True)
    op.drop_table("game_runs", if_exists=True)
