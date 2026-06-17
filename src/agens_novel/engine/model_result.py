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
    if narrative and not choices:
        return ModelResultStatus(ModelResultKind.INCOMPLETE_OUTPUT, "模型已返回叙事，但未返回可用 A/B/C 选项。")
    if not narrative and not choices:
        return ModelResultStatus(ModelResultKind.INCOMPLETE_OUTPUT, "模型输出缺少叙事和 A/B/C 选项。")
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
