"""Death summary and legacy reward coverage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.web.api_fixtures import _create_invite, _register, _runner
from web.backend.app import create_app

pytestmark = pytest.mark.xdist_group("pg_test_db")


def test_death_summary_persists_for_registered_user(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
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
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    _register(client)
    db = app.state.service.db
    user_id = db.get_user_by_username("player")["id"]
    # Pre-seed legacy bonuses for the user.
    db.save_legacy_bonus(
        user_id=user_id,
        bonus_type="attribute_points",
        bonus_value="2",
        label="+2",
        source_session_id="seeded",
    )
    db.save_legacy_bonus(
        user_id=user_id,
        bonus_type="legacy_talent",
        bonus_value="游历之眼",
        label="游历之眼",
        source_session_id="seeded",
    )
    db.save_legacy_bonus(
        user_id=user_id,
        bonus_type="opening_title",
        bonus_value="飞升者",
        label="飞升者",
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
                    "root_bone": 5, "comprehension": 5, "luck": 5,
                    "willpower": 5, "physique": 5, "soul": 5,
                },
            },
        ).json()
    # All bonuses should be visible before the rows are consumed.
    assert started["game_started"] is True
    assert started["character"]["legacy_talents"] == ["游历之眼"]
    assert started["character"]["titles"] == ["飞升者"]
    # After consumption, legacy_bonuses for this user should be 0 (runs_remaining 0).
    remaining = db.list_legacy_bonuses(user_id)
    assert all(b["runs_remaining"] == 0 for b in remaining)

def test_legacy_bonuses_endpoint_returns_empty_for_guest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)
    # No login → 401 (endpoint requires auth).
    assert client.get("/api/users/me/legacy_bonuses").status_code == 401

def test_guest_death_summary_returns_in_memory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
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
