"""Shared canned helpers for focused GameEngine turn tests."""

from __future__ import annotations

from typing import Any

from tests.unit.engine.fixtures import canned_judge, canned_world_builder, patch_turn_runner


def canned_narrator() -> dict[str, Any]:
    return {
        "narrative": "你静坐吐纳，灵气缓缓涌入。",
        "state_delta": {"character": {"attributes": {"willpower": 1}}},
        "choices": ["继续吐纳", "请教师兄", "观察灵气流向"],
        "output_path": "",
        "audit_path": "",
        "finished_at": "",
        "llm_error": "",
    }


class FixedRuleRng:
    def __init__(self, value: float) -> None:
        self.value = value

    def random(self, _stream: str) -> float:
        return self.value


def patch_turn_runner_for_tests(call_log: list[str] | None = None) -> Any:
    return patch_turn_runner(
        narrator=canned_narrator,
        judge=canned_judge,
        world_builder=canned_world_builder,
        call_log=call_log,
    )
