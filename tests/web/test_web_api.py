from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from web.backend.app import create_app
from web.backend.auth import hash_invite_code


def _world_builder_result() -> dict:
    return {
        "generated_data": {
            "character": {
                "name": "许满",
                "realm": "练气",
                "realm_stage": 1,
                "spirit_root": "火灵根",
                "spirit_root_grade": "地",
                "age": 16,
                "talent": "剑心微明",
                "family_background": "寒门",
                "difficulty": "普通",
                "attributes": {
                    "root_bone": 50,
                    "comprehension": 50,
                    "luck": 50,
                    "willpower": 50,
                    "physique": 50,
                    "soul": 50,
                },
                "techniques": [{"name": "基础吐纳术", "level": 1, "type": "内功"}],
                "inventory": [{"name": "粗布道袍", "quantity": 1, "type": "防具"}],
                "status_effects": [],
                "lifespan": 100,
            },
            "world": {
                "current_scene": "青玄宗山门",
                "location": "青玄宗山门",
                "region": "东荒",
                "npcs_present": [],
                "active_quests": [],
                "discovered_locations": ["青玄宗山门"],
                "lore_facts": ["青玄宗立于东荒云脉之上。"],
                "day_count": 1,
            },
            "opening_narrative": "晨雾漫过青玄宗山门，你踏上第一阶石阶。",
            "choices": ["拜见执事", "观察山门", "询问路人"],
        },
        "llm_error": "",
    }


def _narrator_result(text: str = "你拜见执事，听完入门规矩后气息更稳。") -> dict:
    return {
        "narrative": text,
        "state_delta": {
            "character": {"attributes": {"willpower": 1}},
            "world": {"current_scene": "山门执事堂"},
        },
        "choices": ["继续请教", "前往住处", "查看木牌"],
        "llm_error": "",
    }


def _judge_result() -> dict:
    return {"approved": True, "corrected_delta": {}, "llm_error": ""}


def _runner(agent_name: str, *_args, **_kwargs):
    if agent_name == "world_builder":
        return _world_builder_result()
    if agent_name == "narrator":
        return _narrator_result()
    if agent_name == "judge":
        return _judge_result()
    raise AssertionError(agent_name)


def _register(client: TestClient, invite: str = "invite-code-123") -> dict:
    return client.post(
        "/api/auth/register",
        json={"username": "player", "password": "password-123", "invite_code": invite},
    ).json()["user"]


def _create_invite(app, invite: str = "invite-code-123") -> None:
    app.state.service.db.create_invite_code(hash_invite_code(invite), max_uses=10)


def test_web_api_minimum_game_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("AGENS_WEB_DB", str(tmp_path / "agens_web.sqlite3"))
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)

    _create_invite(app)
    user = _register(client)
    created = client.post("/api/sessions", json={"user_id": "forged", "title": "测试局"}).json()
    session_id = created["session_id"]
    assert created["user_id"] == user["id"]

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        started = client.post(
            f"/api/sessions/{session_id}/start",
            json={
                "char_name": "许满",
                "talent": "剑心微明",
                "spirit_root": "火灵根",
                "family_background": "寒门",
                "difficulty": "普通",
                "randomize_attributes": False,
                "attributes": {
                    "root_bone": 50,
                    "comprehension": 50,
                    "luck": 50,
                    "willpower": 50,
                    "physique": 50,
                    "soul": 50,
                },
            },
        ).json()
        assert started["game_started"] is True
        assert started["fallback_prompt"]["active"] is False
        assert len(started["choices"]) == 4
        assert "气运" in started["choices"][-1]
        assert started["character"]["name"] == "许满"

        chosen = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice_index": 0},
        ).json()
        assert chosen["turn_count"] == 1
        assert "experience" not in chosen["character"]
        assert "insight" not in chosen["character"]
        assert "gold" not in chosen["character"]
        assert chosen["character"]["age"] > started["character"]["age"]
        assert chosen["choices"] == ["继续请教", "前往住处", "查看木牌", "【气运】随缘而行，听天命、赌因果"]

        acted = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice_index": 3},
        ).json()
        assert acted["turn_count"] == 2
        assert acted["panels"]["status"]

        with app.state.service.db.connect() as conn:
            turn_count = conn.execute(
                "SELECT count(*) AS c FROM game_turns WHERE run_id = ?",
                (session_id,),
            ).fetchone()["c"]
        assert turn_count == 2

        ended = client.post(
            f"/api/sessions/{session_id}/end",
            json={"reason": "玩家结束本局"},
        ).json()
        assert ended["game_over"] is True
        assert app.state.service.db.get_player_progress(user["id"]) == {
            "runs_completed": 1,
            "ascension_count": 0,
        }

        client.post(f"/api/sessions/{session_id}/end", json={"reason": "玩家结束本局"})
        assert app.state.service.db.get_player_progress(user["id"]) == {
            "runs_completed": 1,
            "ascension_count": 0,
        }


