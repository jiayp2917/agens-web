from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from agens_novel.engine.turn_rules import classify_choice
from agens_novel.game.constants import ATTRIBUTE_KEYS
from web.backend.app import create_app
from web.backend.auth import hash_invite_code
from web.backend.service import _with_choice_semantic


pytestmark = pytest.mark.xdist_group("pg_test_db")


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
                    "root_bone": 5,
                    "comprehension": 5,
                    "luck": 5,
                    "willpower": 5,
                    "physique": 5,
                    "soul": 5,
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


def test_choice_index_semantic_prefixes_match_rule_categories() -> None:
    expected = [
        "\u7a33\u59a5",
        "\u673a\u9047",
        "\u98ce\u9669",
        "\u6c14\u8fd0",
    ]

    for index, category in enumerate(expected):
        action = _with_choice_semantic(index, "\u5c71\u95e8\u4fee\u884c")
        assert classify_choice(action) == category


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
        assert chosen["choices"] == ["继续请教", "前往住处", "查看木牌", "【气运】随缘而行，听天命、赌因果"]

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


def test_local_story_fallback_records_turn(
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
    assert body["turn_count"] == 1
    assert body["fallback_prompt"]["active"] is True
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
    assert row["elapsed_years"] == 0
    assert row["event_kind"] == "fallback"
    assert row["state_delta"]["meta"]["local_story_fallback"] is True


def test_incomplete_narrator_choices_recover_without_local_story_fallback(
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
    assert body["turn_count"] == 1
    assert body["fallback_prompt"]["active"] is False
    assert len(body["choices"]) == 4
    visible_texts = [
        str(event.get("text") or "")
        for event in body["events"]
        if event.get("type") in {"narrative", "info", "error", "model_failure"}
    ]
    assert not any("补齐下一步选择" in text_value or "因果结算" in text_value for text_value in visible_texts)
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


def test_model_failure_prompt_exposes_sanitized_http_404_cause(
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
    client.post(f"/api/sessions/{session_id}/start", json={"char_name": "model-404-flow"})

    def narrator_404(agent_name: str, *_args, **_kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "",
                "state_delta": {},
                "choices": [],
                "llm_error": 'HTTP 404: {"error":{"message":"Not Found","code":"404"}}',
            }
        return _runner(agent_name)

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=narrator_404):
        chosen = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice": "A"},
        )

    assert chosen.status_code == 200
    body = chosen.json()
    assert body["fallback_prompt"]["active"] is True
    text_value = body["fallback_prompt"]["text"]
    assert "HTTP 404" in text_value
    assert "模型名/Base URL" in text_value
    assert "sk-" not in text_value
    assert "https://" not in text_value


def test_transient_narrator_404_retries_without_fallback(
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
    client.post(f"/api/sessions/{session_id}/start", json={"char_name": "retry-404-flow"})

    calls = {"narrator": 0}

    def transient_narrator_404(agent_name: str, *_args, **_kwargs):
        if agent_name == "narrator":
            calls["narrator"] += 1
            if calls["narrator"] == 1:
                return {
                    "narrative": "",
                    "state_delta": {},
                    "choices": [],
                    "llm_error": 'HTTP 404: {"error":{"type":"upstream_error","code":"404"}}',
                }
            return {
                "narrative": "你将地图副本交入执事堂，换得一段清静修行时日。",
                "state_delta": {"character": {"attributes": {"willpower": 1}}},
                "choices": ["回院吐纳", "打听赏格", "追查地图", "随缘等候"],
                "llm_error": "",
            }
        return _runner(agent_name)

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=transient_narrator_404):
        chosen = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice": "A"},
        )

    assert chosen.status_code == 200
    body = chosen.json()
    assert calls["narrator"] == 2
    assert body["turn_count"] == 1
    assert body["fallback_prompt"]["active"] is False
    assert len(body["choices"]) == 4


def test_model_failure_prompt_and_event_redact_secret_bearing_format_reason(
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
    client.post(f"/api/sessions/{session_id}/start", json={"char_name": "model-redact-flow"})

    secret_bearing_reason = (
        "状态更新格式不完整: https://provider.example/v1 "
        "x-api-key sk-secret Authorization: Bearer token"
    )

    def narrator_secret_error(agent_name: str, *_args, **_kwargs):
        if agent_name == "narrator":
            return {
                "narrative": "",
                "state_delta": {},
                "choices": [],
                "llm_error": secret_bearing_reason,
            }
        return _runner(agent_name)

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=narrator_secret_error):
        chosen = client.post(
            f"/api/sessions/{session_id}/choice",
            json={"choice": "A"},
        )

    assert chosen.status_code == 200
    body = chosen.json()
    visible_texts = [body["fallback_prompt"]["text"]]
    visible_texts.extend(
        event.get("text", "")
        for event in body["events"]
        if event.get("type") in {"model_failure", "error", "info"}
    )
    assert any("天道紊乱" in text for text in visible_texts)
    for text_value in visible_texts:
        assert "sk-" not in text_value
        assert "Authorization" not in text_value
        assert "x-api-key" not in text_value
        assert "provider.example" not in text_value
        assert "https://" not in text_value


