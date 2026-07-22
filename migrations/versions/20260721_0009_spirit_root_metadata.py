"""add spirit-root catalog presentation metadata"""

from __future__ import annotations

from alembic import op

revision = "20260721_0009"
down_revision = "20260710_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE catalog_spirit_roots "
        "ADD COLUMN IF NOT EXISTS rarity TEXT NOT NULL DEFAULT '普通'"
    )
    op.execute(
        "ALTER TABLE catalog_spirit_roots "
        "ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT ''"
    )
    op.execute("COMMENT ON COLUMN catalog_spirit_roots.rarity IS '稀有度。'")
    op.execute("COMMENT ON COLUMN catalog_spirit_roots.description IS '灵根描述。'")


def downgrade() -> None:
    op.execute("ALTER TABLE catalog_spirit_roots DROP COLUMN IF EXISTS description")
    op.execute("ALTER TABLE catalog_spirit_roots DROP COLUMN IF EXISTS rarity")