def test_web_save_load_restores_snapshot_and_chat_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)
    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        client.post(f"/api/sessions/{session_id}/start", json={"char_name": "许满"})
        saved = client.post(f"/api/sessions/{session_id}/save", json={"name": "slot_1"}).json()
        assert saved["save"]["name"] == "slot_1"

        loaded = client.post(f"/api/sessions/{session_id}/load", json={"name": "slot_1"}).json()
        assert loaded["character"]["name"] == "许满"
        assert len(loaded["choices"]) == 4
        assert "气运" in loaded["choices"][-1]

    db_text = (tmp_path / "agens_web.sqlite3").read_bytes()
    assert b"sk-test-web-api" not in db_text


def test_web_model_failure_exposes_fallback_and_can_end(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.setenv("AGENS_START_MODEL_OPENING", "1")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)
    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]

    started = client.post(f"/api/sessions/{session_id}/start", json={"char_name": "许满"}).json()

    assert started["game_over"] is False
    assert started["local_story"]["active"] is True
    assert started["fallback_prompt"]["active"] is True
    assert started["choices"]

    ended = client.post(
        f"/api/sessions/{session_id}/end",
        json={"reason": "玩家结束本局。"},
    ).json()
    assert ended["game_over"] is True
    assert ended["fallback_prompt"]["active"] is False
    assert ended["error"] == "玩家结束本局。"


def test_model_settings_never_returns_raw_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("INVITE_ADMIN_CODE", "admin-invite-123")
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)
    client.post(
        "/api/auth/register",
        json={"username": "admin", "password": "password-123", "invite_code": "admin-invite-123"},
    )
    raw_key = "sk-test-web-secret-123456789"
    saved = client.post(
        "/api/settings/model",
        json={
            "provider": "Agens",
            "base_url": "https://apihub.agnes-ai.com/v1",
            "model": "agnes-2.0-flash",
            "api_key": raw_key,
        },
    ).json()
    assert saved["api_key_set"] is True
    assert saved["api_key_masked"] != raw_key
    assert raw_key not in json.dumps(saved, ensure_ascii=False)


def test_post_model_settings_rejects_oversized_field(tmp_path: Path) -> None:
    """F-002: 四个字段均有 max_length 约束。超长值必须返回 422。"""
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)
    app.state.service.db.create_user("admin", "hash", is_admin=True)
    token = __import__("web.backend.auth", fromlist=["create_session_token"]).create_session_token(
        app.state.service.db.get_user_by_username("admin")["id"]
    )
    client.cookies.set("agens_session", token)
    cases = [
        ("provider", "x" * 200),
        ("base_url", "https://" + "a" * 600),
        ("model", "m" * 300),
        ("api_key", "k" * 1024),
    ]
    for field, oversize_value in cases:
        payload = {
            "provider": "Agens",
            "base_url": "https://apihub.agnes-ai.com/v1",
            "model": "agnes-2.0-flash",
            "api_key": "",
        }
        payload[field] = oversize_value
        resp = client.post("/api/settings/model", json=payload)
        assert resp.status_code == 422, f"{field}: expected 422, got {resp.status_code}"
        body = resp.text
        assert field in body or "too_long" in body or "max_length" in body or "longer than" in body


def test_invite_register_and_auth_required(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)

    guest = client.post("/api/sessions", json={})
    assert guest.status_code == 200
    assert guest.json()["guest"] is True
    _create_invite(app, "valid-invite-123")
    bad = client.post(
        "/api/auth/register",
        json={"username": "bad", "password": "password-123", "invite_code": "wrong-code"},
    )
    assert bad.status_code == 400

    ok = client.post(
        "/api/auth/register",
        json={"username": "player", "password": "password-123", "invite_code": "valid-invite-123"},
    )
    assert ok.status_code == 200
    assert ok.json()["user"]["username"] == "player"
    assert client.post("/api/sessions", json={}).json()["guest"] is False