def test_web_save_load_restores_snapshot_and_chat_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
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


def test_web_model_failure_exposes_fallback_and_can_end(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.setenv("AGENS_START_MODEL_OPENING", "1")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]

    started = client.post(f"/api/sessions/{session_id}/start", json={"char_name": "许满"}).json()

    assert started["game_over"] is False
    assert started["local_story"]["active"] is False
    assert started["fallback_prompt"]["active"] is True
    assert any(event.get("type") == "model_failure" for event in started["events"])
    assert started["world"]["world_profile"].get("chronicle_0_16")
    assert started["choices"]

    ended = client.post(
        f"/api/sessions/{session_id}/end",
        json={"reason": "玩家结束本局。"},
    ).json()
    assert ended["game_over"] is True
    assert ended["fallback_prompt"]["active"] is False
    assert ended["error"] == "玩家结束本局。"



def _login_user(client: TestClient, username: str, invite: str) -> dict:
    return client.post(
        "/api/auth/register",
        json={"username": username, "password": "password-123", "invite_code": invite},
    ).json()["user"]


def _model_payload(api_key: str = "") -> dict[str, str]:
    return {
        "provider": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key": api_key,
    }


def test_user_model_settings_save_read_clear_and_encrypts_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    user = _login_user(client, "player", "invite-code-123")

    initial = client.get("/api/settings/model")
    assert initial.status_code == 200
    assert initial.json()["source"] == "system"

    raw_key = "test-user-key-123456789"
    saved = client.post("/api/settings/model", json=_model_payload(raw_key))
    assert saved.status_code == 200
    body = saved.json()
    assert body["source"] == "user"
    assert body["provider"] == "DeepSeek"
    assert body["api_key_set"] is True
    assert body["api_key_masked"] != raw_key
    assert raw_key not in json.dumps(body, ensure_ascii=False)

    read_back = client.get("/api/settings/model").json()
    assert read_back["source"] == "user"
    assert raw_key not in json.dumps(read_back, ensure_ascii=False)

    with app.state.service.db.engine.connect() as conn:
        row = conn.execute(
            text("SELECT user_id, api_key_encrypted, api_key_masked FROM user_model_configs")
        ).mappings().one()
    assert row["user_id"] == user["id"]
    assert row["api_key_encrypted"].startswith("fernet:")
    assert raw_key not in row["api_key_encrypted"]
    assert raw_key not in row["api_key_masked"]

    cleared = client.delete("/api/settings/model")
    assert cleared.status_code == 200
    assert cleared.json()["source"] == "system"
    assert app.state.service.db.get_user_model_config(user["id"]) is None


