from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from web.backend.app import create_app


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


def test_web_api_minimum_game_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test-web-api")
    monkeypatch.setenv("AGENS_WEB_DB", str(tmp_path / "agens_web.sqlite3"))
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)

    user = client.post("/api/users/login", json={"username": "local"}).json()
    created = client.post("/api/sessions", json={"user_id": user["id"], "title": "测试局"}).json()
    session_id = created["session_id"]

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
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)
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
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)
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
    app = create_app(tmp_path / "agens_web.sqlite3")
    client = TestClient(app)
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
