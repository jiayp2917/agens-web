"""add user scoped encrypted model configs"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260622_0005"
down_revision = "20260622_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    model_config_columns = {column["name"] for column in inspector.get_columns("model_config")}
    if "api_key_encrypted" not in model_config_columns:
        op.add_column(
            "model_config",
            sa.Column("api_key_encrypted", sa.Text(), nullable=False, server_default=""),
        )
    if not inspector.has_table("user_model_configs"):
        op.create_table(
            "user_model_configs",
            sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("provider", sa.Text(), nullable=False),
            sa.Column("base_url", sa.Text(), nullable=False),
            sa.Column("model", sa.Text(), nullable=False),
            sa.Column("api_key_masked", sa.Text(), nullable=False),
            sa.Column("api_key_set", sa.Boolean(), nullable=False),
            sa.Column("api_key_encrypted", sa.Text(), nullable=False, server_default=""),
            sa.Column("updated_at", sa.Float(), nullable=False),
        )
    op.alter_column("model_config", "api_key_encrypted", server_default=None)
    op.alter_column("user_model_configs", "api_key_encrypted", server_default=None)


def downgrade() -> None:
    op.drop_table("user_model_configs")
    op.drop_column("model_config", "api_key_encrypted")