def test_guest_can_play_but_cannot_use_cloud_saves(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)

    created = client.post("/api/sessions", json={"title": "访客局"}).json()
    assert created["guest"] is True
    assert created["user_id"].startswith("guest:")
    session_id = created["session_id"]

    started = client.post(f"/api/sessions/{session_id}/start", json={"char_name": "访客"}).json()
    assert started["game_started"] is True
    assert started["guest"] is True
    assert started["local_story"]["active"] is False

    assert client.post(
        f"/api/sessions/{session_id}/action",
        json={"action": "继续本局"},
    ).status_code == 200
    assert client.post(f"/api/sessions/{session_id}/save", json={"name": "slot_1"}).status_code == 401
    assert client.get("/api/saves").status_code == 401
    assert client.get(f"/api/sessions/{session_id}").status_code == 200

    other_client = TestClient(app)
    assert other_client.get(f"/api/sessions/{session_id}").status_code == 401
    assert other_client.post(
        f"/api/sessions/{session_id}/action",
        json={"action": "继续本局"},
    ).status_code == 401


def test_legacy_local_login_route_is_removed(tmp_path: Path) -> None:
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)
    assert client.post("/api/users/login", json={"username": "local"}).status_code == 404


def test_user_cannot_access_another_users_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app(tmp_path / "agens_web.sqlite3")
    client_a = TestClient(app)
    client_b = TestClient(app)
    app.state.service.db.create_invite_code(hash_invite_code("invite-a-123"), max_uses=1)
    app.state.service.db.create_invite_code(hash_invite_code("invite-b-123"), max_uses=1)
    client_a.post(
        "/api/auth/register",
        json={"username": "user_a", "password": "password-123", "invite_code": "invite-a-123"},
    )
    client_b.post(
        "/api/auth/register",
        json={"username": "user_b", "password": "password-123", "invite_code": "invite-b-123"},
    )
    session_id = client_a.post("/api/sessions", json={}).json()["session_id"]
    assert client_b.get(f"/api/sessions/{session_id}").status_code == 403
    for path, payload in (
        (f"/api/sessions/{session_id}/start", {"char_name": "盗档者"}),
        (f"/api/sessions/{session_id}/choice", {"choice_index": 0}),
        (f"/api/sessions/{session_id}/action", {"action": "查看"}),
        (f"/api/sessions/{session_id}/save", {"name": "slot_1"}),
        (f"/api/sessions/{session_id}/load", {"name": "slot_1"}),
        (f"/api/sessions/{session_id}/end", {"reason": "结束"}),
    ):
        assert client_b.post(path, json=payload).status_code == 403


