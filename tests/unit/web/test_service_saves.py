"""Unit coverage for extracted web save/load use cases."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from web.backend.database import WebDatabaseProtocol
from web.backend.service import WebGameService, WebRunner


class _SaveDatabase:
    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot
        self.commit_kwargs: dict[str, Any] = {}

    def get_session_mutation(self, _session_id: str, _request_id: str) -> None:
        return None

    def load_save(self, _user_id: str, name: str) -> dict[str, Any]:
        return {"name": name, "snapshot": self.snapshot, "events": [{"type": "info"}]}

    def commit_session_mutation(self, **kwargs: Any) -> dict[str, Any]:
        self.commit_kwargs = kwargs
        response = dict(kwargs["response"])
        response["version"] = int(kwargs["expected_version"]) + 1
        return response

    def list_saves(self, user_id: str) -> list[dict[str, str]]:
        return [{"name": "slot_1", "user_id": user_id}]


def test_save_rejects_guest_runner_after_extraction() -> None:
    service = WebGameService(SimpleNamespace())
    runner = WebRunner(session_id="guest-session", user_id="guest:visitor")
    service._register_runner(runner.session_id, runner)

    with pytest.raises(PermissionError, match="访客游玩"):
        service._require_non_guest_runner(runner.session_id, None, action="存档")


def test_load_commits_rewind_and_replaces_cached_runner() -> None:
    source = WebRunner(session_id="save-session", user_id="player")
    source.engine.game_session.char_name = "许满"
    source.engine.game_session.realm = "练气"
    source.engine.game_session.turn_count = 2
    snapshot = source.snapshot()
    database = _SaveDatabase(snapshot)
    service = WebGameService(cast(WebDatabaseProtocol, database))
    current = WebRunner(session_id="save-session", user_id="player", version=4)
    service._register_runner(current.session_id, current)

    result = service.load(
        current.session_id,
        {"name": "slot_1", "request_id": "load-request", "expected_version": 4},
        user_id="player",
    )

    assert database.commit_kwargs["operation"] == "load"
    assert database.commit_kwargs["rewind_run"] == {
        "turn_count": 2,
        "char_name": "许满",
        "realm": "练气",
    }
    assert result["version"] == 5
    assert service.runners[current.session_id].engine.game_session.turn_count == 2


def test_list_saves_requires_login_after_extraction() -> None:
    database = _SaveDatabase(WebRunner("s", "player").snapshot())
    service = WebGameService(cast(WebDatabaseProtocol, database))

    with pytest.raises(PermissionError, match="读取存档"):
        service.list_saves()
    assert service.list_saves("player") == [{"name": "slot_1", "user_id": "player"}]
