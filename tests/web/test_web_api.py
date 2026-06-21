from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

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
                "hp": 100,
                "hp_max": 100,
                "mp": 50,
                "mp_max": 50,
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
                    "spiritual_sense": 50,
                },
                "experience": 0,
                "experience_to_next": 100,
                "gold": 10,
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
            "character": {"experience": "+10"},
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
                "game_name": "青玄",
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
                    "spiritual_sense": 50,
                },
            },
        ).json()
        assert started["game_started"] is True
        assert started["fallback_prompt"]["active"] is False
        assert started["choices"] == ["拜见执事", "观察山门", "询问路人"]
        assert started["character"]["name"] == "许满"

        chosen = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice_index": 0},
        ).json()
        assert chosen["turn_count"] == 1
        assert chosen["character"]["experience"] == 10
        assert chosen["choices"] == ["继续请教", "前往住处", "查看木牌"]

        acted = client.post(
            f"/api/sessions/{session_id}/action",
            json={"action": "查看木牌"},
        ).json()
        assert acted["turn_count"] == 2
        assert acted["panels"]["status"]


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
        assert loaded["choices"] == ["拜见执事", "观察山门", "询问路人"]

    db_text = (tmp_path / "agens_web.sqlite3").read_bytes()
    assert b"sk-test-web-api" not in db_text


def test_web_model_failure_exposes_fallback_and_can_end(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
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

    assert client.post("/api/sessions", json={}).status_code == 401
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
    assert client.post("/api/sessions", json={}).status_code == 200


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
