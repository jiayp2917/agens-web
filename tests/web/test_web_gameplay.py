"""Core Web session and turn API coverage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from agens_novel.engine.choices import choice_with_semantic
from agens_novel.engine.turn_rules import classify_choice
from agens_novel.game.constants import ATTRIBUTE_KEYS
from tests.web.api_fixtures import (
    _create_invite,
    _judge_result,
    _narrator_result,
    _register,
    _runner,
)
from web.backend.app import create_app

pytestmark = pytest.mark.xdist_group("pg_test_db")

def test_choice_index_semantic_prefixes_match_rule_categories() -> None:
    expected = [
        "\u7a33\u59a5",
        "\u673a\u9047",
        "\u98ce\u9669",
        "\u6c14\u8fd0",
    ]

    for index, category in enumerate(expected):
        action = choice_with_semantic(index, "\u5c71\u95e8\u4fee\u884c")
        assert classify_choice(action) == category
def test_web_api_minimum_game_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
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
                    "root_bone": 5,
                    "comprehension": 5,
                    "luck": 5,
                    "willpower": 5,
                    "physique": 5,
                    "soul": 5,
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
        assert chosen["choices"][:3] == ["继续请教", "前往住处", "查看木牌"]
        assert chosen["choices"][3] == "随缘观望"

        acted = client.post(
            f"/api/sessions/{session_id}/action",
            json={"action": "继续请教"},
        ).json()
        assert acted["turn_count"] == 2
        assert list(acted["panels"]) == ["status_bar"]
        assert acted["panels"]["status_bar"]

        with app.state.service.db.engine.connect() as conn:
            turn_count = conn.execute(
                text("SELECT count(*) FROM game_turns WHERE run_id = :run_id"),
                {"run_id": session_id},
            ).scalar()
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

def test_registered_account_session_start_choice_keeps_owner_and_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)

    _create_invite(app)
    user = _register(client)
    created = client.post("/api/sessions", json={"title": "账号局"}).json()
    session_id = created["session_id"]

    assert created["user_id"] == user["id"]
    assert created["guest"] is False
    with app.state.service.db.engine.connect() as conn:
        owner = conn.execute(
            text("SELECT user_id FROM sessions WHERE id = :id"),
            {"id": session_id},
        ).scalar_one()
    assert owner == user["id"]

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        started = client.post(
            f"/api/sessions/{session_id}/start",
            json={"char_name": "账号局", "attributes": {key: 5 for key in ATTRIBUTE_KEYS}},
        )
        assert started.status_code == 200
        started_body = started.json()
        assert started_body["user_id"] == user["id"]
        assert started_body["guest"] is False
        assert started_body["game_started"] is True

        chosen = client.post(f"/api/sessions/{session_id}/choice", json={"choice_index": 0})
        assert chosen.status_code == 200
        chosen_body = chosen.json()
        assert chosen_body["user_id"] == user["id"]
        assert chosen_body["guest"] is False
        assert chosen_body["turn_count"] == 1

    with app.state.service.db.engine.connect() as conn:
        counts = conn.execute(
            text(
                """
                SELECT
                    (SELECT count(*) FROM users WHERE id = :user_id) AS users_count,
                    (SELECT count(*) FROM sessions WHERE id = :session_id AND user_id = :user_id) AS sessions_count,
                    (SELECT count(*) FROM game_turns WHERE run_id = :session_id) AS turns_count
                """
            ),
            {"user_id": user["id"], "session_id": session_id},
        ).mappings().one()

    assert counts["users_count"] == 1
    assert counts["sessions_count"] == 1
    assert counts["turns_count"] == 1

def test_choice_endpoint_rejects_free_text_and_accepts_choice_letter_or_number(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)

    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        client.post(f"/api/sessions/{session_id}/start", json={"char_name": "fixed-choice"})

        rejected = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice": "free typed action"},
        )
        assert rejected.status_code == 400
        assert client.get(f"/api/sessions/{session_id}").json()["turn_count"] == 0

        accepted = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice": "A"},
        )
        assert accepted.status_code == 200
        assert accepted.json()["turn_count"] == 1

        accepted_number = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice": "1"},
        )
        assert accepted_number.status_code == 200
        assert accepted_number.json()["turn_count"] == 2

        rejected_number = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice": "5"},
        )
        assert rejected_number.status_code == 400
        rejected_mixed = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice": "1abc"},
        )
        assert rejected_mixed.status_code == 400
        assert client.get(f"/api/sessions/{session_id}").json()["turn_count"] == 2

def test_ineligible_breakthrough_choice_advances_and_records_turn(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)

    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]
    client.post(f"/api/sessions/{session_id}/start", json={"char_name": "breakthrough-button"})
    app.state.service.runners[session_id].engine.game_session.last_choices = [
        "尝试突破",
        "外出历练",
        "检查经脉",
        "随缘而行",
    ]

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        chosen = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice": "A"},
        )

    assert chosen.status_code == 200
    body = chosen.json()
    assert body["turn_count"] == 1
    assert body["fallback_prompt"]["active"] is False
    with app.state.service.db.engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT count(*) AS c, max(turn_no) AS max_turn
                FROM game_turns
                WHERE run_id = :run_id
                """
            ),
            {"run_id": session_id},
        ).mappings().one()
    assert dict(row) == {"c": 1, "max_turn": 1}

