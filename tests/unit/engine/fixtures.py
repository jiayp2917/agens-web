"""Reusable canned agent responses for GameEngine unit tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from agens_novel.engine.world_generator import build_world_fallback
from agens_novel.session.game_session import GameSession

AgentResult = Callable[[], dict[str, Any]]


def canned_world_builder() -> dict[str, Any]:
    generated = build_world_fallback(
        {
            "char_name": "许满",
            "spirit_root": "火木双灵根",
            "spirit_root_grade": "地",
        }
    )
    generated["world"].update(
        {
            "current_scene": "晨雾中的青云山外门",
            "location": "青云山外门",
            "region": "东荒",
        }
    )
    return {
        "generated_data": generated,
        "world_description": "",
        "opening_narrative": "",
        "output_path": "",
        "audit_path": "",
        "finished_at": "",
        "llm_error": "",
        "response_mode": "json_object",
        "provider_json_envelope_ok": True,
    }


def canned_judge() -> dict[str, Any]:
    return {
        "approved": True,
        "corrected_delta": {},
        "judgment_note": "ok",
        "review_score": 8,
        "output_path": "",
        "audit_path": "",
        "finished_at": "",
        "llm_error": "",
    }


def patch_turn_runner(
    *,
    world_builder: AgentResult = canned_world_builder,
    judge: AgentResult = canned_judge,
    narrator: AgentResult | None = None,
    call_log: list[str] | None = None,
) -> Any:
    calls = call_log if call_log is not None else []

    def fake_run_turn_sync(
        agent_name: str, _user_input: str, _session: GameSession, **_kwargs: Any
    ) -> dict[str, Any]:
        calls.append(agent_name)
        if agent_name == "narrator" and narrator is not None:
            return narrator()
        if agent_name == "judge":
            return judge()
        if agent_name == "world_builder":
            return world_builder()
        return {}

    return patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_run_turn_sync)
