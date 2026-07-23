"""Web-visible model failure and retry coverage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.web.api_fixtures import _create_invite, _register, _runner
from web.backend.app import create_app

pytestmark = pytest.mark.xdist_group("pg_test_db")

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
