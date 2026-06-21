"""initial PostgreSQL web schema"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260621_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("username", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "invite_codes",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("code_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("role", sa.Text(), nullable=False, server_default="user"),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("uses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.Float(), nullable=True),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("created_by", sa.Text(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("events", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "saves",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("events", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_saves_user_name"),
    )
    op.create_table(
        "model_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("api_key_masked", sa.Text(), nullable=False),
        sa.Column("api_key_set", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_model_config_singleton"),
    )
    op.create_table(
        "catalog_talents",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("rarity", sa.Text(), nullable=False, server_default="普通"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "attribute_mods",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.Float(),
            nullable=False,
            server_default=sa.text("EXTRACT(EPOCH FROM now())"),
        ),
    )
    op.create_table(
        "catalog_family_backgrounds",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("rarity", sa.Text(), nullable=False, server_default="普通"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "initial_resources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "initial_risks",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "story_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.Float(),
            nullable=False,
            server_default=sa.text("EXTRACT(EPOCH FROM now())"),
        ),
    )
    op.create_table(
        "catalog_spirit_roots",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("element", sa.Text(), nullable=False, server_default=""),
        sa.Column("grade", sa.Text(), nullable=False, server_default="地"),
        sa.Column("cultivation_bonus", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("breakthrough_bonus", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("cultivation_tendency", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "event_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.Float(),
            nullable=False,
            server_default=sa.text("EXTRACT(EPOCH FROM now())"),
        ),
    )
    op.create_table(
        "catalog_difficulties",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("risk_multiplier", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("reward_multiplier", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("lifespan_modifier", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("luck_modifier", sa.Float(), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.Float(),
            nullable=False,
            server_default=sa.text("EXTRACT(EPOCH FROM now())"),
        ),
    )
    op.create_table(
        "catalog_story_seeds",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.Float(),
            nullable=False,
            server_default=sa.text("EXTRACT(EPOCH FROM now())"),
        ),
    )
    op.create_table(
        "run_achievements",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("achievement_key", sa.Text(), nullable=False),
        sa.Column("achievement_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("death_cause", sa.Text(), nullable=False, server_default=""),
        sa.Column("achieved_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "account_rewards",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reward_type", sa.Text(), nullable=False),
        sa.Column("reward_value", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_session_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("granted_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "legacy_bonuses",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("bonus_type", sa.Text(), nullable=False),
        sa.Column("bonus_value", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False, server_default=""),
        sa.Column("runs_remaining", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_session_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("granted_at", sa.Float(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("legacy_bonuses")
    op.drop_table("account_rewards")
    op.drop_table("run_achievements")
    op.drop_table("catalog_story_seeds")
    op.drop_table("catalog_difficulties")
    op.drop_table("catalog_spirit_roots")
    op.drop_table("catalog_family_backgrounds")
    op.drop_table("catalog_talents")
    op.drop_table("model_config")
    op.drop_table("saves")
    op.drop_table("sessions")
    op.drop_table("invite_codes")
    op.drop_table("users")
