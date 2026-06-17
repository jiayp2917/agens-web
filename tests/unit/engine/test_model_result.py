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
        "judge_approved": None,
        "has_corrected_delta": False,
    }
