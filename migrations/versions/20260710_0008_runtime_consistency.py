"""add runtime consistency, guest persistence, and idempotency guards"""

from __future__ import annotations

from alembic import op

revision = "20260710_0008"
down_revision = "20260705_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sessions ALTER COLUMN user_id DROP NOT NULL")
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS guest_token_hash TEXT")
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS expires_at DOUBLE PRECISION")
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 0")
    op.execute(
        """
        ALTER TABLE sessions
        ADD CONSTRAINT ck_sessions_owner
        CHECK ((user_id IS NOT NULL) <> (guest_token_hash IS NOT NULL))
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_sessions_guest_expiry ON sessions(expires_at)")

    op.execute("ALTER TABLE game_runs ADD COLUMN IF NOT EXISTS started_at DOUBLE PRECISION")
    op.execute("ALTER TABLE game_runs ADD COLUMN IF NOT EXISTS completed BOOLEAN NOT NULL DEFAULT TRUE")
    op.execute("ALTER TABLE game_runs ALTER COLUMN finished_at DROP NOT NULL")
    op.execute("UPDATE game_runs SET started_at = COALESCE(started_at, finished_at)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_game_runs_session ON game_runs(session_id) WHERE session_id <> ''"
    )

    op.execute(
        """
        INSERT INTO game_runs
            (id, user_id, session_id, char_name, realm, death_cause, ascended,
             turn_count, started_at, finished_at, completed)
        SELECT DISTINCT ON (t.run_id)
            t.run_id,
            s.user_id,
            s.id,
            COALESCE(s.snapshot->'character'->>'name', ''),
            COALESCE(s.snapshot->'character'->>'realm', ''),
            '', FALSE,
            COALESCE((s.snapshot->>'turn_count')::INTEGER, 0),
            s.created_at,
            NULL,
            FALSE
        FROM game_turns t
        JOIN sessions s ON s.id = t.run_id
        WHERE s.user_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM game_runs r WHERE r.id = t.run_id)
        ORDER BY t.run_id, t.turn_no
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM game_turns t
                LEFT JOIN game_runs r ON r.id = t.run_id
                WHERE r.id IS NULL
            ) THEN
                RAISE EXCEPTION 'orphan game_turns prevent runtime consistency migration';
            END IF;
        END $$
        """
    )
    op.execute("ALTER TABLE game_turns ADD COLUMN IF NOT EXISTS request_id TEXT")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_game_turns_request ON game_turns(run_id, request_id) WHERE request_id IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE game_turns ADD CONSTRAINT fk_game_turns_run FOREIGN KEY (run_id) REFERENCES game_runs(id) ON DELETE CASCADE"
    )

    op.execute(
        """
        CREATE TABLE session_mutations (
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            request_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            expected_version INTEGER NOT NULL,
            result_version INTEGER NOT NULL,
            response JSONB NOT NULL,
            created_at DOUBLE PRECISION NOT NULL,
            PRIMARY KEY (session_id, request_id)
        )
        """
    )

    _assert_no_duplicates(
        "run_achievements",
        "user_id, session_id, achievement_key",
    )
    _assert_no_duplicates(
        "account_rewards",
        "user_id, source_session_id, reward_type, reward_value",
    )
    _assert_no_duplicates(
        "legacy_bonuses",
        "user_id, source_session_id, bonus_type, bonus_value",
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_run_achievement_business ON run_achievements(user_id, session_id, achievement_key)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_account_reward_business ON account_rewards(user_id, source_session_id, reward_type, reward_value)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_legacy_bonus_business ON legacy_bonuses(user_id, source_session_id, bonus_type, bonus_value)"
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM sessions WHERE user_id IS NULL)
               OR EXISTS (SELECT 1 FROM game_runs WHERE finished_at IS NULL) THEN
                RAISE EXCEPTION 'guest sessions or active runs prevent runtime consistency downgrade';
            END IF;
        END $$
        """
    )
    op.drop_index("uq_legacy_bonus_business", table_name="legacy_bonuses")
    op.drop_index("uq_account_reward_business", table_name="account_rewards")
    op.drop_index("uq_run_achievement_business", table_name="run_achievements")
    op.drop_table("session_mutations")
    op.drop_constraint("fk_game_turns_run", "game_turns", type_="foreignkey")
    op.drop_index("uq_game_turns_request", table_name="game_turns")
    op.drop_column("game_turns", "request_id")
    op.drop_index("uq_game_runs_session", table_name="game_runs")
    op.execute("ALTER TABLE game_runs ALTER COLUMN finished_at SET NOT NULL")
    op.drop_column("game_runs", "completed")
    op.drop_column("game_runs", "started_at")
    op.drop_constraint("ck_sessions_owner", "sessions", type_="check")
    op.drop_index("ix_sessions_guest_expiry", table_name="sessions")
    op.drop_column("sessions", "version")
    op.drop_column("sessions", "expires_at")
    op.drop_column("sessions", "guest_token_hash")
    op.execute("ALTER TABLE sessions ALTER COLUMN user_id SET NOT NULL")


def _assert_no_duplicates(table: str, columns: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM {table}
                GROUP BY {columns}
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'duplicate business rows in {table} prevent migration';
            END IF;
        END $$
        """
    )