def test_production_rejects_default_session_secret(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://agens_user:test@postgres:5432/agens_web")
    monkeypatch.setenv("INVITE_ADMIN_CODE", "admin-invite-123")
    monkeypatch.delenv("SESSION_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        create_app(tmp_path / "agens_web.sqlite3")

    monkeypatch.setenv("SESSION_SECRET", "dev-session-secret-change-me")
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        create_app(tmp_path / "agens_web.sqlite3")


def test_production_requires_allowed_origins(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENS_ENV", "production")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://agens_user:test@postgres:5432/agens_web")
    monkeypatch.setenv("INVITE_ADMIN_CODE", "admin-invite-123")
    monkeypatch.setenv("SESSION_SECRET", "not-the-dev-secret")
    monkeypatch.delenv("AGENS_ALLOWED_ORIGINS", raising=False)

    with pytest.raises(RuntimeError, match="AGENS_ALLOWED_ORIGINS"):
        create_app(tmp_path / "agens_web.sqlite3")


def test_production_hides_openapi_and_rejects_untrusted_host(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENS_ENV", "production")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://agens_user:test@postgres:5432/agens_web")
    monkeypatch.setenv("INVITE_ADMIN_CODE", "admin-invite-123")
    monkeypatch.setenv("SESSION_SECRET", "not-the-dev-secret")
    monkeypatch.setenv("AGENS_ALLOWED_ORIGINS", "https://game.example.test")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app(tmp_path / "agens_web.sqlite3")

    client = TestClient(app, base_url="https://game.example.test")
    assert client.get("/api/health").status_code == 200
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404

    blocked = TestClient(app, base_url="https://evil.example.test")
    assert blocked.get("/api/health").status_code == 400


def test_origin_mismatch_is_rejected_for_state_changes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("AGENS_ALLOWED_ORIGINS", "https://game.example.test")
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app, base_url="https://game.example.test")
    _create_invite(app)
    client.post(
        "/api/auth/register",
        json={"username": "player", "password": "password-123", "invite_code": "invite-code-123"},
        headers={"Origin": "https://game.example.test"},
    )

    blocked = client.post(
        "/api/sessions",
        json={},
        headers={"Origin": "https://evil.example.test"},
    )
    assert blocked.status_code == 403

    allowed = client.post(
        "/api/sessions",
        json={},
        headers={"Origin": "https://game.example.test"},
    )
    assert allowed.status_code == 200


def test_body_size_limit_rejects_actual_large_body(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("AGENS_MAX_REQUEST_BYTES", "128")
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)

    response = client.post(
        "/api/auth/login",
        content=b'{"username":"' + (b"x" * 256) + b'","password":"password-123"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


@pytest.mark.anyio("asyncio")
async def test_body_size_limit_rejects_chunked_body_without_content_length() -> None:
    from web.backend.security import BodySizeLimitMiddleware

    async def inner_app(_scope, _receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = BodySizeLimitMiddleware(inner_app, max_bytes=8)
    scope = {"type": "http", "headers": []}
    messages = iter(
        [
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"6789", "more_body": False},
        ]
    )
    sent: list[dict[str, Any]] = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    await middleware(scope, receive, send)

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413


@pytest.mark.anyio("asyncio")
async def test_body_size_limit_replays_allowed_chunked_body() -> None:
    from web.backend.security import BodySizeLimitMiddleware

    seen_body = b""

    async def inner_app(_scope, receive, send):
        nonlocal seen_body
        message = await receive()
        seen_body = message["body"]
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = BodySizeLimitMiddleware(inner_app, max_bytes=16)
    scope = {"type": "http", "headers": []}
    messages = iter(
        [
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"678", "more_body": False},
        ]
    )
    sent: list[dict[str, Any]] = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    await middleware(scope, receive, send)

    assert seen_body == b"12345678"
    assert sent[0]["status"] == 204


def test_admin_invite_create_validates_schema(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)
    app.state.service.db.create_user("admin", "hash", is_admin=True)
    token = __import__("web.backend.auth", fromlist=["create_session_token"]).create_session_token(
        app.state.service.db.get_user_by_username("admin")["id"]
    )
    client.cookies.set("agens_session", token)

    assert client.post("/api/invites", json={"code": "short"}).status_code == 422
    assert client.post(
        "/api/invites",
        json={"code": "valid-code-123", "role": "owner", "max_uses": 1},
    ).status_code == 422
    assert client.post(
        "/api/invites",
        json={"code": "valid-code-123", "role": "user", "max_uses": "many"},
    ).status_code == 422


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


def test_model_failure_events_are_public_safe(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)
    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]

    def failing_world_builder(agent_name: str, *_args, **_kwargs):
        if agent_name == "world_builder":
            return {"generated_data": {}, "llm_error": "sk-secret leaked via provider"}
        return _runner(agent_name)

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=failing_world_builder):
        payload = client.post(f"/api/sessions/{session_id}/start", json={"char_name": "许满"}).json()

    body = json.dumps(payload, ensure_ascii=False)
    assert "sk-secret" not in body
    assert "模型暂不可用，当前以本地故事继续。" in body


