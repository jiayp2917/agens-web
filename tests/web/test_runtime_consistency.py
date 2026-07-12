from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from web.backend.app import create_app
from web.backend.auth import GUEST_COOKIE_NAME, hash_invite_code, hash_password
from web.backend.service_errors import InvalidInvite

pytestmark = pytest.mark.xdist_group("pg_test_db")


def _runner(agent_name: str, *_args, **_kwargs):
    if agent_name == "world_builder":
        return {
            "generated_data": {
                "character": {
                    "name": "许满",
                    "realm": "练气",
                    "realm_stage": 1,
                    "age": 16,
                    "lifespan": 100,
                },
                "world": {"current_scene": "山门", "location": "山门", "region": "东荒"},
                "opening_narrative": "十六岁，你来到山门。",
                "choices": ["稳住气息", "寻找机缘", "探查险地", "随缘而行"],
            },
            "llm_error": "",
        }
    if agent_name == "narrator":
        return {
            "narrative": "一年过去，你的根基更稳。",
            "state_delta": {"character": {}, "world": {}, "meta": {}},
            "choices": ["继续修行", "寻找机缘", "外出历练", "随缘而行"],
            "llm_error": "",
        }
    return {"approved": True, "corrected_delta": {}, "llm_error": ""}


def _register(client: TestClient, app, username: str = "player") -> dict:
    invite = f"invite-{username}-123"
    app.state.service.db.create_invite_code(hash_invite_code(invite), max_uses=5)
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "password-123", "invite_code": invite},
    )
    assert response.status_code == 200
    return response.json()["user"]


def _capture(operation, value):
    try:
        return operation(value)
    except Exception as exc:
        return exc


def test_registration_failure_rolls_back_invite_use(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    db = app.state.service.db
    db.create_user("taken", hash_password("password-123"))
    invite = "rollback-invite-123"
    db.create_invite_code(hash_invite_code(invite), max_uses=1)
    client = TestClient(app)

    response = client.post(
        "/api/auth/register",
        json={"username": "taken", "password": "password-123", "invite_code": invite},
    )

    assert response.status_code == 409
    with db.engine.connect() as conn:
        uses = conn.execute(
            text("SELECT uses FROM invite_codes WHERE code_hash = :code_hash"),
            {"code_hash": hash_invite_code(invite)},
        ).scalar_one()
    assert uses == 0


def test_bootstrap_admin_is_serialized(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    db = create_app().state.service.db

    def create(username: str):
        return db.register_user_atomic(
            username,
            hash_password("password-123"),
            bootstrap_admin=True,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda name: _capture(create, name), ["admin_a", "admin_b"]))

    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, InvalidInvite) for result in results) == 1


def test_guest_session_recovers_across_service_instances(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app_one = create_app()
    client_one = TestClient(app_one)
    created = client_one.post("/api/sessions", json={}).json()
    guest_token = client_one.cookies.get(GUEST_COOKIE_NAME)
    assert guest_token

    app_two = create_app()
    client_two = TestClient(app_two)
    client_two.cookies.set(GUEST_COOKIE_NAME, guest_token)
    restored = client_two.get(f"/api/sessions/{created['session_id']}")

    assert restored.status_code == 200
    assert restored.json()["guest"] is True
    assert restored.json()["version"] == created["version"]


def test_login_deletes_current_guest_session(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)
    client.post("/api/sessions", json={})
    _register(client, app)

    with app.state.service.db.engine.connect() as conn:
        guest_count = conn.execute(
            text("SELECT count(*) FROM sessions WHERE user_id IS NULL")
        ).scalar_one()
    assert guest_count == 0
    assert client.cookies.get(GUEST_COOKIE_NAME) is None


def test_turn_request_is_idempotent_and_stale_version_conflicts(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("AGNES_API_KEY", "test-key")
    app = create_app()
    client = TestClient(app)
    _register(client, app)
    created = client.post("/api/sessions", json={}).json()
    session_id = created["session_id"]

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        start_body = {
            "char_name": "许满",
            "request_id": "start-request-123",
            "expected_version": 0,
        }
        started = client.post(f"/api/sessions/{session_id}/start", json=start_body)
        repeated_start = client.post(f"/api/sessions/{session_id}/start", json=start_body)
        assert started.json() == repeated_start.json()

        choice_body = {
            "choice_index": 0,
            "request_id": "choice-request-123",
            "expected_version": 1,
        }
        chosen = client.post(f"/api/sessions/{session_id}/choice", json=choice_body)
        repeated_choice = client.post(f"/api/sessions/{session_id}/choice", json=choice_body)

    assert chosen.status_code == 200
    assert chosen.json() == repeated_choice.json()
    assert chosen.json()["turn_count"] == 1
    assert chosen.json()["version"] == 2
    stale = client.post(
        f"/api/sessions/{session_id}/choice",
        json={
            "choice_index": 0,
            "request_id": "stale-request-123",
            "expected_version": 1,
        },
    )
    assert stale.status_code == 409
    with app.state.service.db.engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM game_turns WHERE run_id = :run_id"),
            {"run_id": session_id},
        ).scalar_one()
    assert count == 1


def test_mutation_requests_require_request_id_and_expected_version() -> None:
    app = create_app()
    client = TestClient(app)
    created = client.post("/api/sessions", json={"title": "严格契约"}).json()

    response = client.request(
        "POST",
        f"/api/sessions/{created['session_id']}/start",
        json={"char_name": "缺少幂等字段"},
    )

    assert response.status_code == 422
    missing = {item["loc"][-1] for item in response.json()["detail"]}
    assert missing == {"request_id", "expected_version"}


def test_turn_transaction_failure_rolls_back_snapshot_and_log(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("AGNES_API_KEY", "test-key")
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    _register(client, app)
    created = client.post("/api/sessions", json={}).json()
    session_id = created["session_id"]
    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        client.post(
            f"/api/sessions/{session_id}/start",
            json={
                "char_name": "许满",
                "request_id": "start-rollback-123",
                "expected_version": 0,
            },
        )
        with patch.object(
            app.state.service.db._session_mutation,
            "_insert_turn",
            side_effect=RuntimeError("write failed"),
        ):
            failed = client.post(
                f"/api/sessions/{session_id}/choice",
                json={
                    "choice_index": 0,
                    "request_id": "turn-rollback-123",
                    "expected_version": 1,
                },
            )
    assert failed.status_code == 500
    restored = client.get(f"/api/sessions/{session_id}").json()
    assert restored["turn_count"] == 0
    assert restored["version"] == 1
    with app.state.service.db.engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM game_turns WHERE run_id = :run_id"),
            {"run_id": session_id},
        ).scalar_one()
    assert count == 0


def test_start_failure_does_not_consume_legacy_bonus(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("AGNES_API_KEY", "test-key")
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    user = _register(client, app)
    db = app.state.service.db
    db.save_legacy_bonus(
        user_id=user["id"],
        bonus_type="extra_lifespan",
        bonus_value="10",
        label="+10",
        source_session_id="previous-run",
    )
    session_id = client.post("/api/sessions", json={}).json()["session_id"]

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        with patch.object(db._session_mutation, "_ensure_active_run", side_effect=RuntimeError("run write failed")):
            response = client.post(
                f"/api/sessions/{session_id}/start",
                json={
                    "char_name": "许满",
                    "request_id": "start-bonus-rollback",
                    "expected_version": 0,
                },
            )

    assert response.status_code == 500
    assert db.list_legacy_bonuses(user["id"])[0]["runs_remaining"] == 1
    restored = client.get(f"/api/sessions/{session_id}").json()
    assert restored["game_started"] is False
    assert restored["version"] == 0


def test_terminal_bundle_is_atomic_and_retryable(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("AGNES_API_KEY", "test-key")
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    user = _register(client, app)
    db = app.state.service.db
    session_id = client.post("/api/sessions", json={}).json()["session_id"]
    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        client.post(
            f"/api/sessions/{session_id}/start",
            json={
                "char_name": "许满",
                "request_id": "start-terminal-atomic",
                "expected_version": 0,
            },
        )

    original = db._session_mutation._finalize_terminal

    def fail_after_writes(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("terminal write failed")

    with patch.object(db._session_mutation, "_finalize_terminal", side_effect=fail_after_writes):
        failed = client.post(
            f"/api/sessions/{session_id}/end",
            json={
                "reason": "本地测试结束",
                "request_id": "end-terminal-failed",
                "expected_version": 1,
            },
        )
    assert failed.status_code == 500
    assert db.get_player_progress(user["id"])["runs_completed"] == 0
    assert db.list_run_achievements(user["id"], session_id) == []
    assert db.list_account_rewards(user["id"]) == []
    assert client.get(f"/api/sessions/{session_id}").json()["game_over"] is False

    completed = client.post(
        f"/api/sessions/{session_id}/end",
        json={
            "reason": "本地测试结束",
            "request_id": "end-terminal-retry",
            "expected_version": 1,
        },
    )
    assert completed.status_code == 200
    assert db.get_player_progress(user["id"])["runs_completed"] == 1
