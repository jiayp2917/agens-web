"""Story binding compatibility for restored WebRunner snapshots."""

from __future__ import annotations

import pytest

from agens_novel.session.game_session import GameSession
from web.backend.service import WebRunner


def _legacy_started_snapshot() -> dict:
    session = GameSession(
        game_started=True,
        char_name="旧档修士",
        region="青岚药境",
        world_profile={"world_key": "forest", "world_name": "青岚药境"},
    )
    snapshot = session.to_save_dict()
    snapshot["world"].pop("story_key", None)
    snapshot["world"].pop("story_version", None)
    snapshot["world"].pop("story_state", None)
    return snapshot


def test_restored_legacy_started_snapshot_receives_story_binding() -> None:
    runner = WebRunner.from_snapshot(
        session_id="legacy-session",
        user_id="user-1",
        snapshot=_legacy_started_snapshot(),
    )

    session = runner.engine.game_session
    assert session.story_key == "herb-boundary-blight"
    assert session.story_version == 1
    assert session.story_state["status"] == "active"


def test_restored_snapshot_rejects_unknown_exact_story_version() -> None:
    snapshot = _legacy_started_snapshot()
    snapshot["world"]["story_key"] = "herb-boundary-blight"
    snapshot["world"]["story_version"] = 999
    snapshot["world"]["story_state"] = {"status": "active"}

    with pytest.raises(ValueError, match="剧情版本不可用"):
        WebRunner.from_snapshot(
            session_id="invalid-version-session",
            user_id="user-1",
            snapshot=snapshot,
        )


def test_restored_snapshot_exposes_titles_and_relationships() -> None:
    session = GameSession(
        char_name="许满",
        titles=["外门魁首"],
        relationships=[{"name": "陈师兄", "relation": "盟友", "affinity": 12}],
    )

    runner = WebRunner.from_snapshot(
        session_id="structured-state-session",
        user_id="user-1",
        snapshot=session.to_save_dict(),
    )

    character = runner.response()["character"]
    assert character["titles"] == ["外门魁首"]
    assert character["relationships"] == [
        {"name": "陈师兄", "relation": "盟友", "affinity": 12}
    ]
