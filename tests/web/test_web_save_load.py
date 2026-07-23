"""Save/load tests extracted from test_web_api.py — snapshot restore, rewind, completed-run continuation."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.web.api_fixtures import _create_invite, _register, _runner
from web.backend.app import create_app

pytestmark = pytest.mark.xdist_group("pg_test_db")


def test_web_save_load_restores_snapshot_and_chat_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        started = client.post(
            f"/api/sessions/{session_id}/start", json={"char_name": "许满"}
        ).json()
        visible_events = list(started["events"])
        saved = client.post(f"/api/sessions/{session_id}/save", json={"name": "slot_1"}).json()
        assert saved["save"]["name"] == "slot_1"
        assert saved["session"]["events"] == visible_events

        loaded = client.post(f"/api/sessions/{session_id}/load", json={"name": "slot_1"}).json()
        assert loaded["character"]["name"] == "许满"
        assert len(loaded["choices"]) == 4
        assert "气运" in loaded["choices"][-1]
        assert loaded["events"] == visible_events
        assert all("slot_1" not in str(event) for event in loaded["events"])

    # Security: the raw API key must never be persisted. Under PostgreSQL there
    # is no DB file to scan, so check the columns that could hold it.
    with app.state.service.db.engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT api_key_masked::text FROM model_config
                UNION ALL SELECT snapshot::text FROM sessions
                UNION ALL SELECT snapshot::text FROM saves
                UNION ALL SELECT state_delta::text FROM game_turns
                UNION ALL SELECT state_after::text FROM game_turns
                UNION ALL SELECT narrative FROM game_turns
                """
            )
        )
        db_text = " ".join(row[0] for row in rows if row[0])
    assert "sk-test-web-api" not in db_text


def test_web_load_rewinds_future_turn_rows_before_continuing(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    user = _register(client)
    session = client.post("/api/sessions", json={}).json()
    session_id = session["session_id"]

    def mutation(body: dict[str, Any], current: dict[str, Any], request_id: str) -> dict[str, Any]:
        return {
            **body,
            "request_id": request_id,
            "expected_version": current["version"],
        }

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        current = client.post(
            f"/api/sessions/{session_id}/start",
            json=mutation({"char_name": "许满"}, session, "rewind-start-0001"),
        ).json()
        current = client.post(
            f"/api/sessions/{session_id}/choice",
            json=mutation({"choice_index": 0}, current, "rewind-turn-0001"),
        ).json()
        saved_turn = current["turn_count"]
        current = client.post(
            f"/api/sessions/{session_id}/save",
            json=mutation({"name": "rewind_slot"}, current, "rewind-save-0001"),
        ).json()["session"]
        current = client.post(
            f"/api/sessions/{session_id}/choice",
            json=mutation({"choice_index": 1}, current, "rewind-turn-0002"),
        ).json()
        assert current["turn_count"] == saved_turn + 1

        current = client.post(
            f"/api/sessions/{session_id}/load",
            json=mutation({"name": "rewind_slot"}, current, "rewind-load-0001"),
        ).json()
        assert current["turn_count"] == saved_turn
        continued = client.post(
            f"/api/sessions/{session_id}/choice",
            json=mutation({"choice_index": 2}, current, "rewind-turn-0002"),
        )

    assert continued.status_code == 200
    assert continued.json()["turn_count"] == saved_turn + 1
    with app.state.service.db.engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    """
                SELECT turn_no FROM game_turns
                WHERE run_id = :run_id
                ORDER BY turn_no
                """
                ),
                {"run_id": session_id},
            )
            .scalars()
            .all()
        )
    assert rows == list(range(1, saved_turn + 2))
    assert user["id"]


def test_web_new_session_can_load_completed_run_save_and_continue(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    _register(client)

    def mutation(body: dict[str, Any], current: dict[str, Any], request_id: str) -> dict[str, Any]:
        return {**body, "request_id": request_id, "expected_version": current["version"]}

    original = client.post("/api/sessions", json={}).json()
    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        current = client.post(
            f"/api/sessions/{original['session_id']}/start",
            json=mutation({"char_name": "许满"}, original, "new-load-start-0001"),
        ).json()
        current = client.post(
            f"/api/sessions/{original['session_id']}/choice",
            json=mutation({"choice_index": 0}, current, "new-load-turn-0001"),
        ).json()
        saved_turn = current["turn_count"]
        current = client.post(
            f"/api/sessions/{original['session_id']}/save",
            json=mutation({"name": "completed_source"}, current, "new-load-save-0001"),
        ).json()["session"]
        ended = client.post(
            f"/api/sessions/{original['session_id']}/end",
            json=mutation({"reason": "玩家结束本局"}, current, "new-load-end-0001"),
        )
        assert ended.status_code == 200

        fresh = client.post("/api/sessions", json={}).json()
        loaded = client.post(
            f"/api/sessions/{fresh['session_id']}/load",
            json=mutation({"name": "completed_source"}, fresh, "new-load-load-0001"),
        )
        assert loaded.status_code == 200
        loaded_body = loaded.json()
        continued = client.post(
            f"/api/sessions/{fresh['session_id']}/choice",
            json=mutation({"choice_index": 1}, loaded_body, "new-load-turn-0002"),
        )

    assert continued.status_code == 200
    assert continued.json()["turn_count"] == saved_turn + 1
    with app.state.service.db.engine.connect() as conn:
        run = (
            conn.execute(
                text("SELECT completed, turn_count FROM game_runs WHERE id = :id"),
                {"id": fresh["session_id"]},
            )
            .mappings()
            .one()
        )
    assert run["completed"] is False
    assert run["turn_count"] == saved_turn + 1
