"""document production DDL policy (no-op migration)

P3 DDL demotion: ``AGENS_ENV=production`` disables ``PostgresWebDatabase.initialize()``.
The production schema is owned by alembic; auto-DDL at runtime would silently
mutate it. This migration is a marker so operators have a named revision to
point at when running ``alembic upgrade head`` in production.

No schema changes — alembic_version is bumped so the policy is observable in
the migration history.
"""

from __future__ import annotations

revision = "20260622_0004"
down_revision = "20260622_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass