"""Tests for model result classification and diagnostics."""

from __future__ import annotations

from agens_novel.engine.model_result import (
    ModelResultKind,
    classify_judge_result,
    classify_narrator_result,
    classify_world_builder_result,
    is_retryable_model_request_failure,
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


def test_narrator_requires_exactly_four_choices() -> None:
    result = {
        "narrative": "山门风起，外门弟子各自择路。",
        "state_delta": {"character": {}, "world": {}, "meta": {}},
        "choices": ["闭关", "拜访同门", "探查山径"],
        "llm_error": "",
    }

    status = classify_narrator_result(result)

    assert status.kind == ModelResultKind.INCOMPLETE_OUTPUT
    assert "恰好 4 个" in status.reason


def test_narrator_visible_contract_residue_is_incomplete() -> None:
    base = {
        "narrative": "山门风起，外门弟子各自择路。",
        "state_delta": {"character": {}, "world": {}, "meta": {}},
        "choices": ["闭关", "拜访同门", "探查山径", "随缘而行"],
        "llm_error": "",
    }

    structured = classify_narrator_result({
        **base,
        "contract_diagnostics": {"structured_residue": True},
    })
    english = classify_narrator_result({
        **base,
        "contract_diagnostics": {"english_residue": True},
    })

    assert structured.kind == ModelResultKind.INCOMPLETE_OUTPUT
    assert "结构化残留" in structured.reason
    assert english.kind == ModelResultKind.INCOMPLETE_OUTPUT
    assert "英文残留" in english.reason


def test_schema_narrator_requires_accepted_provider_envelope() -> None:
    result = {
        "narrative": "山门名册已有变化。",
        "state_delta": {},
        "choices": ["闭关", "寻访", "历练", "随缘"],
        "provider_json_schema": True,
        "provider_transport": "json_schema",
        "provider_json_envelope_ok": False,
    }

    status = classify_narrator_result(result)

    assert status.kind == ModelResultKind.INCOMPLETE_OUTPUT
    assert "JSON" in status.reason


def test_narrator_compatibility_parse_without_raw_tags_is_not_strict_ok() -> None:
    result = {
        "narrative": "山门风起，外门弟子各自择路。",
        "state_delta": {"character": {}, "world": {}, "meta": {}},
        "choices": ["闭关", "拜访同门", "探查山径", "随缘而行"],
        "llm_error": "",
        "contract_diagnostics": {
            "raw_has_state_update_tag": False,
            "raw_has_choices_tag": False,
        },
    }

    status = classify_narrator_result(result)

    assert status.kind == ModelResultKind.INCOMPLETE_OUTPUT
    assert "choices 标签" in status.reason


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


def test_retryable_model_request_failure_detects_transient_provider_errors() -> None:
    assert is_retryable_model_request_failure(
        {"llm_error": 'HTTP 404: {"error":{"type":"upstream_error","code":"404"}}'}
    )
    assert is_retryable_model_request_failure({"llm_error": "request timed out"})
    assert not is_retryable_model_request_failure({"llm_error": "HTTP 401 unauthorized"})
    assert not is_retryable_model_request_failure({"llm_error": "AGNES_API_KEY missing"})


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
        "retried_after_request_failed": False,
        "retried_after_incomplete_output": False,
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
        "contract_missing_narrative": False,
        "contract_missing_state_update": False,
        "contract_choices_count_ok": False,
        "contract_raw_has_state_update_tag": False,
        "contract_raw_has_choices_tag": False,
        "contract_structured_residue": False,
        "contract_english_residue": False,
        "contract_narrative_english_residue": False,
        "contract_choice_english_indices": [],
        "provider_json_schema": False,
        "provider_json_envelope_ok": False,
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


def test_result_diagnostics_include_incomplete_retry_flag_without_text() -> None:
    result = {
        "narrative": "山门风紧。",
        "state_delta": {},
        "choices": ["吐纳", "询问", "历练", "随缘"],
        "retried_after_incomplete_output": True,
    }

    diagnostics = result_diagnostics(result)

    assert diagnostics["retried_after_incomplete_output"] is True
    assert "narrative" not in diagnostics
    assert "api_key" not in diagnostics
