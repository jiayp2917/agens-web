"""Web test DB isolation.

After the Option C consolidation the web layer is PostgreSQL-only, so every
web test runs against a single shared test database (TEST_DATABASE_URL).
This autouse fixture truncates all application tables before each test for
isolation; each test's ``create_app()`` then re-seeds catalogs on startup.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text

# All application tables (alembic_version is intentionally excluded).
_TEST_TABLES = (
    "users",
    "invite_codes",
    "sessions",
    "saves",
    "model_config",
    "catalog_talents",
    "catalog_family_backgrounds",
    "catalog_spirit_roots",
    "catalog_difficulties",
    "catalog_story_seeds",
    "run_achievements",
    "account_rewards",
    "legacy_bonuses",
    "game_runs",
    "game_turns",
    "player_progress",
)


@pytest.fixture(autouse=True)
def _isolated_pg_db(_pg_test_url, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point create_app() at the shared test DB and truncate before each test."""
    url = _pg_test_url
    if url is None:
        pytest.skip("TEST_DATABASE_URL not configured")
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_engine(url)
    try:
        table_list = ", ".join(_TEST_TABLES)
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"))
    finally:
        engine.dispose()
    yield
