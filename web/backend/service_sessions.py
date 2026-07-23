"""Session lifecycle use cases delegated by :mod:`web.backend.service`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agens_novel.engine.death_rewards import apply_legacy_bonuses

from .auth import hash_guest_token
from .service_session_support import GUEST_USER_PREFIX, is_guest_user_id

if TYPE_CHECKING:
    from .service import WebGameService


def login(service: WebGameService, username: str = "local") -> dict[str, Any]:
    return service.db.upsert_user(username)


def create_session(
    service: WebGameService,
    user_id: str,
    title: str = "新局",
    guest_token: str = "",
) -> dict[str, Any]:
    if not user_id:
        raise ValueError("创建持久会话需要登录用户。")
    session_id = service._new_session_id()
    runner = service._new_runner(session_id, user_id, guest_token=guest_token)
    service._register_runner(session_id, runner)
    runner.record("info", text="新会话已创建。")
    service._persist(runner, title=title)
    return runner.response()


def authorize_guest_session(service: WebGameService, session_id: str, guest_token: str) -> bool:
    if not guest_token:
        return False
    cached = service.runners.get(session_id)
    if cached is not None and is_guest_user_id(cached.user_id):
        return bool(cached.guest_token and cached.guest_token == guest_token)
    row = service.db.load_guest_session(session_id, hash_guest_token(guest_token))
    if row is None:
        return False
    runner = service._restore_runner(
        session_id=session_id,
        user_id=f"{GUEST_USER_PREFIX}{session_id}",
        snapshot=row["snapshot"],
        events=row.get("events", []),
        guest_token=guest_token,
        version=int(row.get("version") or 0),
    )
    service._register_runner(session_id, runner)
    return True


def delete_guest_session(service: WebGameService, guest_token: str) -> int:
    if not guest_token:
        return 0
    token_hash = hash_guest_token(guest_token)
    for session_id, runner in list(service.runners.items()):
        if is_guest_user_id(runner.user_id) and runner.guest_token == guest_token:
            service._drop_runner(session_id)
    return service.db.delete_guest_session(token_hash)


def get_session(
    service: WebGameService,
    session_id: str,
    user_id: str | None = None,
) -> dict[str, Any]:
    return service._runner(session_id, user_id=user_id).response()


def start_session(
    service: WebGameService,
    session_id: str,
    profile: dict[str, Any],
    user_id: str | None = None,
) -> dict[str, Any]:
    with service._session_lock(session_id):
        runner = service._runner(session_id, user_id=user_id)
        request_id, expected_version = service._mutation_context(runner, profile)
        duplicate = service.db.get_session_mutation(session_id, request_id)
        if duplicate is not None:
            return duplicate
        rollback = service._rollback_state(runner)
        try:
            service._model_config.apply_runner(runner)
            scenario = service._evaluation_hooks.active_scenario()
            normalized = service._normalize_profile(scenario.profile if scenario else profile)
            bonuses: list[dict[str, Any]] = []
            if user_id and not is_guest_user_id(user_id):
                bonuses = service.db.list_legacy_bonuses(user_id)
                if bonuses:
                    normalized = apply_legacy_bonuses(normalized, bonuses)
                    normalized["_allow_legacy_bonus_attributes"] = True
            runner.engine.start_from_profile(normalized)
            session = runner.engine.game_session
            if scenario is not None:
                service._evaluation_hooks.install_authority(runner.engine, scenario)
            return service._commit_runner(
                runner,
                expected_version=expected_version,
                request_id=request_id,
                operation="start",
                response=runner.response(),
                title=session.char_name or "新局",
                start_run={
                    "char_name": session.char_name,
                    "realm": session.realm,
                    "turn_count": session.turn_count,
                },
                consume_legacy_bonuses=bool(bonuses),
                terminal=service._terminal_bundle(runner),
            )
        except Exception:
            service._restore_rollback(runner, rollback)
            raise


def end_session(
    service: WebGameService,
    session_id: str,
    payload: dict[str, Any],
    user_id: str | None = None,
) -> dict[str, Any]:
    with service._session_lock(session_id):
        runner = service._runner(session_id, user_id=user_id)
        request_id, expected_version = service._mutation_context(runner, payload)
        duplicate = service.db.get_session_mutation(session_id, request_id)
        if duplicate is not None:
            return duplicate
        rollback = service._rollback_state(runner)
        try:
            session = runner.engine.game_session
            session.game_over = True
            session.finale = False
            session.error = str(payload.get("reason") or "玩家结束本局。")
            if runner.engine.on_game_over is not None:
                runner.engine.on_game_over(session.error)
            else:
                runner.record("game_over", text=session.error)
            return service._commit_runner(
                runner,
                expected_version=expected_version,
                request_id=request_id,
                operation="end",
                response=runner.response(),
                terminal=service._terminal_bundle(runner),
            )
        except Exception:
            service._restore_rollback(runner, rollback)
            raise