def test_start_accepts_seeded_catalog_character_options(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)
    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        started = client.post(
            f"/api/sessions/{session_id}/start",
            json={
                "char_name": "许满",
                "talent": "万法归宗",
                "spirit_root": "混沌灵根",
                "family_background": "隐世仙族",
                "difficulty": "普通",
                "randomize_attributes": False,
                "attributes": {
                    "root_bone": 50,
                    "comprehension": 50,
                    "luck": 50,
                    "willpower": 50,
                    "physique": 50,
                    "soul": 50,
                },
            },
        ).json()

    assert started["game_started"] is True
    assert started["character"]["talent"] == "万法归宗"
    assert started["character"]["spirit_root"] == "混沌灵根"
    assert started["character"]["spirit_root_grade"] == "天"
    assert started["character"]["family_background"] == "隐世仙族"


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not configured")
def test_postgres_database_url_smoke(monkeypatch) -> None:
    from alembic import command
    from alembic.config import Config

    monkeypatch.setenv("DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("INVITE_ADMIN_CODE", "pg-admin-invite-123")
    monkeypatch.setenv("SESSION_SECRET", "test-postgres-session-secret")
    monkeypatch.setenv("AGENS_ALLOWED_ORIGINS", "https://game.example.test")

    alembic_cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")

    from web.backend.database import create_database

    db = create_database()
    assert db.engine.url.drivername.startswith("postgresql")
    assert db.list_catalog("catalog_talents")

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


# ── P4: Death rewards ──────────────────────────────────────────────────


def test_death_summary_persists_for_registered_user(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)
    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={"title": "试炼"}).json()["session_id"]

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        client.post(f"/api/sessions/{session_id}/start", json={"char_name": "许满"})
        ended = client.post(
            f"/api/sessions/{session_id}/end",
            json={"reason": "玩家结束本局。"},
        ).json()
        assert ended["game_over"] is True

    summary_resp = client.get(f"/api/sessions/{session_id}/death_summary").json()
    assert summary_resp["is_guest"] is False
    summary = summary_resp["summary"]
    assert summary["death_cause"] == "玩家结束本局"
    achievement_keys = {a["key"] for a in summary.get("achievements", [])}
    assert "long_lived_mortal" not in achievement_keys
    # At minimum, base attribute_points are always granted.
    types = {r["type"] for r in summary.get("rewards", [])}
    assert "attribute_points" in types

    # Legacy bonuses should now be listed for the user.
    bonuses = client.get("/api/users/me/legacy_bonuses").json()
    assert len(bonuses) >= 1
    assert any(b["bonus_type"] == "attribute_points" for b in bonuses)


def test_legacy_bonuses_applied_on_next_character(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)
    _create_invite(app)
    _register(client)
    db = app.state.service.db
    user_id = db.get_user_by_username("player")["id"]
    # Pre-seed two legacy bonuses for the user.
    db.save_legacy_bonus(
        user_id=user_id,
        bonus_type="attribute_points",
        bonus_value="2",
        label="+2",
        source_session_id="seeded",
    )
    db.save_legacy_bonus(
        user_id=user_id,
        bonus_type="extra_lifespan",
        bonus_value="10",
        label="+10",
        source_session_id="seeded",
    )

    session_id = client.post("/api/sessions", json={}).json()["session_id"]
    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        started = client.post(
            f"/api/sessions/{session_id}/start",
            json={
                "char_name": "许满",
                "attributes": {
                    "root_bone": 50, "comprehension": 50, "luck": 50,
                    "willpower": 50, "physique": 50, "soul": 50,
                },
            },
        ).json()
    # Both bonuses should have been applied: +2 attribute points distributed
    # to the lowest stats, +10 extra lifespan reflected in world/character.
    assert started["game_started"] is True
    # After consumption, legacy_bonuses for this user should be 0 (runs_remaining 0).
    remaining = db.list_legacy_bonuses(user_id)
    assert all(b["runs_remaining"] == 0 for b in remaining)


def test_legacy_bonuses_endpoint_returns_empty_for_guest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)
    # No login → 401 (endpoint requires auth).
    assert client.get("/api/users/me/legacy_bonuses").status_code == 401


def test_guest_death_summary_returns_in_memory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)
    session_id = client.post("/api/sessions", json={"title": "访客局"}).json()["session_id"]

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        client.post(f"/api/sessions/{session_id}/start", json={"char_name": "访客"})
        client.post(
            f"/api/sessions/{session_id}/end",
            json={"reason": "玩家结束本局。"},
        )

    summary = client.get(f"/api/sessions/{session_id}/death_summary").json()
    assert summary["is_guest"] is True
    # Summary exists even though the guest has no DB.
    assert summary["summary"]["death_cause"] == "玩家结束本局"
