"""Tests for web service model diagnostic event hygiene."""

from __future__ import annotations

from web.backend.service import WebRunner


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
