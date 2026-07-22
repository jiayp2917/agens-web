"""Deterministic local model playthrough runner for v2 smoke and v3 trials."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from ..artifacts import store
from ..engine.choices import has_visible_english
from ..engine.game_engine import GameEngine
from ..engine.story_catalog import opening_story_binding
from .ledger import EvaluationCallObserver, EvaluationLedger
from .model_config import EvaluationModelConfig
from .scenarios import CanonicalScenarioV1


def run_canonical_playthrough(
    config: EvaluationModelConfig,
    scenario: CanonicalScenarioV1,
    *,
    story_version: int,
    ledger: EvaluationLedger,
    max_turns: int,
    live_opening: bool = False,
    live_judge: bool = False,
) -> dict[str, Any]:
    """Run one fixed-slot evaluation without persisting product state.

    The engine uses its normal narrator path. Rule seed, story binding, and
    slot policy are installed after deterministic profile setup and before the
    first choice, so a provider cannot alter the comparison's authority.
    """
    engine = GameEngine()
    runtime = config.runtime_config()
    engine.model_config = runtime.public_metadata()
    engine.model_runtime_resolver = config.runtime_config
    engine.model_call_observer = EvaluationCallObserver(ledger)
    events: list[dict[str, Any]] = []
    narratives: list[str] = []
    info_messages: list[str] = []
    notices: list[str] = []
    engine.on_narrative = lambda narrative, _turn: narratives.append(str(narrative or ""))
    engine.on_info = lambda message: info_messages.append(str(message or ""))
    engine.on_error = lambda message: notices.append(str(message or ""))
    engine.on_model_result = _model_result_callback(events)

    with _opening_mode(live_opening):
        engine.start_from_profile(scenario.profile)
    _install_canonical_binding(engine, scenario, story_version)

    for slot in scenario.slots[:max_turns]:
        if engine.game_session.game_over:
            break
        before_turn = engine.game_session.turn_count
        engine.handle_action(slot)
        if engine.game_session.turn_count <= before_turn:
            notices.append("turn_did_not_advance")
            break

    judge_status = "not_requested"
    if live_judge and narratives:
        result = engine.run_agent(
            "judge",
            "评估探测",
            engine.game_session,
            narrative=narratives[-1],
            state_delta={},
        )
        judge_status = "ok" if result.get("approved") is True and not result.get("llm_error") else "failed"

    session = engine.game_session
    narrator_events = [event for event in events if event["agent"] == "narrator"]
    opening_events = [event for event in events if event["agent"] == "world_builder"]
    result = {
        "scenario": scenario.key,
        "story_version": story_version,
        "world_key": scenario.world_key,
        "run_seed": scenario.run_seed,
        "turn_count": session.turn_count,
        "game_over": session.game_over,
        "finale": session.finale,
        "end_reason": session.error,
        "story_resolution": str(session.story_state.get("arc_resolution") or ""),
        "story_status": str(session.story_state.get("status") or ""),
        "local_story_active": bool(session.local_story_active),
        "narrator_first_pass_strict": sum(_first_pass_strict(event) for event in narrator_events),
        "narrator_final_strict": sum(event["status"] == "ok" for event in narrator_events),
        "narrator_event_count": len(narrator_events),
        "world_opening_event_count": len(opening_events),
        "world_opening_final_strict": sum(event["status"] == "ok" for event in opening_events),
        "fallback_count": int(session.local_story_active),
        "repair_count": sum(bool(event["diagnostics"].get("repaired_output")) for event in narrator_events),
        "retry_count": sum(_retried(event) for event in narrator_events),
        "visible_english": any(has_visible_english(text) for text in narratives + session.last_choices),
        "notices": notices,
        "info_count": len(info_messages),
        "model_events": events,
        "final_narrative": narratives[-1] if narratives else "",
        "final_choices": list(session.last_choices),
        "judge_status": judge_status,
    }
    run_id = f"{scenario.key}-v{story_version}"
    store.write_audit("playthrough", run_id, result)
    if narratives:
        store.write_output("playthrough", run_id, narratives[-1])
    return result


def _install_canonical_binding(
    engine: GameEngine,
    scenario: CanonicalScenarioV1,
    story_version: int,
) -> None:
    session = engine.game_session
    session.run_seed = scenario.run_seed
    session.rule_rng_counter = 0
    profile = session.world_profile if isinstance(session.world_profile, dict) else {}
    profile["world_key"] = scenario.world_key
    profile["fate_hooks"] = [session.talent, "天命"]
    session.world_profile = profile
    binding = opening_story_binding(
        scenario.world_key,
        profile["fate_hooks"],
        content_version=story_version,
        run_seed=scenario.run_seed,
        character_name=session.char_name,
    )
    session.story_key = str(binding["story_key"])
    session.story_version = int(binding["story_version"])
    session.story_state = dict(binding["story_state"])


def _model_result_callback(events: list[dict[str, Any]]):
    def callback(
        agent: str,
        source: str,
        status: str,
        _model_set: bool,
        _base_url_set: bool,
        _key_set: bool,
        _config_source: str,
        diagnostics: dict[str, Any],
    ) -> None:
        events.append(
            {
                "agent": str(agent),
                "source": str(source),
                "status": str(status),
                "diagnostics": dict(diagnostics) if isinstance(diagnostics, dict) else {},
            }
        )

    return callback


def _first_pass_strict(event: dict[str, Any]) -> bool:
    diagnostics = event["diagnostics"]
    return event["status"] == "ok" and not _retried(event) and not diagnostics.get("repaired_output")


def _retried(event: dict[str, Any]) -> bool:
    diagnostics = event["diagnostics"]
    return bool(
        diagnostics.get("retried_after_request_failed")
        or diagnostics.get("retried_after_incomplete_output")
    )


@contextmanager
def _opening_mode(live_opening: bool) -> Iterator[None]:
    names = ("AGENS_START_MODEL_WORLD", "AGENS_START_MODEL_OPENING")
    previous = {name: os.environ.get(name) for name in names}
    try:
        for name in names:
            os.environ[name] = "1" if live_opening else "0"
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