def test_mismatched_narrative_still_records_contiguous_turns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)

    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]
    client.post(f"/api/sessions/{session_id}/start", json={"char_name": "mismatch-flow"})

    def mismatch_once(agent_name: str, *_args, **_kwargs):
        if agent_name == "narrator":
            return _narrator_result("你获得一枚清灵丹，又习得云水诀。")
        if agent_name == "judge":
            return _judge_result()
        return _runner(agent_name)

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=mismatch_once):
        first = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice": "A"},
        ).json()
    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        second = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice": "A"},
        ).json()

    assert first["turn_count"] == 1
    assert second["turn_count"] == 2
    assert all(item.get("name") != "清灵丹" for item in second["character"]["inventory"])
    with app.state.service.db.engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT turn_no
                FROM game_turns
                WHERE run_id = :run_id
                ORDER BY turn_no
                """
            ),
            {"run_id": session_id},
        ).scalars().all()
    assert rows == [1, 2]

def test_pending_model_failure_requires_explicit_local_story_before_recording_turn(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)

    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]
    client.post(f"/api/sessions/{session_id}/start", json={"char_name": "fallback-flow"})

    def incomplete_narrator(agent_name: str, *_args, **_kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "",
                "state_delta": {},
                "choices": [],
                "llm_error": "",
            }
        return _runner(agent_name)

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=incomplete_narrator):
        chosen = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice": "A"},
        )

    assert chosen.status_code == 200
    body = chosen.json()
    assert body["turn_count"] == 0
    assert body["fallback_prompt"]["active"] is False
    assert body["pending_model_failure"] == {
        **body["pending_model_failure"],
        "stage": "turn",
        "slot": "A",
        "status": "pending",
    }
    assert body["pending_model_failure"]["error_code"]
    with app.state.service.db.engine.connect() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM game_turns WHERE run_id = :run_id"),
            {"run_id": session_id},
        ).scalar_one() == 0

    resolved = client.post(
        f"/api/sessions/{session_id}/action",
        json={"action": "use_local_story"},
    )

    assert resolved.status_code == 200
    body = resolved.json()
    assert body["turn_count"] == 1
    assert body["pending_model_failure"] is None
    assert body["local_story"]["active"] is True
    assert body["fallback_prompt"]["active"] is True
    with app.state.service.db.engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT turn_no, elapsed_years, event_kind, narrative, state_delta
                FROM game_turns
                WHERE run_id = :run_id
                """
            ),
            {"run_id": session_id},
        ).mappings().one()
    assert row["turn_no"] == 1
    assert row["elapsed_years"] >= 1
    assert row["event_kind"] in {"稳妥", "event"}
    assert row["narrative"]
    assert row["state_delta"]["meta"]["local_story_fallback"] is True

def test_retry_pending_model_failure_reuses_frozen_rule_turn(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)

    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]
    client.post(f"/api/sessions/{session_id}/start", json={"char_name": "recover-flow"})

    def incomplete_choices(agent_name: str, *_args, **_kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "你在药谷石亭听见外门弟子议论新开的任务。",
                "state_delta": {},
                "choices": [],
                "llm_error": "",
            }
        return _runner(agent_name)

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=incomplete_choices):
        chosen = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice": "A"},
        )

    assert chosen.status_code == 200
    body = chosen.json()
    assert body["turn_count"] == 0
    assert body["fallback_prompt"]["active"] is False
    assert body["pending_model_failure"]["stage"] == "turn"

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        retried = client.post(
            f"/api/sessions/{session_id}/action",
            json={"action": "retry_model"},
        )

    assert retried.status_code == 200
    body = retried.json()
    assert body["turn_count"] == 1
    assert body["pending_model_failure"] is None
    assert len(body["choices"]) == 4
    with app.state.service.db.engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT turn_no, elapsed_years, event_kind, state_delta
                FROM game_turns
                WHERE run_id = :run_id
                """
            ),
            {"run_id": session_id},
        ).mappings().one()
    assert row["turn_no"] == 1
    assert row["elapsed_years"] > 0
    assert row["event_kind"] != "fallback"
    assert row["state_delta"]["meta"]["choice_category"] in {"稳妥", "机遇", "风险", "气运"}
    assert "local_story_fallback" not in row["state_delta"]["meta"]

def test_malformed_state_update_with_narrative_settles_rule_turn(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)

    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]
    client.post(f"/api/sessions/{session_id}/start", json={"char_name": "malformed-flow"})

    def malformed_state_update(agent_name: str, *_args, **_kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "你在山门前停步，听见执事提起一卷残缺竹简。",
                "state_delta": None,
                "choices": ["登记借阅名册", "询问执事来历", "夜里潜去旧架", "随缘抽取一卷"],
                "llm_error": "",
            }
        return _runner(agent_name)

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=malformed_state_update):
        chosen = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice": "A"},
        )

    assert chosen.status_code == 200
    body = chosen.json()
    assert body["turn_count"] == 1
    assert body["fallback_prompt"]["active"] is False
    with app.state.service.db.engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT turn_no, elapsed_years, event_kind, state_delta
                FROM game_turns
                WHERE run_id = :run_id
                """
            ),
            {"run_id": session_id},
        ).mappings().one()
    assert row["turn_no"] == 1
    assert row["elapsed_years"] > 0
    assert row["event_kind"] != "fallback"
    assert row["state_delta"]["meta"]["choice_category"] in {"稳妥", "机遇", "风险", "气运"}
    assert "local_story_fallback" not in row["state_delta"]["meta"]
