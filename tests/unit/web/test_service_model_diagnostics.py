"""Tests for web service model diagnostic event hygiene."""

from __future__ import annotations

from web.backend.service import PUBLIC_MODEL_FALLBACK_TEXT, WebRunner


def test_web_runner_records_only_sanitized_model_diagnostics() -> None:
    runner = WebRunner(session_id="session-1", user_id="user-1")

    runner._record_model_result(
        "narrator",
        "turn",
        "ok",
        True,
        True,
        True,
        "system",
        {
            "elapsed_ms": 1000,
            "prompt_chars": 1200,
            "prompt_tokens": 500,
            "repaired_output": True,
            "raw_text": "should be dropped",
            "api_key": "should be dropped",
        },
    )

    event = runner.events[-1]

    assert event["type"] == "model_result"
    assert event["agent"] == "narrator"
    assert event["model_set"] is True
    assert event["base_url_set"] is True
    assert "model" not in event
    assert "base_url" not in event
    assert event["diagnostics"]["elapsed_ms"] == 1000
    assert event["diagnostics"]["prompt_chars"] == 1200
    assert event["diagnostics"]["prompt_tokens"] == 500
    assert event["diagnostics"]["repaired_output"] is True
    assert "raw_text" not in event["diagnostics"]
    assert "api_key" not in event["diagnostics"]


def test_web_runner_fallback_prompt_uses_current_failure_state() -> None:
    runner = WebRunner(session_id="session-1", user_id="user-1")

    runner._choose_model_failure("turn", "HTTP 404")
    assert runner.response()["fallback_prompt"]["active"] is True

    runner._record_model_result(
        "narrator",
        "turn",
        "ok",
        True,
        True,
        True,
        "system",
        {"elapsed_ms": 1000},
    )

    assert runner.response()["fallback_prompt"]["active"] is False


def test_web_runner_historical_model_failure_event_does_not_keep_prompt_active() -> None:
    runner = WebRunner(session_id="session-1", user_id="user-1")
    runner.record("model_failure", text="历史模型不可用提示", source="turn")

    assert runner.response()["fallback_prompt"]["active"] is False


def test_web_runner_does_not_force_streaming_by_default(monkeypatch) -> None:
    monkeypatch.delenv("AGENS_WEB_STREAMING", raising=False)

    runner = WebRunner(session_id="session-1", user_id="user-1")

    assert runner.engine.on_stream_chunk is None


def test_web_runner_streaming_can_be_enabled_by_env(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_WEB_STREAMING", "1")

    runner = WebRunner(session_id="session-1", user_id="user-1")

    assert runner.engine.on_stream_chunk is not None


def test_web_runner_local_story_still_keeps_fallback_prompt_active() -> None:
    runner = WebRunner(session_id="session-1", user_id="user-1")
    runner.engine.game_session.local_story_active = True

    assert runner.response()["fallback_prompt"]["active"] is True


def test_web_runner_from_snapshot_restores_current_fallback_prompt_state() -> None:
    source = WebRunner(session_id="session-1", user_id="user-1")
    snapshot = source.snapshot()

    restored = WebRunner.from_snapshot(
        "session-1",
        "user-1",
        snapshot,
        events=[
            {
                "type": "model_failure",
                "text": PUBLIC_MODEL_FALLBACK_TEXT,
                "source": "profile_opening_missing_key",
            }
        ],
    )

    assert restored.response()["fallback_prompt"]["active"] is True
    assert restored.response()["fallback_prompt"]["text"] == PUBLIC_MODEL_FALLBACK_TEXT


def test_web_runner_from_snapshot_clears_fallback_prompt_after_recovered_model_result() -> None:
    source = WebRunner(session_id="session-1", user_id="user-1")
    snapshot = source.snapshot()

    restored = WebRunner.from_snapshot(
        "session-1",
        "user-1",
        snapshot,
        events=[
            {"type": "model_failure", "text": PUBLIC_MODEL_FALLBACK_TEXT, "source": "turn"},
            {
                "type": "model_result",
                "agent": "narrator",
                "source": "turn",
                "status": "ok",
            },
        ],
    )

    assert restored.response()["fallback_prompt"]["active"] is False
