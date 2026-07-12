"""Auth-stream tests extracted from test_web_api.py — invite/register/guest/user-isolation/admin/service-error-mapping."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.web.test_web_api import _create_invite
from web.backend.app import create_app
from web.backend.auth import create_session_token, hash_invite_code

pytestmark = pytest.mark.xdist_group("pg_test_db")


def test_invite_register_and_auth_required(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
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
    app = create_app()
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
    app = create_app()
    client = TestClient(app)
    assert client.post("/api/users/login", json={"username": "local"}).status_code == 404


def test_user_cannot_access_another_users_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
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


@pytest.mark.parametrize(
    ("method_name", "request_method", "path_suffix", "payload", "exc", "status_code"),
    [
        ("get_session", "get", "", None, KeyError("missing session"), 404),
        ("start_session", "post", "/start", {"char_name": "许满"}, ValueError("bad start"), 400),
        ("choose", "post", "/choice", {"choice_index": 0}, ValueError("bad choice"), 400),
        ("act", "post", "/action", {"action": "查看"}, ValueError("bad action"), 400),
        ("save", "post", "/save", {"name": "slot_1"}, PermissionError("not owner"), 403),
        ("load", "post", "/load", {"name": "slot_1"}, PermissionError("not owner"), 403),
        ("end_session", "post", "/end", {"reason": "结束"}, PermissionError("not owner"), 403),
        ("death_summary", "get", "/death_summary", None, KeyError("missing summary"), 404),
    ],
)
def test_session_routes_map_service_errors(
    tmp_path: Path,
    monkeypatch,
    method_name: str,
    request_method: str,
    path_suffix: str,
    payload: dict[str, object] | None,
    exc: Exception,
    status_code: int,
) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)
    app.state.service.db.create_user("player", "hash")
    token = create_session_token(app.state.service.db.get_user_by_username("player")["id"])
    client.cookies.set("agens_session", token)
    session_id = "session-for-error-mapping"

    def fail(*_args, **_kwargs):
        raise exc

    monkeypatch.setattr(app.state.service, method_name, fail)
    request = getattr(client, request_method)
    response = request(f"/api/sessions/{session_id}{path_suffix}", json=payload) if payload is not None else request(
        f"/api/sessions/{session_id}{path_suffix}"
    )

    assert response.status_code == status_code


def test_admin_invite_create_validates_schema(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)
    app.state.service.db.create_user("admin", "hash", is_admin=True)
    token = create_session_token(app.state.service.db.get_user_by_username("admin")["id"])
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
