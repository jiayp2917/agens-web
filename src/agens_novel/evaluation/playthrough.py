"""Deterministic local model playthrough runner for v2 smoke and v3 trials."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from ..artifacts import sink, store
from ..engine.choices import has_visible_english
from ..engine.game_engine import GameEngine
from ..engine.story_catalog import opening_story_binding
from ..session.game_session import GameSession
from .ledger import EvaluationCallObserver, EvaluationLedger
from .model_config import EvaluationModelConfig
from .scenarios import CanonicalScenarioV1, canonical_scenario_hash


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
    expected_trajectory = canonical_authority_trajectory(
        scenario,
        story_version=story_version,
        max_turns=max_turns,
    )
    engine = GameEngine()
    engine.model_config = config.public_metadata()
    engine.model_runtime_resolver = config.runtime_config
    engine.model_call_observer = EvaluationCallObserver(ledger)
    events: list[dict[str, Any]] = []
    opening_events: list[dict[str, Any]] = []
    narratives: list[str] = []
    info_messages: list[str] = []
    notices: list[str] = []
    engine.on_narrative = lambda narrative, _turn: narratives.append(str(narrative or ""))
    engine.on_info = lambda message: info_messages.append(str(message or ""))
    engine.on_error = lambda message: notices.append(str(message or ""))
    engine.on_model_result = _model_result_callback(events, scope="turn")

    if live_opening:
        opening_engine = GameEngine()
        opening_engine.model_config = config.public_metadata()
        opening_engine.model_runtime_resolver = config.runtime_config
        opening_engine.model_call_observer = EvaluationCallObserver(ledger)
        opening_engine.on_model_result = _model_result_callback(opening_events, scope="opening")
        with _opening_mode(True):
            opening_engine.start_from_profile(scenario.profile)
    with _opening_mode(False):
        engine.start_from_profile(scenario.profile)
    install_canonical_binding(engine, scenario, story_version)
    accepted_turns: list[dict[str, Any]] = []

    for index, slot in enumerate(scenario.slots[:max_turns]):
        if engine.game_session.game_over:
            break
        before_turn = engine.game_session.turn_count
        event_index = len(events)
        call_index = ledger.call_count
        started = time.monotonic()
        engine.handle_action(canonical_action_for_slot(slot))
        if engine.game_session.turn_count <= before_turn:
            notices.append("turn_did_not_advance")
            break
        accepted_turns.append(
            _accepted_turn_record(
                engine.game_session,
                slot=slot,
                expected=expected_trajectory[index] if index < len(expected_trajectory) else None,
                model_events=events[event_index:],
                calls=ledger.calls_since(call_index),
                end_to_end_ms=int((time.monotonic() - started) * 1000),
            )
        )

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
    world_opening_events = [event for event in opening_events if event["agent"] == "world_builder"]
    result = {
        "scenario": scenario.key,
        "story_version": story_version,
        "world_key": scenario.world_key,
        "story_key": session.story_key,
        "story_version_bound": session.story_version,
        "scenario_hash": canonical_scenario_hash(scenario, story_version=story_version),
        "run_seed": scenario.run_seed,
        "turn_count": session.turn_count,
        "game_over": session.game_over,
        "finale": session.finale,
        "end_reason": session.error,
        "story_resolution": str(session.story_state.get("arc_resolution") or ""),
        "story_status": str(session.story_state.get("status") or ""),
        "local_story_active": bool(session.local_story_active),
        "narrator_first_pass_strict": sum(item["strict"]["first_pass"] for item in accepted_turns),
        "narrator_final_strict": sum(item["strict"]["final"] for item in accepted_turns),
        "narrator_event_count": len(narrator_events),
        "world_opening_event_count": len(world_opening_events),
        "world_opening_final_strict": sum(event["status"] == "ok" for event in world_opening_events),
        "fallback_count": sum(item["fallback"] for item in accepted_turns),
        "repair_count": sum(item["repair"] for item in accepted_turns),
        "recovery_count": sum(item["recovery"] for item in accepted_turns),
        "retry_count": sum(item["retry"] for item in accepted_turns),
        "authority_mismatch_count": sum(not item["authority"]["matches_expected"] for item in accepted_turns),
        "visible_english": any(has_visible_english(text) for text in narratives + session.last_choices),
        "notices": notices,
        "info_count": len(info_messages),
        "model_events": [*opening_events, *events],
        "accepted_turns": accepted_turns,
        "final_narrative": narratives[-1] if narratives else "",
        "final_choices": list(session.last_choices),
        "judge_status": judge_status,
    }
    run_id = f"{scenario.key}-v{story_version}-{store.new_run_id()}"
    store.write_audit("playthrough", run_id, result)
    sink.write_json("playthrough", run_id, "accepted-turns.json", {"turns": accepted_turns})
    if narratives:
        store.write_output("playthrough", run_id, narratives[-1])
    return result


def canonical_authority_trajectory(
    scenario: CanonicalScenarioV1,
    *,
    story_version: int,
    max_turns: int,
) -> tuple[dict[str, Any], ...]:
    """Replay real rules with a deterministic narrator that cannot alter state."""
    engine = _RuleReplayEngine()
    with _opening_mode(False):
        engine.start_from_profile(scenario.profile)
    install_canonical_binding(engine, scenario, story_version)
    trajectory: list[dict[str, Any]] = []
    for slot in canonical_slots(scenario, max_turns=max_turns):
        if engine.game_session.game_over:
            break
        before_turn = engine.game_session.turn_count
        engine.handle_action(canonical_action_for_slot(slot))
        if engine.game_session.turn_count <= before_turn:
            raise RuntimeError("canonical rule replay did not advance")
        trajectory.append(
            {
                "turn": engine.game_session.turn_count,
                "slot": slot,
                "authority_hash": authority_state_hash(engine.game_session),
            }
        )
    return tuple(trajectory)


def canonical_replay_session(
    scenario: CanonicalScenarioV1,
    *,
    story_version: int,
    target_turn: int,
) -> GameSession:
    """Build a frozen state from the catalog and rule replay, never a hand stub."""
    engine = _RuleReplayEngine()
    with _opening_mode(False):
        engine.start_from_profile(scenario.profile)
    install_canonical_binding(engine, scenario, story_version)
    for slot in canonical_slots(scenario, max_turns=max(0, target_turn)):
        if engine.game_session.game_over:
            break
        engine.handle_action(canonical_action_for_slot(slot))
    return GameSession.from_save_dict(engine.game_session.to_save_dict())


def install_canonical_authority(
    engine: GameEngine,
    scenario: CanonicalScenarioV1,
    *,
    story_version: int,
) -> None:
    """Restore the frozen authority baseline after a live display-only opening."""
    display_choices = list(engine.game_session.last_choices)
    engine.game_session = canonical_replay_session(
        scenario,
        story_version=story_version,
        target_turn=0,
    )
    if len(display_choices) == 4:
        engine.game_session.last_choices = display_choices


def authority_state_hash(session: GameSession) -> str:
    """Hash only state that deterministic turn rules own across providers."""
    payload = {
        "turn_count": session.turn_count,
        "realm_turn_count": session.realm_turn_count,
        "game_started": session.game_started,
        "game_over": session.game_over,
        "finale": bool(session.finale),
        "error": str(session.error or ""),
        "run_seed": session.run_seed,
        "rule_rng_counter": session.rule_rng_counter,
        "local_story_active": bool(session.local_story_active),
        "character": {
            "realm": session.realm,
            "realm_stage": session.realm_stage,
            "age": session.age,
            "attributes": session.attributes,
            "breakthrough_flags": session.breakthrough_flags,
            "titles": session.titles,
            "relationships": session.relationships,
            "status_effects": session.status_effects,
            "lifespan": session.lifespan,
        },
        "story": {
            "key": session.story_key,
            "version": session.story_version,
            "state": session.story_state,
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def canonical_slots(
    scenario: CanonicalScenarioV1,
    *,
    max_turns: int,
) -> tuple[str, ...]:
    """Extend a registered slot policy only for deterministic post-arc probes."""
    count = max(0, int(max_turns))
    if count <= len(scenario.slots):
        return scenario.slots[:count]
    if not scenario.slots:
        return ()
    return scenario.slots + (scenario.slots[-1],) * (count - len(scenario.slots))


def install_canonical_binding(
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


def _model_result_callback(events: list[dict[str, Any]], *, scope: str):
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
                "scope": scope,
                "agent": str(agent),
                "source": str(source),
                "status": str(status),
                "diagnostics": dict(diagnostics) if isinstance(diagnostics, dict) else {},
            }
        )

    return callback


def _accepted_turn_record(
    session: GameSession,
    *,
    slot: str,
    expected: dict[str, Any] | None,
    model_events: list[dict[str, Any]],
    calls: tuple[Any, ...],
    end_to_end_ms: int,
) -> dict[str, Any]:
    entry = session.turn_history[-1] if session.turn_history else {}
    delta = entry.get("delta") if isinstance(entry, dict) else {}
    meta = delta.get("meta") if isinstance(delta, dict) else {}
    safe_meta = meta if isinstance(meta, dict) else {}
    narrator_events = [event for event in model_events if event.get("agent") == "narrator"]
    diagnostics: list[dict[str, Any]] = []
    for event in narrator_events:
        diagnostic = event.get("diagnostics")
        if isinstance(diagnostic, dict):
            diagnostics.append(diagnostic)
    final_strict = bool(narrator_events) and narrator_events[-1].get("status") == "ok"
    retry = any(_retried(event) for event in narrator_events)
    repair = any(bool(item.get("repaired_output")) for item in diagnostics)
    recovery = any(event.get("status") == "incomplete_output" for event in narrator_events)
    fallback = bool(session.local_story_active) or any(event.get("status") == "local_fallback" for event in narrator_events)
    actual_hash = authority_state_hash(session)
    expected_hash = str(expected.get("authority_hash") or "") if expected else ""
    full_response_ms = sum(int(getattr(call, "elapsed_ms", 0) or 0) for call in calls)
    ttft_values = [getattr(call, "ttft_ms", None) for call in calls]
    return {
        "turn": int(session.turn_count),
        "slot": slot,
        "intent_category": str(safe_meta.get("choice_category") or ""),
        "event_id": str(safe_meta.get("event_id") or ""),
        "motif": _current_motif(session),
        "rule_outcome": str(safe_meta.get("turn_summary") or ""),
        "narrative": str(entry.get("narrative") or "") if isinstance(entry, dict) else "",
        "choices": list(entry.get("choices") or []) if isinstance(entry, dict) else [],
        "strict": {"first_pass": final_strict and not retry, "final": final_strict},
        "retry": retry,
        "repair": repair,
        "fallback": fallback,
        "recovery": recovery,
        "authority": {
            "expected_hash": expected_hash,
            "actual_hash": actual_hash,
            "matches_expected": bool(expected_hash) and actual_hash == expected_hash,
        },
        "timing_ms": {
            "end_to_end": max(0, end_to_end_ms),
            "full_response": full_response_ms,
            "ttft": next((value for value in ttft_values if value is not None), None),
        },
    }


def _current_motif(session: GameSession) -> str:
    state = session.story_state if isinstance(session.story_state, dict) else {}
    motifs = state.get("recent_motifs")
    return str(motifs[-1] or "") if isinstance(motifs, list) and motifs else ""


def canonical_action_for_slot(slot: str) -> str:
    """Return the fixed rule action used by a registered evaluation slot."""
    if slot not in {"A", "B", "C", "D"}:
        raise ValueError(f"evaluation slot is not registered: {slot}")
    # GameEngine resolves the slot against the current four displayed choices.
    # Keeping the slot intact avoids a free-text parser defaulting every route to B.
    return slot


class _RuleReplayEngine(GameEngine):
    """GameEngine that keeps normal rules but never dispatches a model request."""

    def run_agent(
        self,
        agent_name: str,
        user_input: str,
        session: GameSession,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if agent_name == "narrator":
            return {
                "narrative": "规则回放已结算本回合因果。",
                "choices": [
                    "稳步整理眼前线索",
                    "寻访可用机缘",
                    "踏入未知险地",
                    "借势尝试新路",
                ],
                "state_delta": {},
                "llm_error": "",
            }
        return {"approved": True, "llm_error": ""}


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
