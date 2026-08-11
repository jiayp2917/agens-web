"""Tests for deterministic, provider-free local authority replay."""

from __future__ import annotations

from agens_novel.engine.turn_rules import choice_intent
from agens_novel.session.game_session import GameSession
from agens_novel.verification.authority import (
    authority_state_hash,
    authority_state_hash_from_persisted_state,
    canonical_action_for_slot,
    canonical_authority_trajectory,
    canonical_replay_session,
    canonical_slots,
)
from agens_novel.verification.scenarios import canonical_v3_scenarios


def test_canonical_slots_extend_only_for_post_arc_coverage() -> None:
    scenario = canonical_v3_scenarios()[0]

    assert canonical_slots(scenario, max_turns=90) == scenario.slots
    assert canonical_slots(scenario, max_turns=95) == scenario.slots + ("A",) * 5


def test_canonical_actions_preserve_fixed_slot_semantics() -> None:
    for slot in ("A", "B", "C", "D"):
        assert choice_intent(canonical_action_for_slot(slot)).slot == slot


def test_replay_hashes_are_deterministic_and_match_persisted_state() -> None:
    scenario = canonical_v3_scenarios()[0]
    first = canonical_authority_trajectory(scenario, story_version=3, max_turns=5)
    second = canonical_authority_trajectory(scenario, story_version=3, max_turns=5)
    session = canonical_replay_session(scenario, story_version=3, target_turn=5)

    assert first == second
    assert first[-1]["authority_hash"] == authority_state_hash(session)
    assert authority_state_hash_from_persisted_state(session.as_game_state()) == authority_state_hash(
        session
    )


def test_authority_hash_includes_persisted_validation_mode() -> None:
    ordinary = GameSession(run_seed="fixed-seed")
    validation = GameSession(run_seed="fixed-seed", validation_mode="golden_route")

    assert authority_state_hash(ordinary) != authority_state_hash(validation)
