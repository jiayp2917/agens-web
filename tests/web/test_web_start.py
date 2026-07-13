"""Character creation and model-assisted opening coverage."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.web.test_web_api import _create_invite, _register, _runner
from web.backend.app import create_app

pytestmark = pytest.mark.xdist_group("pg_test_db")


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
    assert "模型暂不可用，已切换本地故事，请直接选择下方选项继续。" in body

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
