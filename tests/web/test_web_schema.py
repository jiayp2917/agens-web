"""PostgreSQL migration, schema and database smoke coverage."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.web.test_web_api import _runner
from web.backend.app import create_app

pytestmark = pytest.mark.xdist_group("pg_test_db")


def test_alembic_initial_pg_schema_covers_runtime_tables() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "20260621_0001_initial_web_pg.py"
    ).read_text(encoding="utf-8")
    for table in (
        "catalog_talents",
        "catalog_family_backgrounds",
        "catalog_spirit_roots",
        "catalog_difficulties",
        "catalog_story_seeds",
        "run_achievements",
        "account_rewards",
        "legacy_bonuses",
    ):
        assert f'"{table}"' in migration

def test_alembic_game_mode_v5_bridge_covers_runtime_tables() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "20260622_0003_game_mode_v5_runs_turns_progress.py"
    ).read_text(encoding="utf-8")
    for table in ("game_runs", "game_turns", "player_progress"):
        assert table in migration
    assert "CREATE TABLE IF NOT EXISTS" in migration
    assert 'down_revision = "20260621_0002"' in migration

def test_alembic_user_model_configs_migration_covers_runtime_tables() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "20260622_0005_user_model_configs.py"
    ).read_text(encoding="utf-8")
    assert 'revision = "20260622_0005"' in migration
    assert 'down_revision = "20260622_0004"' in migration
    assert "user_model_configs" in migration
    assert "api_key_encrypted" in migration

def test_auto_ddl_schema_includes_database_comments() -> None:
    from web.backend.database_postgres_schema import schema_comment_statements

    comments = "\n".join(schema_comment_statements())
    assert "COMMENT ON TABLE user_model_configs" in comments
    assert "用户个人模型配置表" in comments
    assert "COMMENT ON COLUMN game_turns.run_id" in comments
    assert "当前等于 session_id" in comments


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not configured")
def test_postgres_database_url_smoke(monkeypatch) -> None:
    from alembic import command
    from alembic.config import Config

    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("INVITE_ADMIN_CODE", "pg-admin-invite-123")
    monkeypatch.setenv("SESSION_SECRET", "test-postgres-session-secret")
    monkeypatch.setenv("AGENS_ALLOWED_ORIGINS", "https://game.example.test")

    engine = create_engine(os.environ["TEST_DATABASE_URL"], isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()

    alembic_cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")

    from web.backend.database import create_database

    db = create_database()
    assert db.engine.url.drivername.startswith("postgresql")
    assert db.list_catalog("catalog_talents")
    with db.engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.user_model_configs')")).scalar() == "user_model_configs"
        columns = conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'model_config'")
        ).scalars().all()
        table_comment = conn.execute(
            text(
                """
                SELECT obj_description('public.user_model_configs'::regclass)
                """
            )
        ).scalar()
        run_id_comment = conn.execute(
            text(
                """
                SELECT col_description('public.game_turns'::regclass, ordinal_position)
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'game_turns'
                  AND column_name = 'run_id'
                """
            )
        ).scalar()
    assert "api_key_encrypted" in columns
    with db.engine.connect() as conn:
        spirit_root_columns = conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'catalog_spirit_roots'")
        ).scalars().all()
    assert {"rarity", "description"}.issubset(spirit_root_columns)
    assert table_comment == "用户个人模型配置表。每个注册用户最多一条，加密保存个人 API Key。"
    assert "当前等于 session_id" in run_id_comment

    app = create_app()
    client = TestClient(app, base_url="https://game.example.test")
    client.post(
        "/api/auth/register",
        json={"username": "pg_player", "password": "password-123", "invite_code": "pg-admin-invite-123"},
        headers={"Origin": "https://game.example.test"},
    )
    created = client.post(
        "/api/sessions",
        json={},
        headers={"Origin": "https://game.example.test"},
    ).json()
    session_id = created["session_id"]
    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        started = client.post(
            f"/api/sessions/{session_id}/start",
            json={"char_name": "pg_player"},
            headers={"Origin": "https://game.example.test"},
        ).json()
        assert started["game_started"] is True
        assert client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice_index": 0},
            headers={"Origin": "https://game.example.test"},
        ).status_code == 200
        assert client.post(
            f"/api/sessions/{session_id}/save",
            json={"name": "slot_1"},
            headers={"Origin": "https://game.example.test"},
        ).status_code == 200
        assert client.post(
            f"/api/sessions/{session_id}/load",
            json={"name": "slot_1"},
            headers={"Origin": "https://game.example.test"},
        ).status_code == 200
        assert client.post(
            f"/api/sessions/{session_id}/end",
            json={"reason": "done"},
            headers={"Origin": "https://game.example.test"},
        ).status_code == 200
    assert client.get(f"/api/sessions/{session_id}/death_summary").status_code == 200
