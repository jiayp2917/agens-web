"""bridge catalog and reward tables for already-applied 0001 revisions"""

from __future__ import annotations

from alembic import op

revision = "20260621_0002"
down_revision = "20260621_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Some production databases already applied the original 0001 before these
    # tables were added to it. Fresh databases get them from 0001; this bridge
    # makes existing databases catch up without failing on fresh installs.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_talents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            rarity TEXT NOT NULL DEFAULT '普通',
            description TEXT NOT NULL DEFAULT '',
            attribute_mods JSONB NOT NULL DEFAULT '{}'::jsonb,
            tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now())
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_family_backgrounds (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            rarity TEXT NOT NULL DEFAULT '普通',
            description TEXT NOT NULL DEFAULT '',
            initial_resources JSONB NOT NULL DEFAULT '{}'::jsonb,
            initial_risks JSONB NOT NULL DEFAULT '[]'::jsonb,
            story_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now())
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_spirit_roots (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            element TEXT NOT NULL DEFAULT '',
            grade TEXT NOT NULL DEFAULT '地',
            cultivation_bonus DOUBLE PRECISION NOT NULL DEFAULT 1.0,
            breakthrough_bonus DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            cultivation_tendency TEXT NOT NULL DEFAULT '',
            event_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now())
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_difficulties (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            risk_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
            reward_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
            lifespan_modifier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
            luck_modifier DOUBLE PRECISION NOT NULL DEFAULT 0,
            description TEXT NOT NULL DEFAULT '',
            created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now())
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_story_seeds (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now())
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS run_achievements (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            session_id TEXT NOT NULL,
            achievement_key TEXT NOT NULL,
            achievement_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            death_cause TEXT NOT NULL DEFAULT '',
            achieved_at DOUBLE PRECISION NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS account_rewards (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            reward_type TEXT NOT NULL,
            reward_value TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            source_session_id TEXT NOT NULL DEFAULT '',
            granted_at DOUBLE PRECISION NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS legacy_bonuses (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            bonus_type TEXT NOT NULL,
            bonus_value TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            runs_remaining INTEGER NOT NULL DEFAULT 1,
            source_session_id TEXT NOT NULL DEFAULT '',
            granted_at DOUBLE PRECISION NOT NULL
        )
        """
    )


def downgrade() -> None:
    # No-op by design: current 0001 owns these tables on fresh databases, while
    # this bridge only repairs databases that applied an older 0001 revision.
    pass
