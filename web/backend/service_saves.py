"""Save and load use cases delegated by :mod:`web.backend.service`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .service_session_support import is_guest_user_id

if TYPE_CHECKING:
    from .service import WebGameService, WebRunner


def save(
    service: WebGameService,
    session_id: str,
    payload: dict[str, Any],
    user_id: str | None = None,
) -> dict[str, Any]:
    with service._session_lock(session_id):
        runner = require_non_guest_runner(service, session_id, user_id, action="存档")
        request_id, expected_version = service._mutation_context(runner, payload)
        duplicate = service.db.get_session_mutation(session_id, request_id)
        if duplicate is not None:
            return duplicate
        slot = {
            "name": str(payload.get("name") or "slot_1"),
            "snapshot": runner.snapshot(),
            "events": list(runner.events),
        }
        rollback = service._rollback_state(runner)
        try:
            return service._commit_runner(
                runner,
                expected_version=expected_version,
                request_id=request_id,
                operation="save",
                response={"save": {}, "session": runner.response()},
                save_slot=slot,
            )
        except Exception:
            service._restore_rollback(runner, rollback)
            raise


def load(
    service: WebGameService,
    session_id: str,
    payload: dict[str, Any],
    user_id: str | None = None,
) -> dict[str, Any]:
    with service._session_lock(session_id):
        runner = require_non_guest_runner(service, session_id, user_id, action="读档")
        request_id, expected_version = service._mutation_context(runner, payload)
        duplicate = service.db.get_session_mutation(session_id, request_id)
        if duplicate is not None:
            return duplicate
        save_name = str(payload.get("name") or "slot_1")
        saved = service.db.load_save(runner.user_id, save_name)
        if saved is None:
            raise KeyError(f"存档不存在: {save_name}")
        restored = service._restore_runner(
            session_id=session_id,
            user_id=runner.user_id,
            snapshot=saved["snapshot"],
            events=saved.get("events", []),
            version=runner.version,
        )
        response = service._commit_runner(
            restored,
            expected_version=expected_version,
            request_id=request_id,
            operation="load",
            response=restored.response(),
            title=restored.engine.game_session.char_name or saved["name"],
            rewind_run={
                "turn_count": restored.engine.game_session.turn_count,
                "char_name": restored.engine.game_session.char_name,
                "realm": restored.engine.game_session.realm,
            },
        )
        service._register_runner(session_id, restored)
        return response


def list_saves(service: WebGameService, user_id: str = "") -> list[dict[str, Any]]:
    if not user_id:
        raise PermissionError("读取存档需要登录。")
    return service.db.list_saves(user_id)


def require_non_guest_runner(
    service: WebGameService,
    session_id: str,
    user_id: str | None,
    *,
    action: str,
) -> WebRunner:
    """Resolve a runner and reject guest callers for the given action."""
    runner = service._runner(session_id, user_id=user_id)
    if is_guest_user_id(runner.user_id):
        raise PermissionError(f"访客游玩不提供云端{action}，请先注册或登录。")
    return runner
