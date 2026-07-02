"""Tests for model result classification and diagnostics."""

from __future__ import annotations

from agens_novel.engine.model_result import (
    ModelResultKind,
    classify_judge_result,
    classify_narrator_result,
    classify_world_builder_result,
    result_diagnostics,
)


def test_narrator_text_without_choices_is_incomplete() -> None:
    result = {"narrative": "山门风起。", "state_delta": {}, "choices": [], "llm_error": ""}

    status = classify_narrator_result(result)

    assert status.kind == ModelResultKind.INCOMPLETE_OUTPUT
    assert "未返回可用 A/B/C" in status.reason


def test_narrator_choices_without_text_is_incomplete() -> None:
    result = {
        "narrative": "",
        "state_delta": {"character": {}, "world": {}, "meta": {}},
        "choices": ["留在山门吐纳", "询问接引弟子", "冒险下山", "随缘而行"],
        "llm_error": "",
    }

    status = classify_narrator_result(result)

    assert status.kind == ModelResultKind.INCOMPLETE_OUTPUT
    assert "缺少叙事正文" in status.reason


def test_request_failure_is_separate_from_incomplete_output() -> None:
    result = {"narrative": "", "state_delta": {}, "choices": [], "llm_error": "timeout"}

    status = classify_narrator_result(result)

    assert status.kind == ModelResultKind.REQUEST_FAILED
    assert "timeout" in status.reason


def test_world_builder_missing_structured_data_is_incomplete() -> None:
    result = {"generated_data": {}, "world_description": "有文本", "llm_error": ""}

    status = classify_world_builder_result(result)

    assert status.kind == ModelResultKind.INCOMPLETE_OUTPUT


def test_judge_llm_error_is_judge_failed() -> None:
    result = {"approved": False, "corrected_delta": {}, "llm_error": "HTTP 500"}

    status = classify_judge_result(result)

    assert status.kind == ModelResultKind.JUDGE_FAILED


def test_result_diagnostics_are_non_secret_shape_facts() -> None:
    result = {
        "narrative": "获得清灵丹。",
        "state_delta": {"character": {"inventory_add": [{"name": "清灵丹"}]}},
        "choices": ["查看丹药", "继续前行", "请教师兄"],
        "elapsed_ms": 1234,
        "llm_error": "",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        "prompt_metrics": {
            "prompt_chars": 100,
            "message_count": 3,
            "history_count": 2,
            "game_state_chars": 50,
            "user_input_chars": 6,
        },
    }

    diagnostics = result_diagnostics(result)

    assert diagnostics == {
        "elapsed_ms": 1234,
        "has_error": False,
        "has_narrative": True,
        "state_delta_ok": True,
        "choices_count": 3,
        "generated_ok": False,
        "repaired_output": False,
        "repair_elapsed_ms": 0,
        "judge_approved": None,
        "has_corrected_delta": False,
        "prompt_chars": 100,
        "message_count": 3,
        "history_count": 2,
        "game_state_chars": 50,
        "user_input_chars": 6,
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30,
        "repair_prompt_tokens": 0,
        "repair_completion_tokens": 0,
    }


def test_result_diagnostics_include_repair_metrics_without_text() -> None:
    result = {
        "narrative": "山门风紧。",
        "state_delta": {},
        "choices": ["吐纳", "询问", "历练", "随缘"],
        "elapsed_ms": 1000,
        "repaired_output": True,
        "repair_elapsed_ms": 300,
        "repair_usage": {"prompt_tokens": 40, "completion_tokens": 12},
    }

    diagnostics = result_diagnostics(result)

    assert diagnostics["repaired_output"] is True
    assert diagnostics["repair_elapsed_ms"] == 300
    assert diagnostics["repair_prompt_tokens"] == 40
    assert diagnostics["repair_completion_tokens"] == 12
    assert "narrative" not in diagnostics
    assert "api_key" not in diagnostics
