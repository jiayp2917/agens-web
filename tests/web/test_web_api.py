from __future__ import annotations

import socket
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from agens_novel.engine.choices import choice_with_semantic
from agens_novel.engine.turn_rules import classify_choice
from agens_novel.game.constants import ATTRIBUTE_KEYS
from web.backend.app import create_app
from web.backend.auth import hash_invite_code

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
        action = choice_with_semantic(index, "\u5c71\u95e8\u4fee\u884c")
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
        assert chosen["choices"][:3] == ["继续请教", "前往住处", "查看木牌"]
        assert "气运" in chosen["choices"][3]
        assert "早开灵草" in chosen["choices"][3]

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
    fallback_text = body["fallback_prompt"]["text"]
    assert "已切换本地故事" in fallback_text
    assert "模型暂不可用" in fallback_text
    assert "状态更新格式不完整" not in fallback_text
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

def test_model_failure_prompt_uses_sanitized_public_http_404_notice(
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
    assert "叙事服务配置暂未接通" in text_value
    assert "系统默认" in text_value
    assert "HTTP 404" not in text_value
    assert "Base URL" not in text_value
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
    assert any("本回合记录暂未续上" in text for text in visible_texts)
    for text_value in visible_texts:
        assert "sk-" not in text_value
        assert "Authorization" not in text_value
        assert "x-api-key" not in text_value
        assert "provider.example" not in text_value
        assert "https://" not in text_value

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

def _use_public_model_dns(monkeypatch) -> None:
    monkeypatch.setattr(
        "agens_novel.llm.url_security.socket.getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
        ],
    )
