"""Persistence and integrity coverage for pending model failures."""

from __future__ import annotations

from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.pending_model_failure import PendingModelFailureV1
from agens_novel.session.game_session import GameSession


def test_pending_model_failure_round_trips_through_a_save() -> None:
    pending = PendingModelFailureV1.create(
        stage="turn",
        action="A",
        slot="A",
        frozen_result={"state_delta": {"character": {"age": 1}}},
        rule_rng_counter=7,
        error_code="incomplete_output",
    )
    session = GameSession(game_started=True, pending_model_failure=pending.to_dict())

    restored = GameSession.from_save_dict(session.to_save_dict())

    assert restored.pending_model_failure == pending.to_dict()


def test_tampered_pending_model_failure_is_discarded_on_load() -> None:
    pending = PendingModelFailureV1.create(
        stage="turn",
        action="A",
        slot="A",
        frozen_result={"state_delta": {"character": {"age": 1}}},
        rule_rng_counter=7,
        error_code="request_failed",
    )
    payload = GameSession(pending_model_failure=pending.to_dict()).to_save_dict()
    payload["pending_model_failure"]["frozen_result"]["state_delta"]["character"]["age"] = 99

    restored = GameSession.from_save_dict(payload)

    assert restored.pending_model_failure == {}


def test_pending_failure_emits_retrying_and_resolved_audit_states() -> None:
    engine = GameEngine()
    states: list[dict[str, object]] = []
    engine.on_model_failure_state = lambda failure: states.append(dict(failure))
    pending = engine.create_pending_model_failure(
        stage="turn",
        action="A",
        slot="A",
        frozen_result={"state_delta": {}, "turn_summary": "冻结回合"},
        error_code="request_failed",
    )

    engine.replace_pending_model_failure(pending.with_status("retrying", request_no=2))
    engine.clear_pending_model_failure()

    assert [item["status"] for item in states] == ["retrying", "resolved"]
    assert engine.pending_model_failure() is None