def test_model_settings_are_isolated_per_user(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    app = create_app()
    _create_invite(app, "invite-a-123")
    _create_invite(app, "invite-b-123")

    client_a = TestClient(app)
    user_a = _login_user(client_a, "player_a", "invite-a-123")
    client_a.post("/api/settings/model", json=_model_payload("test-user-a-key-123456"))

    client_b = TestClient(app)
    user_b = _login_user(client_b, "player_b", "invite-b-123")
    assert client_b.get("/api/settings/model").json()["source"] == "system"
    client_b.post("/api/settings/model", json=_model_payload("test-user-b-key-123456"))

    assert client_a.get("/api/settings/model").json()["source"] == "user"
    assert client_b.get("/api/settings/model").json()["source"] == "user"
    assert app.state.service.db.get_user_model_config(user_a["id"])["api_key_encrypted"] != app.state.service.db.get_user_model_config(user_b["id"])["api_key_encrypted"]


def test_user_model_settings_reject_empty_initial_key_and_keep_existing_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    monkeypatch.setenv("AGNES_API_KEY", "test-system-key-123456")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    user = _login_user(client, "player_empty_key", "invite-code-123")

    rejected = client.post("/api/settings/model", json=_model_payload(""))
    assert rejected.status_code == 400
    assert client.get("/api/settings/model").json()["source"] == "system"
    assert app.state.service.db.get_user_model_config(user["id"]) is None

    saved = client.post("/api/settings/model", json=_model_payload("test-user-key-123456"))
    assert saved.status_code == 200
    encrypted = app.state.service.db.get_user_model_config(user["id"])["api_key_encrypted"]

    updated = client.post(
        "/api/settings/model",
        json={
            "provider": "Qwen",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-plus",
            "api_key": "",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["source"] == "user"
    assert updated.json()["api_key_set"] is True
    assert app.state.service.db.get_user_model_config(user["id"])["api_key_encrypted"] == encrypted
    runtime = app.state.service._model_config.runtime(user["id"])
    assert runtime["api_key"] == "test-user-key-123456"
    assert runtime["provider"] == "Qwen"


def test_guest_model_settings_rejected_and_admin_system_endpoint_is_admin_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    monkeypatch.setenv("INVITE_ADMIN_CODE", "admin-invite-123")
    app = create_app()
    guest = TestClient(app)
    assert guest.get("/api/settings/model").status_code == 401
    assert guest.post("/api/settings/model", json=_model_payload("test-guest-key-123456")).status_code == 401
    assert guest.delete("/api/settings/model").status_code == 401
    assert guest.get("/api/admin/settings/model").status_code == 401

    _create_invite(app, "normal-invite-123")
    user_client = TestClient(app)
    _login_user(user_client, "normal_user", "normal-invite-123")
    assert user_client.get("/api/admin/settings/model").status_code == 403
    assert user_client.post("/api/admin/settings/model", json=_model_payload("test-user-key-123456")).status_code == 403

    admin_client = TestClient(app)
    admin_client.post(
        "/api/auth/register",
        json={"username": "admin", "password": "password-123", "invite_code": "admin-invite-123"},
    )
    saved = admin_client.post("/api/admin/settings/model", json=_model_payload("test-admin-key-123456"))
    assert saved.status_code == 200
    assert saved.json()["source"] == "system"
    assert saved.json()["api_key_set"] is True
    assert "test-admin-key" not in json.dumps(saved.json(), ensure_ascii=False)


def test_model_settings_missing_secret_fails_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    monkeypatch.setenv("AGNES_API_KEY", "test-env-key-must-not-be-used")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    user = _login_user(client, "player", "invite-code-123")
    client.post("/api/settings/model", json=_model_payload("test-user-key-123456"))

    monkeypatch.delenv("MODEL_CONFIG_SECRET", raising=False)
    runtime = app.state.service._model_config.runtime(user["id"])
    assert runtime["source"] == "user"
    assert runtime["api_key"] == ""
    assert runtime["api_key_set"] is False
    assert runtime["key_error"]

    rejected = client.post("/api/settings/model", json=_model_payload("test-new-user-key-123456"))
    assert rejected.status_code == 400


def test_runtime_model_config_uses_current_user_without_env_pollution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    monkeypatch.setenv("AGNES_API_KEY", "test-env-key-should-not-win")
    app = create_app()
    _create_invite(app, "invite-a-123")
    _create_invite(app, "invite-b-123")

    client_a = TestClient(app)
    user_a = _login_user(client_a, "player_a", "invite-a-123")
    client_a.post("/api/settings/model", json=_model_payload("test-user-a-key-123456"))

    client_b = TestClient(app)
    user_b = _login_user(client_b, "player_b", "invite-b-123")
    client_b.post("/api/settings/model", json=_model_payload("test-user-b-key-123456"))

    config_a = app.state.service._model_config.runtime(user_a["id"])
    config_b = app.state.service._model_config.runtime(user_b["id"])
    assert config_a["api_key"] == "test-user-a-key-123456"
    assert config_b["api_key"] == "test-user-b-key-123456"
    assert os.environ["AGNES_API_KEY"] == "test-env-key-should-not-win"
    assert config_a["api_key"] != config_b["api_key"]


def test_legacy_system_model_config_without_encrypted_key_uses_env_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    monkeypatch.setenv("AGNES_API_KEY", "test-env-key-legacy-system")
    app = create_app()
    app.state.service.db.save_model_config({
        "provider": "Agens",
        "base_url": "https://apihub.agnes-ai.com/v1",
        "model": "agnes-2.0-flash",
        "api_key_set": True,
        "api_key_masked": "<legacy>",
        "api_key_encrypted": "",
    })

    runtime = app.state.service._model_config.runtime(None)

    assert runtime["source"] == "system"
    assert runtime["api_key"] == "test-env-key-legacy-system"
    assert runtime["api_key_set"] is True


def test_post_model_settings_rejects_oversized_field(tmp_path: Path, monkeypatch) -> None:
    """F-002: four fields have max_length constraints and oversized values return 422."""
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    _login_user(client, "player", "invite-code-123")
    cases = [
        ("provider", "x" * 200),
        ("base_url", "https://" + "a" * 600),
        ("model", "m" * 300),
        ("api_key", "k" * 1024),
    ]
    for field, oversize_value in cases:
        payload = _model_payload("")
        payload[field] = oversize_value
        resp = client.post("/api/settings/model", json=payload)
        assert resp.status_code == 422, f"{field}: expected 422, got {resp.status_code}"
        body = resp.text
        assert field in body or "too_long" in body or "max_length" in body or "longer than" in body


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
    token = __import__("web.backend.auth", fromlist=["create_session_token"]).create_session_token(
        app.state.service.db.get_user_by_username("player")["id"]
    )
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


def test_production_rejects_default_session_secret(tmp_path: Path, monkeypatch) -> None:
    # Production mode is driven by AGENS_ENV (not DATABASE_BACKEND) since the
    # Option C consolidation made PostgreSQL the only backend.
    monkeypatch.setenv("AGENS_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://agens_user:test@postgres:5432/agens_web")
    monkeypatch.setenv("INVITE_ADMIN_CODE", "admin-invite-123")
    monkeypatch.delenv("SESSION_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        create_app()

    monkeypatch.setenv("SESSION_SECRET", "dev-session-secret-change-me")
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        create_app()


def test_production_requires_allowed_origins(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENS_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://agens_user:test@postgres:5432/agens_web")
    monkeypatch.setenv("INVITE_ADMIN_CODE", "admin-invite-123")
    monkeypatch.setenv("SESSION_SECRET", "not-the-dev-secret")
    monkeypatch.delenv("AGENS_ALLOWED_ORIGINS", raising=False)

    with pytest.raises(RuntimeError, match="AGENS_ALLOWED_ORIGINS"):
        create_app()


def test_production_hides_openapi_and_rejects_untrusted_host(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENS_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.setenv("INVITE_ADMIN_CODE", "admin-invite-123")
    monkeypatch.setenv("SESSION_SECRET", "not-the-dev-secret")
    monkeypatch.setenv("AGENS_ALLOWED_ORIGINS", "https://game.example.test")
    monkeypatch.setenv("MODEL_CONFIG_SECRET", "test-model-config-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()

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
    app = create_app()
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
    app = create_app()
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
    app = create_app()
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


def test_model_failure_events_are_public_safe(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
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
    app = create_app()
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
    assert started["character"]["talent"] == "万法归宗"
    assert started["character"]["spirit_root"] == "混沌灵根"
    assert started["character"]["spirit_root_grade"] == "天"
    assert started["character"]["family_background"] == "隐世仙族"


def test_start_rejects_invalid_manual_attribute_pool(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]

    response = client.post(
        f"/api/sessions/{session_id}/start",
        json={
            "char_name": "bad-pool",
            "randomize_attributes": False,
            "attributes": {
                "root_bone": 5,
                "comprehension": 5,
                "luck": 5,
                "willpower": 5,
                "physique": 5,
                "soul": 4,
            },
        },
    )

    assert response.status_code == 400
    assert "30" in response.json()["detail"]


def test_randomized_start_uses_30_point_attribute_pool(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]
    preview_attrs = {
        "root_bone": 0,
        "comprehension": 10,
        "luck": 7,
        "willpower": 3,
        "physique": 6,
        "soul": 4,
    }

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_runner):
        started = client.post(
            f"/api/sessions/{session_id}/start",
            json={
                "char_name": "random-pool",
                "randomize_attributes": True,
                "attributes": preview_attrs,
            },
        ).json()

    attrs = started["character"]["attributes"]
    assert attrs == preview_attrs
    assert sum(attrs.values()) == 30
    assert all(0 <= value <= 10 for value in attrs.values())


def test_start_persists_dynamic_opening_world_profile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("AGENS_START_MODEL_OPENING", "1")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]

    def dynamic_world_builder(agent_name: str, user_input: str, *_args, **_kwargs):
        if agent_name == "world_builder":
            assert "六维属性" in user_input
            assert "命数倾向" in user_input
            return {
                "generated_data": {
                    "world_name": "归墟潮界",
                    "regions": [{"name": "潮生海市"}],
                    "sects": [{"name": "潮音阁"}],
                    "current_conflicts": ["灵潮提前"],
                    "fate_hooks": ["天命奇遇"],
                    "chronicle_0_16": [
                        "零至六岁，许满常听潮声。",
                        "七至十二岁，他在寒门旧屋读残卷。",
                        "十六岁，灵潮把他带到渡口。",
                    ],
                    "initial_situation": "许满抵达潮音渡口。",
                    "initial_situation_16": "十六岁这年，许满抵达潮音渡口。",
                    "opening_narrative": "归墟潮界灵潮提前，许满在十六岁抵达潮音渡口。",
                    "world": {
                        "location": "潮音渡口",
                        "region": "归墟潮界",
                        "current_scene": "潮音渡口正在登记听潮弟子",
                        "lore_facts": ["归墟潮界灵潮提前。"],
                    },
                    "choices": ["稳住渡口差事", "打听灵潮", "夜探沉星礁", "随潮而行"],
                },
                "llm_error": "",
            }
        return _runner(agent_name)

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=dynamic_world_builder):
        started = client.post(
            f"/api/sessions/{session_id}/start",
            json={
                "char_name": "许满",
                "talent": "天命道胎",
                "spirit_root": "雷灵根",
                "family_background": "寒门",
                "difficulty": "普通",
                "randomize_attributes": True,
                "attributes": {
                    "root_bone": 3,
                    "comprehension": 5,
                    "luck": 9,
                    "willpower": 5,
                    "physique": 4,
                    "soul": 4,
                },
            },
        ).json()

    assert started["fallback_prompt"]["active"] is False
    assert any(
        event.get("type") == "model_result"
        and event.get("agent") == "world_builder"
        and event.get("source") == "profile_opening"
        and event.get("status") == "ok"
        for event in started["events"]
    )
    assert started["world"]["world_profile"]["world_name"] == "归墟潮界"
    assert started["world"]["current_scene"] == "潮音渡口正在登记听潮弟子"
    assert started["choices"] == ["稳住渡口差事", "打听灵潮", "夜探沉星礁", "随潮而行"]
    with app.state.service.db.engine.connect() as conn:
        snapshot_text = conn.execute(
            text("SELECT snapshot::text FROM sessions WHERE id = :session_id"),
            {"session_id": session_id},
        ).scalar_one()
    assert "归墟潮界" in snapshot_text
    assert "chronicle_0_16" in snapshot_text


def test_start_model_failure_reports_fallback_but_uses_dynamic_profile_opening(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("AGENS_START_MODEL_OPENING", "1")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]

    def failing_world_builder(agent_name: str, *_args, **_kwargs):
        if agent_name == "world_builder":
            return {"generated_data": {}, "llm_error": "timeout"}
        return _runner(agent_name)

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=failing_world_builder):
        started = client.post(
            f"/api/sessions/{session_id}/start",
            json={
                "char_name": "许满",
                "difficulty": "困难",
                "randomize_attributes": True,
                "attributes": {
                    "root_bone": 2,
                    "comprehension": 4,
                    "luck": 2,
                    "willpower": 8,
                    "physique": 8,
                    "soul": 6,
                },
            },
        ).json()

    assert started["fallback_prompt"]["active"] is True
    assert started["local_story"]["active"] is False
    assert started["world"]["world_profile"]["world_name"] == "西陲裂土"
    assert len(started["choices"]) == 4
    assert any(event.get("type") == "model_failure" for event in started["events"])


def test_incomplete_start_model_output_is_not_live_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("AGENS_START_MODEL_OPENING", "1")
    app = create_app()
    client = TestClient(app)
    _create_invite(app)
    _register(client)
    session_id = client.post("/api/sessions", json={}).json()["session_id"]

    def incomplete_world_builder(agent_name: str, *_args, **_kwargs):
        if agent_name == "world_builder":
            return {
                "generated_data": {
                    "opening_narrative": "模型只给出一段残缺开场。",
                    "choices": ["稳住渡口差事"],
                },
                "llm_error": "",
            }
        return _runner(agent_name)

    with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=incomplete_world_builder):
        started = client.post(
            f"/api/sessions/{session_id}/start",
            json={
                "char_name": "许满",
                "difficulty": "普通",
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

    assert started["fallback_prompt"]["active"] is True
    assert started["world"]["world_profile"].get("chronicle_0_16")
    assert len(started["choices"]) == 4
    assert not any(
        event.get("type") == "model_result"
        and event.get("agent") == "world_builder"
        and event.get("source") == "profile_opening"
        and event.get("status") == "ok"
        for event in started["events"]
    )


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


# ── P4: Death rewards ──────────────────────────────────────────────────


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
                    "root_bone": 5, "comprehension": 5, "luck": 5,
                    "willpower": 5, "physique": 5, "soul": 5,
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
