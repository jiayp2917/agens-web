"""PostgreSQL migration exercises for the runtime-consistency boundary."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError

from web.backend.database import resolve_database_url
from web.backend.local_postgres_safety import require_loopback_postgres_url

pytestmark = [
    pytest.mark.integration,
    pytest.mark.postgres,
]


_ROOT = Path(__file__).resolve().parents[2]
_PREVIOUS_REVISION = "20260705_0007"
_HEAD_REVISION = "20260721_0009"


@contextmanager
def _temporary_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[URL]:
    source = require_loopback_postgres_url(make_url(resolve_database_url()))
    database = create_engine(source)
    cfg = _alembic_config()
    _reset_public_schema(database)
    try:
        monkeypatch.setenv("DATABASE_URL", source.render_as_string(hide_password=False))
        yield source
    finally:
        _reset_public_schema(database)
        command.upgrade(cfg, "head")
        database.dispose()


def _reset_public_schema(database) -> None:
    with database.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def _alembic_config() -> Config:
    return Config(str(_ROOT / "alembic.ini"))


def _revision(database_url: URL) -> str:
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            return str(conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one())
    finally:
        engine.dispose()


def test_existing_0007_session_turn_is_backfilled_before_foreign_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _temporary_database(monkeypatch) as database_url:
        cfg = _alembic_config()
        command.upgrade(cfg, _PREVIOUS_REVISION)
        engine = create_engine(database_url)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO users (id, username, password_hash, is_admin, created_at, updated_at) "
                        "VALUES ('user-1', 'legacy_user', 'hash', FALSE, 10, 10)"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO sessions (id, user_id, title, snapshot, events, created_at, updated_at) "
                        "VALUES ('session-1', 'user-1', 'legacy', "
                        "CAST(:snapshot AS jsonb), CAST(:events AS jsonb), 11, 12)"
                    ),
                    {
                        "snapshot": json.dumps(
                            {
                                "character": {"name": "旧角色", "realm": "练气"},
                                "turn_count": 1,
                            },
                            ensure_ascii=False,
                        ),
                        "events": "[]",
                    },
                )
                conn.execute(
                    text(
                        "INSERT INTO game_turns "
                        "(id, run_id, turn_no, start_age, elapsed_years, end_age, lifespan, "
                        "remaining_lifespan, choices, state_delta, state_after, calendar_summary, narrative) "
                        "VALUES ('turn-1', 'session-1', 1, 16, 1, 17, 100, 83, '[]'::jsonb, "
                        "'{}'::jsonb, '{}'::jsonb, '旧摘要', '旧叙事')"
                    )
                )
        finally:
            engine.dispose()

        command.upgrade(cfg, "head")

        engine = create_engine(database_url)
        try:
            with engine.connect() as conn:
                run = conn.execute(
                    text(
                        "SELECT user_id, session_id, char_name, realm, turn_count, completed, finished_at "
                        "FROM game_runs WHERE id = 'session-1'"
                    )
                ).mappings().one()
                version = conn.execute(
                    text("SELECT version FROM sessions WHERE id = 'session-1'")
                ).scalar_one()
                foreign_key = conn.execute(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conname = 'fk_game_turns_run' AND contype = 'f'"
                    )
                ).scalar_one()
        finally:
            engine.dispose()

        assert run == {
            "user_id": "user-1",
            "session_id": "session-1",
            "char_name": "旧角色",
            "realm": "练气",
            "turn_count": 1,
            "completed": False,
            "finished_at": None,
        }
        assert version == 0
        assert foreign_key == 1
        assert _revision(database_url) == _HEAD_REVISION


def test_partially_applied_user_model_config_migration_reaches_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _temporary_database(monkeypatch) as database_url:
        cfg = _alembic_config()
        command.upgrade(cfg, "20260622_0004")
        engine = create_engine(database_url)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE model_config "
                        "ADD COLUMN api_key_encrypted TEXT NOT NULL DEFAULT ''"
                    )
                )
        finally:
            engine.dispose()

        command.upgrade(cfg, "head")

        engine = create_engine(database_url)
        try:
            with engine.connect() as conn:
                user_config_table = conn.execute(
                    text("SELECT to_regclass('public.user_model_configs')")
                ).scalar_one()
        finally:
            engine.dispose()

        assert user_config_table == "user_model_configs"
        assert _revision(database_url) == _HEAD_REVISION


def test_partially_applied_runtime_consistency_migration_reaches_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _temporary_database(monkeypatch) as database_url:
        cfg = _alembic_config()
        command.upgrade(cfg, "20260705_0007")
        engine = create_engine(database_url)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "CREATE TABLE session_mutations ("
                        "session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, "
                        "request_id TEXT NOT NULL, operation TEXT NOT NULL, "
                        "expected_version INTEGER NOT NULL, result_version INTEGER NOT NULL, "
                        "response JSONB NOT NULL, created_at DOUBLE PRECISION NOT NULL, "
                        "PRIMARY KEY (session_id, request_id))"
                    )
                )
        finally:
            engine.dispose()

        command.upgrade(cfg, "head")

        assert _revision(database_url) == _HEAD_REVISION


def test_orphan_turn_blocks_upgrade_without_partial_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _temporary_database(monkeypatch) as database_url:
        cfg = _alembic_config()
        command.upgrade(cfg, _PREVIOUS_REVISION)
        engine = create_engine(database_url)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO game_turns "
                        "(id, run_id, turn_no, start_age, elapsed_years, end_age, lifespan, "
                        "remaining_lifespan, choices, state_delta, state_after, calendar_summary, narrative) "
                        "VALUES ('orphan-turn', 'missing-run', 1, 16, 1, 17, 100, 83, "
                        "'[]'::jsonb, '{}'::jsonb, '{}'::jsonb, '', '')"
                    )
                )
        finally:
            engine.dispose()

        with pytest.raises(DBAPIError, match="orphan game_turns"):
            command.upgrade(cfg, "head")

        engine = create_engine(database_url)
        try:
            with engine.connect() as conn:
                mutation_table = conn.execute(
                    text("SELECT to_regclass('public.session_mutations')")
                ).scalar_one()
                request_column = conn.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'game_turns' "
                        "AND column_name = 'request_id'"
                    )
                ).scalar_one()
        finally:
            engine.dispose()

        assert mutation_table is None
        assert request_column == 0
        assert _revision(database_url) == _PREVIOUS_REVISION


@pytest.mark.parametrize(
    ("table", "insert_sql"),
    [
        (
            "run_achievements",
            "INSERT INTO run_achievements "
            "(id, user_id, session_id, achievement_key, achievement_name, achieved_at) VALUES "
            "('a-1', 'user-1', 'session-1', 'same-key', '同一成就', 1), "
            "('a-2', 'user-1', 'session-1', 'same-key', '同一成就', 2)",
        ),
        (
            "account_rewards",
            "INSERT INTO account_rewards "
            "(id, user_id, reward_type, reward_value, source_session_id, granted_at) VALUES "
            "('r-1', 'user-1', 'title', 'same', 'session-1', 1), "
            "('r-2', 'user-1', 'title', 'same', 'session-1', 2)",
        ),
        (
            "legacy_bonuses",
            "INSERT INTO legacy_bonuses "
            "(id, user_id, bonus_type, bonus_value, source_session_id, granted_at) VALUES "
            "('b-1', 'user-1', 'attribute', 'same', 'session-1', 1), "
            "('b-2', 'user-1', 'attribute', 'same', 'session-1', 2)",
        ),
    ],
)
def test_duplicate_business_rows_block_upgrade(
    monkeypatch: pytest.MonkeyPatch,
    table: str,
    insert_sql: str,
) -> None:
    with _temporary_database(monkeypatch) as database_url:
        cfg = _alembic_config()
        command.upgrade(cfg, _PREVIOUS_REVISION)
        engine = create_engine(database_url)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO users (id, username, password_hash, is_admin, created_at, updated_at) "
                        "VALUES ('user-1', 'duplicate_user', 'hash', FALSE, 1, 1)"
                    )
                )
                conn.execute(text(insert_sql))
        finally:
            engine.dispose()

        with pytest.raises(DBAPIError, match=f"duplicate business rows in {table}"):
            command.upgrade(cfg, "head")

        assert _revision(database_url) == _PREVIOUS_REVISION


def test_clean_downgrade_and_reupgrade_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    with _temporary_database(monkeypatch) as database_url:
        cfg = _alembic_config()
        command.upgrade(cfg, "head")
        command.downgrade(cfg, _PREVIOUS_REVISION)

        engine = create_engine(database_url)
        try:
            with engine.connect() as conn:
                mutation_table = conn.execute(
                    text("SELECT to_regclass('public.session_mutations')")
                ).scalar_one()
                version_column = conn.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'sessions' "
                        "AND column_name = 'version'"
                    )
                ).scalar_one()
        finally:
            engine.dispose()

        assert mutation_table is None
        assert version_column == 0
        assert _revision(database_url) == _PREVIOUS_REVISION

        command.upgrade(cfg, "head")
        assert _revision(database_url) == _HEAD_REVISION


def test_spirit_root_metadata_upgrade_and_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    with _temporary_database(monkeypatch) as database_url:
        cfg = _alembic_config()
        command.upgrade(cfg, "20260710_0008")
        engine = create_engine(database_url)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO catalog_spirit_roots "
                        "(id, name, element, grade, cultivation_bonus, breakthrough_bonus, cultivation_tendency, event_tags) "
                        "VALUES ('root-1', '旧灵根', '水', '地', 1, 0, '', '[]'::jsonb)"
                    )
                )
        finally:
            engine.dispose()

        command.upgrade(cfg, "head")
        engine = create_engine(database_url)
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT rarity, description FROM catalog_spirit_roots WHERE id = 'root-1'")
                ).mappings().one()
        finally:
            engine.dispose()

        assert row == {"rarity": "普通", "description": ""}
        command.downgrade(cfg, "20260710_0008")
        assert _revision(database_url) == "20260710_0008"


@pytest.mark.parametrize("blocking_state", ["guest", "active_run"])
def test_downgrade_refuses_runtime_state(
    monkeypatch: pytest.MonkeyPatch,
    blocking_state: str,
) -> None:
    with _temporary_database(monkeypatch) as database_url:
        cfg = _alembic_config()
        command.upgrade(cfg, "head")
        engine = create_engine(database_url)
        try:
            with engine.begin() as conn:
                if blocking_state == "guest":
                    conn.execute(
                        text(
                            "INSERT INTO sessions "
                            "(id, user_id, title, snapshot, events, created_at, updated_at, "
                            "guest_token_hash, expires_at, version) "
                            "VALUES ('guest-session', NULL, 'guest', '{}'::jsonb, '[]'::jsonb, "
                            "1, 1, 'guest-hash', 9999999999, 0)"
                        )
                    )
                else:
                    conn.execute(
                        text(
                            "INSERT INTO users (id, username, password_hash, is_admin, created_at, updated_at) "
                            "VALUES ('user-1', 'active_user', 'hash', FALSE, 1, 1)"
                        )
                    )
                    conn.execute(
                        text(
                            "INSERT INTO sessions "
                            "(id, user_id, title, snapshot, events, created_at, updated_at, version) "
                            "VALUES ('active-session', 'user-1', 'active', '{}'::jsonb, '[]'::jsonb, 1, 1, 0)"
                        )
                    )
                    conn.execute(
                        text(
                            "INSERT INTO game_runs "
                            "(id, user_id, session_id, char_name, realm, death_cause, ascended, turn_count, "
                            "started_at, finished_at, completed) "
                            "VALUES ('active-session', 'user-1', 'active-session', '角色', '练气', '', "
                            "FALSE, 0, 1, NULL, FALSE)"
                        )
                    )
        finally:
            engine.dispose()

        with pytest.raises(DBAPIError, match="guest sessions or active runs"):
            command.downgrade(cfg, _PREVIOUS_REVISION)

        assert _revision(database_url) == _HEAD_REVISION
