"""Model-result classification for engine/UI feedback."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .choices import normalize_choices


class ModelResultKind(StrEnum):
    """High-level result categories exposed to UI prompts and logs."""

    OK = "ok"
    REQUEST_FAILED = "request_failed"
    INCOMPLETE_OUTPUT = "incomplete_output"
    LOCAL_FALLBACK = "local_fallback"


@dataclass(frozen=True)
class ModelResultStatus:
    """Classified status for one model call."""

    kind: ModelResultKind
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.kind == ModelResultKind.OK

    @property
    def label(self) -> str:
        """Stable short label for logs and UI routing."""
        return self.kind.value


def classify_narrator_result(result: dict[str, Any]) -> ModelResultStatus:
    """Classify a narrator result without mutating it."""
    if result.get("llm_error"):
        return ModelResultStatus(
            ModelResultKind.REQUEST_FAILED,
            f"叙述失败: {result['llm_error']}",
        )
    narrative = str(result.get("narrative") or "").strip()
    choices = normalize_choices(result.get("choices"))
    contract_value = result.get("contract_diagnostics")
    contract: dict[str, Any] = contract_value if isinstance(contract_value, dict) else {}
    contract_failure = _narrator_contract_failure(result, contract)
    if contract_failure is not None:
        return contract_failure

    if not narrative:
        return ModelResultStatus(ModelResultKind.INCOMPLETE_OUTPUT, "模型输出缺少叙事正文。")
    if narrative and not choices:
        return ModelResultStatus(
            ModelResultKind.INCOMPLETE_OUTPUT, "模型已返回叙事，但未返回可用 A/B/C/D 选项。"
        )
    if len(choices) != 4:
        return ModelResultStatus(
            ModelResultKind.INCOMPLETE_OUTPUT, "模型已返回叙事，但未返回恰好 4 个 A/B/C/D 选项。"
        )
    return ModelResultStatus(ModelResultKind.OK)


def _narrator_contract_failure(
    result: dict[str, Any],
    contract: dict[str, Any],
) -> ModelResultStatus | None:
    transport = str(result.get("response_mode") or result.get("provider_transport") or "").strip()
    if transport and transport not in {"json_schema", "json_object"}:
        return ModelResultStatus(ModelResultKind.INCOMPLETE_OUTPUT, "模型返回了未知传输格式。")
    if transport and not result.get("provider_json_envelope_ok"):
        return ModelResultStatus(
            ModelResultKind.INCOMPLETE_OUTPUT,
            "模型未按 provider JSON 契约返回完整字段。",
        )
    if contract.get("structured_residue"):
        return ModelResultStatus(ModelResultKind.INCOMPLETE_OUTPUT, "模型可见文本仍含结构化残留。")
    if contract.get("english_residue"):
        return ModelResultStatus(ModelResultKind.INCOMPLETE_OUTPUT, "模型可见文本仍含英文残留。")
    return None


def classify_world_builder_result(result: dict[str, Any]) -> ModelResultStatus:
    """Classify a world-builder result."""
    if result.get("llm_error"):
        return ModelResultStatus(
            ModelResultKind.REQUEST_FAILED,
            f"世界生成失败: {result['llm_error']}",
        )
    generated = result.get("generated_data")
    if not isinstance(generated, dict) or not generated:
        return ModelResultStatus(
            ModelResultKind.INCOMPLETE_OUTPUT, "世界生成已返回，但缺少结构化开局数据。"
        )
    return ModelResultStatus(ModelResultKind.OK)


def is_retryable_model_request_failure(result: dict[str, Any]) -> bool:
    """Return True for transient provider failures worth one live retry."""
    if not isinstance(result, dict):
        return False
    error = str(result.get("llm_error") or "").lower()
    if not error:
        return False
    if any(marker in error for marker in ("api_key", "missing key", "401", "403")):
        return False
    retry_markers = (
        "timeout",
        "timed out",
        "temporarily",
        "connection",
        "http 408",
        "http 425",
        "http 429",
        "http 500",
        "http 502",
        "http 503",
        "http 504",
        "http 520",
        "upstream_error",
        "notfounderror",
    )
    return any(marker in error for marker in retry_markers)


def result_diagnostics(result: dict[str, Any]) -> dict[str, Any]:
    """Return non-secret model result facts suitable for logcat diagnostics."""
    generated = result.get("generated_data")
    narrative = (
        result.get("narrative")
        or result.get("opening_narrative")
        or result.get("world_description")
        or ""
    )
    state_delta = result.get("state_delta")
    raw_choices = result.get("choices")
    usage_value = result.get("usage")
    repair_usage_value = result.get("repair_usage")
    prompt_metrics_value = result.get("prompt_metrics")
    contract_value = result.get("contract_diagnostics")
    response_value = result.get("response_diagnostics")
    usage: dict[str, Any] = usage_value if isinstance(usage_value, dict) else {}
    repair_usage: dict[str, Any] = (
        repair_usage_value if isinstance(repair_usage_value, dict) else {}
    )
    prompt_metrics: dict[str, Any] = (
        prompt_metrics_value if isinstance(prompt_metrics_value, dict) else {}
    )
    contract: dict[str, Any] = contract_value if isinstance(contract_value, dict) else {}
    response: dict[str, Any] = response_value if isinstance(response_value, dict) else {}
    choice_english_indices = _choice_english_indices(contract.get("choice_english_indices"))
    if isinstance(generated, dict):
        raw_choices = generated.get("choices", raw_choices)
        narrative = generated.get("opening_narrative") or narrative
    return {
        "elapsed_ms": int(result.get("elapsed_ms") or 0),
        "has_error": bool(result.get("llm_error")),
        "has_narrative": bool(str(narrative).strip()),
        "state_delta_ok": isinstance(state_delta, dict),
        "choices_count": len(normalize_choices(raw_choices)),
        "generated_ok": isinstance(generated, dict) and bool(generated),
        "repaired_output": bool(result.get("repaired_output")),
        "retried_after_request_failed": bool(result.get("retried_after_request_failed")),
        "retried_after_incomplete_output": bool(result.get("retried_after_incomplete_output")),
        "repair_elapsed_ms": int(result.get("repair_elapsed_ms") or 0),
        "prompt_chars": _int_metric(prompt_metrics.get("prompt_chars")),
        "message_count": _int_metric(prompt_metrics.get("message_count")),
        "history_count": _int_metric(prompt_metrics.get("history_count")),
        "game_state_chars": _int_metric(prompt_metrics.get("game_state_chars")),
        "user_input_chars": _int_metric(prompt_metrics.get("user_input_chars")),
        "prompt_tokens": _int_metric(usage.get("prompt_tokens")),
        "completion_tokens": _int_metric(usage.get("completion_tokens")),
        "total_tokens": _int_metric(usage.get("total_tokens")),
        "repair_prompt_tokens": _int_metric(repair_usage.get("prompt_tokens")),
        "repair_completion_tokens": _int_metric(repair_usage.get("completion_tokens")),
        "contract_missing_narrative": bool(contract.get("missing_narrative")),
        "contract_missing_state_update": bool(contract.get("missing_state_update")),
        "contract_choices_count_ok": bool(contract.get("choices_count_ok")),
        "contract_raw_has_state_update_tag": bool(contract.get("raw_has_state_update_tag")),
        "contract_raw_has_choices_tag": bool(contract.get("raw_has_choices_tag")),
        "contract_structured_residue": bool(contract.get("structured_residue")),
        "contract_english_residue": bool(contract.get("english_residue")),
        "contract_narrative_english_residue": bool(contract.get("narrative_english_residue")),
        "contract_choice_english_indices": choice_english_indices,
        "provider_transport": str(result.get("provider_transport") or "legacy_tags"),
        "provider_json_schema": bool(result.get("provider_json_schema")),
        "provider_json_object": bool(result.get("provider_json_object")),
        "provider_json_envelope_ok": bool(result.get("provider_json_envelope_ok")),
        "llm_error_code": _safe_error_code(result.get("llm_error_code")),
        "response_transport_error_category": _safe_transport_error_category(
            response.get("transport_error_category")
        ),
        "response_finish_reason": _safe_finish_reason(response.get("finish_reason")),
        "response_content_present": bool(response.get("content_present")),
        "response_content_length": _int_metric(response.get("content_length")),
        "response_reasoning_content_present": bool(response.get("reasoning_content_present")),
        "response_refusal_present": bool(response.get("refusal_present")),
        "response_choices_present": bool(response.get("choices_present")),
        "response_message_present": bool(response.get("message_present")),
    }


def _int_metric(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _safe_error_code(value: Any) -> str:
    code = str(value or "")
    allowed = {
        "",
        "llm_error",
        "empty_completion",
        "refusal_completion",
        "malformed_response",
        "unsafe_base_url",
        "timeout",
        "transport_unavailable",
        "http_redirect",
        "http_400",
        "http_401",
        "http_403",
        "http_404",
        "http_408",
        "http_413",
        "http_422",
        "http_425",
        "http_429",
        "http_5xx",
        "http_other",
    }
    return code if code in allowed else "other"


def _safe_transport_error_category(value: Any) -> str:
    category = str(value or "")
    allowed = {
        "",
        "total_timeout",
        "connect_timeout",
        "read_timeout",
        "write_timeout",
        "pool_timeout",
        "connect_error",
        "protocol_error",
        "transport_error",
        "unknown",
    }
    return category if category in allowed else "other"


def _safe_finish_reason(value: Any) -> str:
    reason = str(value or "missing")
    return reason if reason in {
        "stop",
        "length",
        "content_filter",
        "tool_calls",
        "function_call",
        "refusal",
        "missing",
        "other",
    } else "other"


def _choice_english_indices(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    return [
        index
        for index in value
        if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < 4
    ]
