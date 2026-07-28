"""Turn use cases delegated by :mod:`web.backend.service`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agens_novel.engine.choices import choice_with_semantic
from agens_novel.session.game_session import GameSession

from .service_session_support import is_guest_user_id

if TYPE_CHECKING:
    from .service import WebGameService, WebRunner


_CHOICE_SLOTS = ("A", "B", "C", "D")
_PENDING_MODEL_ACTIONS = {"retry_model", "use_local_story", "end_model_failure"}


def choose(
    service: WebGameService,
    session_id: str,
    payload: dict[str, Any],
    user_id: str | None = None,
) -> dict[str, Any]:
    with service._session_lock(session_id):
        runner = service._runner(session_id, user_id=user_id)
        action = choice_text(service, runner, payload)
        return advance_turn(service, runner, action, payload)


def act(
    service: WebGameService,
    session_id: str,
    payload: dict[str, Any],
    user_id: str | None = None,
) -> dict[str, Any]:
    with service._session_lock(session_id):
        runner = service._runner(session_id, user_id=user_id)
        return advance_turn(service, runner, str(payload.get("action") or ""), payload)


def advance_turn(
    service: WebGameService,
    runner: WebRunner,
    action: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    request_id, expected_version = service._mutation_context(runner, payload)
    duplicate = service.db.get_session_mutation(runner.session_id, request_id)
    if duplicate is not None:
        return duplicate
    rollback = service._rollback_state(runner)
    try:
        service._model_config.apply_runner(runner)
        before = turn_start_snapshot(runner.engine.game_session)
        pending_before = runner.engine.pending_model_failure()
        if pending_before is not None:
            if action not in _PENDING_MODEL_ACTIONS:
                raise ValueError("请先处理未完成的模型请求。")
            runner.engine.resolve_pending_model_failure(action)
        else:
            runner.engine.handle_action(action)
        pending = runner.engine.pending_model_failure()
        if pending is not None and pending_before is None:
            runner.engine.replace_pending_model_failure(
                pending.with_base_version(expected_version)
            )
        turn = settled_turn_payload(service, runner, before, action)
        return service._commit_runner(
            runner,
            expected_version=expected_version,
            request_id=request_id,
            operation="turn",
            response=runner.response(),
            turn=turn,
            terminal=service._terminal_bundle(runner),
        )
    except Exception:
        service._restore_rollback(runner, rollback)
        raise


def settled_turn_payload(
    service: WebGameService,
    runner: WebRunner,
    before: dict[str, Any],
    choice_taken: str,
) -> dict[str, Any] | None:
    """Build the latest settled turn for the atomic persistence unit."""
    if is_guest_user_id(runner.user_id):
        return None
    session = runner.engine.game_session
    if session.turn_count <= int(before.get("turn_no") or 0):
        return None
    if not session.turn_history:
        return None
    turn = session.turn_history[-1]
    if int(turn.get("turn") or 0) != session.turn_count:
        return None

    delta = turn.get("delta") if isinstance(turn.get("delta"), dict) else {}
    meta = delta.get("meta") if isinstance(delta, dict) else {}
    if not isinstance(meta, dict):
        meta = {}
    elapsed_years = int(
        meta.get("elapsed_years") or max(0, session.age - int(before.get("age") or session.age))
    )
    summary = str(
        meta.get("calendar_summary")
        or meta.get("turn_summary")
        or calendar_summary(before, session, elapsed_years)
    )
    event_kind = str(meta.get("choice_category") or turn.get("event_kind") or "event")
    return {
        "turn_no": session.turn_count,
        "start_age": int(before.get("age") or session.age),
        "elapsed_years": elapsed_years,
        "end_age": int(session.age),
        "lifespan": int(session.lifespan),
        "remaining_lifespan": session.remaining_lifespan,
        "choice_taken": choice_taken,
        "choices": list(turn.get("choices") or session.last_choices or []),
        "state_delta": delta,
        "state_after": session.as_game_state(),
        "calendar_summary": summary,
        "narrative": str(turn.get("narrative") or ""),
        "event_kind": event_kind,
        "end_reason": session.error if session.game_over else None,
    }


def choice_text(
    service: WebGameService,
    runner: WebRunner,
    payload: dict[str, Any],
) -> str:
    choices = list(runner.engine.game_session.last_choices or [])
    def choice_for_index(index: int) -> str:
        if index < 0 or index >= len(choices):
            raise ValueError("选项序号无效。")
        return service._run_policy.action_for_choice(
            index,
            choice_with_semantic(index, choices[index]),
        )

    if "choice_index" in payload and payload["choice_index"] is not None:
        return choice_for_index(int(payload["choice_index"]))

    raw = str(payload.get("choice") or "").strip()
    letter_map = {slot: index for index, slot in enumerate(_CHOICE_SLOTS)}
    if raw.upper() in letter_map and letter_map[raw.upper()] < len(choices):
        return choice_for_index(letter_map[raw.upper()])
    if raw in {"1", "2", "3", "4"}:
        index = int(raw) - 1
        if index < len(choices):
            return choice_for_index(index)
    raise ValueError("请选择 A/B/C/D。")


def turn_start_snapshot(session: GameSession) -> dict[str, Any]:
    return {
        "turn_no": int(session.turn_count or 0),
        "age": int(session.age or 0),
        "lifespan": int(session.lifespan or 0),
    }


def calendar_summary(
    before: dict[str, Any],
    session: GameSession,
    elapsed_years: int,
) -> str:
    start_age = int(before.get("age") or session.age)
    if elapsed_years > 0:
        return f"本回合流逝 {elapsed_years} 年，年龄 {start_age}→{session.age}。"
    return f"本回合完成关键抉择，年龄 {session.age}。"
