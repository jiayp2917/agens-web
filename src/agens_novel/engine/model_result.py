"""Model-result classification for engine/UI feedback."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .choices import normalize_choices


class ModelResultKind(str, Enum):
    """High-level result categories exposed to UI prompts and logs."""

    OK = "ok"
    REQUEST_FAILED = "request_failed"
    INCOMPLETE_OUTPUT = "incomplete_output"
    JUDGE_FAILED = "judge_failed"
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
    state_delta = result.get("state_delta")
    choices = normalize_choices(result.get("choices"))

    if state_delta is None or not isinstance(state_delta, dict):
        return ModelResultStatus(ModelResultKind.INCOMPLETE_OUTPUT, "模型已返回叙事，但状态更新格式不完整。")
    if not narrative:
        return ModelResultStatus(ModelResultKind.INCOMPLETE_OUTPUT, "模型输出缺少叙事正文。")
    if narrative and not choices:
        return ModelResultStatus(ModelResultKind.INCOMPLETE_OUTPUT, "模型已返回叙事，但未返回可用 A/B/C/D 选项。")
    return ModelResultStatus(ModelResultKind.OK)


def classify_world_builder_result(result: dict[str, Any]) -> ModelResultStatus:
    """Classify a world-builder result."""
    if result.get("llm_error"):
        return ModelResultStatus(
            ModelResultKind.REQUEST_FAILED,
            f"世界生成失败: {result['llm_error']}",
        )
    generated = result.get("generated_data")
    if not isinstance(generated, dict) or not generated:
        return ModelResultStatus(ModelResultKind.INCOMPLETE_OUTPUT, "世界生成已返回，但缺少结构化开局数据。")
    return ModelResultStatus(ModelResultKind.OK)


def classify_judge_result(result: dict[str, Any]) -> ModelResultStatus:
    """Classify a judge result."""
    if result.get("llm_error"):
        return ModelResultStatus(
            ModelResultKind.JUDGE_FAILED,
            f"天道审判失败: {result['llm_error']}",
        )
    return ModelResultStatus(ModelResultKind.OK)


def result_diagnostics(result: dict[str, Any]) -> dict[str, Any]:
    """Return non-secret model result facts suitable for logcat diagnostics."""
    generated = result.get("generated_data")
    narrative = result.get("narrative") or result.get("opening_narrative") or result.get("world_description") or ""
    state_delta = result.get("state_delta")
    raw_choices = result.get("choices")
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    repair_usage = result.get("repair_usage") if isinstance(result.get("repair_usage"), dict) else {}
    prompt_metrics = result.get("prompt_metrics") if isinstance(result.get("prompt_metrics"), dict) else {}
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
        "repair_elapsed_ms": int(result.get("repair_elapsed_ms") or 0),
        "judge_approved": result.get("approved") if "approved" in result else None,
        "has_corrected_delta": bool(result.get("corrected_delta")),
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
    }


def _int_metric(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
