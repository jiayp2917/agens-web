"""Rule-only replay and authority-state checks for local verification."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from ..engine.choices import fallback_choices
from ..engine.game_engine import GameEngine
from ..engine.story_catalog import opening_story_binding
from ..session.game_session import GameSession
from .scenarios import CanonicalScenarioV1


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
    """Build a frozen state from catalog data and rule replay, never a hand stub."""
    engine = _RuleReplayEngine()
    with _opening_mode(False):
        engine.start_from_profile(scenario.profile)
    install_canonical_binding(engine, scenario, story_version)
    for slot in canonical_slots(scenario, max_turns=max(0, target_turn)):
        if engine.game_session.game_over:
            break
        engine.handle_action(canonical_action_for_slot(slot))
    return GameSession.from_save_dict(engine.game_session.to_save_dict())


def authority_state_hash(session: GameSession) -> str:
    """Hash only state that deterministic turn rules own across providers."""
    state_hash = authority_state_hash_from_persisted_state(session.as_game_state())
    if state_hash is None:
        raise RuntimeError("authoritative session state is incomplete")
    return state_hash


def authority_state_hash_from_persisted_state(state: dict[str, Any]) -> str | None:
    """Hash persisted game-turn state without tool-owned product fields."""
    character = state.get("character")
    world = state.get("world")
    rule_state = state.get("rule_state")
    local_story = state.get("local_story")
    if not isinstance(character, dict):
        return None
    if not isinstance(world, dict):
        return None
    if not isinstance(rule_state, dict):
        return None
    if not isinstance(local_story, dict):
        return None
    story_state = world.get("story_state")
    if not isinstance(story_state, dict):
        return None
    if "run_seed" not in rule_state or "rng_counter" not in rule_state:
        return None
    payload = {
        "turn_count": state.get("turn_count"),
        "realm_turn_count": state.get("realm_turn_count"),
        "game_started": state.get("game_started"),
        "game_over": state.get("game_over"),
        "finale": bool(state.get("finale")),
        "error": str(state.get("error") or ""),
        "run_seed": str(rule_state["run_seed"] or ""),
        "rule_rng_counter": rule_state["rng_counter"],
        "validation_mode": str(rule_state.get("validation_mode") or ""),
        "local_story_active": bool(local_story.get("active")),
        "character": {
            "realm": character.get("realm"),
            "realm_stage": character.get("realm_stage"),
            "age": character.get("age"),
            "attributes": character.get("attributes"),
            "breakthrough_flags": character.get("breakthrough_flags"),
            "titles": character.get("titles"),
            "relationships": character.get("relationships"),
            "status_effects": character.get("status_effects"),
            "lifespan": character.get("lifespan"),
        },
        "story": {
            "key": world.get("story_key"),
            "version": world.get("story_version"),
            "state": story_state,
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


def canonical_action_for_slot(slot: str) -> str:
    """Return the fixed rule action used by a registered verification slot."""
    if slot not in {"A", "B", "C", "D"}:
        raise ValueError(f"verification slot is not registered: {slot}")
    return slot


def install_canonical_binding(
    engine: GameEngine,
    scenario: CanonicalScenarioV1,
    story_version: int,
) -> None:
    """Bind the deterministic replay session to its catalog-owned story data."""
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


class _RuleReplayEngine(GameEngine):
    """GameEngine that keeps normal rules but never dispatches a model request."""

    def __init__(self) -> None:
        super().__init__()
        self.model_config = {"api_key_set": True, "response_mode": "json_object"}

    def run_agent(
        self,
        agent_name: str,
        user_input: str,
        session: GameSession,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if agent_name == "world_builder":
            profile = session.world_profile if isinstance(session.world_profile, dict) else {}
            chronicle_value = profile.get("chronicle_0_16")
            chronicle = (
                [str(item).strip() for item in chronicle_value if str(item).strip()]
                if isinstance(chronicle_value, list)
                else []
            )
            initial = str(
                profile.get("initial_situation_16")
                or profile.get("initial_situation")
                or session.current_scene
            ).strip()
            opening = "\n".join([*chronicle, initial]).strip()
            return {
                "generated_data": {
                    "opening_narrative": opening,
                    "chronicle_0_16": chronicle,
                    "initial_situation_16": initial,
                    "choices": fallback_choices(session),
                },
                "llm_error": "",
                "response_mode": "json_object",
                "provider_json_envelope_ok": True,
            }
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
