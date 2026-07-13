"""Service layer that adapts GameEngine to web sessions."""

from __future__ import annotations

import logging
import os
import random
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy.exc

from agens_novel.engine.choices import choice_with_semantic, clean_choice_text, clean_visible_text
from agens_novel.engine.death_rewards import (
    apply_legacy_bonuses,
    bonuses_to_legacy,
)
from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.model_fallback_policy import (
    MODEL_FAILURE_CONTINUE,
    public_model_failure_notice,
)
from agens_novel.engine.model_fallback_policy import SECRET_MARKERS as _SECRET_MARKERS
from agens_novel.engine.render import format_status_bar
from agens_novel.engine.start_flow import normalize_profile_attributes
from agens_novel.engine.story_catalog import ensure_story_binding, story_arc_for_binding
from agens_novel.game.constants import (
    ATTRIBUTE_KEYS,
    DIFFICULTY_OPTIONS,
    FAMILY_BACKGROUNDS,
    SPIRIT_ROOTS,
    TALENT_OPTIONS,
)
from agens_novel.session.game_session import GameSession

from .auth import hash_guest_token
from .database import WebDatabaseProtocol
from .database_postgres import PostgresWebDatabase
from .service_death_rewards import DeathRewardsService
from .service_errors import SessionVersionConflict
from .service_model_config import ModelConfigService
from .service_summaries import build_death_summary

_PROFILE_SEMANTIC_FIELDS = (
    "name",
    "rarity",
    "description",
    "attribute_mods",
    "tags",
    "initial_resources",
    "initial_risks",
    "story_tags",
    "element",
    "grade",
    "cultivation_bonus",
    "breakthrough_bonus",
    "cultivation_tendency",
    "event_tags",
    "risk_multiplier",
    "reward_multiplier",
    "lifespan_modifier",
    "luck_modifier",
)

log = logging.getLogger(__name__)

PUBLIC_MODEL_FALLBACK_TEXT = "模型暂不可用，已切换本地故事，请直接选择下方选项继续。"
_MODEL_FAILURE_PREFIXES = (
    "世界生成失败:",
    "叙述失败:",
    "天道审判失败:",
    "突破叙事失败:",
    "突破审判失败:",
)
GUEST_USER_PREFIX = "guest:"


@dataclass
class WebRunner:
    """One browser game session with captured engine callbacks."""

    session_id: str
    user_id: str
    engine: GameEngine = field(default_factory=GameEngine)
    events: list[dict[str, Any]] = field(default_factory=list)
    guest_token: str = ""
    version: int = 0
    db: Any = field(default=None, repr=False, compare=False)
    fallback_prompt_text: str = PUBLIC_MODEL_FALLBACK_TEXT
    fallback_prompt_active: bool = False

    def __post_init__(self) -> None:
        self.engine.on_narrative = lambda text, turn: self.record("narrative", text=text, turn=turn)
        self.engine.on_status_bar = lambda text: self.record("status", text=text)
        self.engine.on_error = lambda text: self.record("error", text=text)
        self.engine.on_info = lambda text: self.record("info", text=text)
        self.engine.on_game_over = lambda text: self._on_game_over(text)
        self.engine.on_finale = lambda text: self.record("finale", text=text)
        self.engine.on_loading = lambda text: self.record("loading", text=text)
        if os.environ.get("AGENS_WEB_STREAMING") == "1":
            self.engine.on_stream_chunk = lambda text: None
        self.engine.on_model_result = self._record_model_result
        self.engine.on_character_created = lambda session: self.record(
            "character_created", state=session.as_game_state()
        )
        self.engine.on_model_failure_choice = self._choose_model_failure

    def _on_game_over(self, text: str) -> None:
        """Record game-over and evaluate rewards (P4).

        Evaluates achievements/rewards for guest and registered sessions.
        Registered users also get the results persisted atomically at terminal commit.
        """
        self.record("game_over", text=text)
        summary = build_death_summary(self.engine.game_session)
        if summary is None:
            return
        self.record(
            "death_summary",
            death_cause=summary["death_cause"],
            achievements=summary["achievements"],
            rewards=summary["rewards"],
            headline=summary["headline"],
            final_realm=summary["final_realm"],
        )

    def _choose_model_failure(self, source: str, reason: str) -> str:
        self.fallback_prompt_text = public_model_failure_notice(reason)
        self.fallback_prompt_active = True
        self.record(
            "model_failure",
            text=self.fallback_prompt_text,
            source=source,
        )
        return MODEL_FAILURE_CONTINUE

    def _record_model_result(
        self,
        agent: str,
        source: str,
        status: str,
        model_set: bool,
        base_url_set: bool,
        key_set: bool,
        config_source: str,
        diagnostics: dict[str, Any],
    ) -> None:
        self.record(
            "model_result",
            agent=agent,
            source=source,
            status=status,
            model_set=model_set,
            base_url_set=base_url_set,
            key_set=key_set,
            config_source=config_source,
            diagnostics=diagnostics,
        )
        if str(status).lower() == "ok" and agent in {"narrator", "world_builder"}:
            self.fallback_prompt_active = False

    @classmethod
    def from_snapshot(
        cls,
        session_id: str,
        user_id: str,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]] | None = None,
        db: Any = None,
        guest_token: str = "",
        version: int = 0,
    ) -> WebRunner:
        runner = cls(
            session_id=session_id,
            user_id=user_id,
            guest_token=guest_token,
            version=version,
            db=db,
        )
        runner.engine.game_session = GameSession.from_save_dict(snapshot)
        session = runner.engine.game_session
        if session.game_started:
            if not session.story_key:
                ensure_story_binding(session)
            elif story_arc_for_binding(session.story_key, session.story_version) is None:
                raise ValueError(
                    f"存档引用的剧情版本不可用: {session.story_key}@{session.story_version}"
                )
        runner.events = list(events or [])
        (
            runner.fallback_prompt_active,
            runner.fallback_prompt_text,
        ) = _fallback_prompt_state_from_events(runner.events)
        return runner

    def record(self, event_type: str, **payload: Any) -> None:
        payload = _sanitize_event_payload(event_type, payload)
        session = self.engine.game_session
        payload.setdefault("age", int(session.age or 0))
        self.events.append({"type": event_type, "at": time.time(), **payload})
        self.events = self.events[-120:]

    def response(self) -> dict[str, Any]:
        session = self.engine.game_session
        state = session.as_game_state()
        return {
            "session_id": self.session_id,
            "version": self.version,
            "user_id": self.user_id,
            "guest": is_guest_user_id(self.user_id),
            "turn_count": session.turn_count,
            "game_started": session.game_started,
            "game_over": session.game_over,
            "finale": session.finale,
            "error": session.error,
            "choices": list(session.last_choices),
            "local_story": {
                "active": session.local_story_active,
                "story_id": session.local_story_id,
                "node_id": session.local_story_node_id,
            },
            "fallback_prompt": {
                "active": not session.game_over
                and (session.local_story_active or self.fallback_prompt_active),
                "text": self.fallback_prompt_text or PUBLIC_MODEL_FALLBACK_TEXT,
            },
            "character": state["character"],
            "world": state["world"],
            "events": self.events[-80:],
            "panels": {
                "status_bar": format_status_bar(session),
            },
        }

    def snapshot(self) -> dict[str, Any]:
        return self.engine.game_session.to_save_dict()


def _sanitize_event_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(payload)
    if event_type == "model_result":
        return _sanitize_model_result_payload(sanitized)
    if event_type == "model_failure":
        sanitized.pop("reason", None)
        text = str(sanitized.get("text") or PUBLIC_MODEL_FALLBACK_TEXT)
        sanitized["text"] = text if _is_public_model_notice(text) else PUBLIC_MODEL_FALLBACK_TEXT
        return sanitized
    if event_type == "info":
        text = str(sanitized.get("text") or "")
        if _looks_internal_model_error(text):
            sanitized["text"] = PUBLIC_MODEL_FALLBACK_TEXT
        else:
            sanitized["text"] = _public_event_text(text)
        return sanitized
    if event_type == "error":
        text = str(sanitized.get("text") or "")
        if _looks_internal_model_error(text):
            sanitized["text"] = PUBLIC_MODEL_FALLBACK_TEXT
        else:
            sanitized["text"] = _public_event_text(text)
        return sanitized
    if event_type in {"narrative", "game_over", "finale"}:
        sanitized["text"] = _public_event_text(str(sanitized.get("text") or ""))
    if "choices" in sanitized and isinstance(sanitized.get("choices"), list):
        sanitized["choices"] = [clean_choice_text(str(choice)) for choice in sanitized["choices"]]
    return sanitized


def _fallback_prompt_state_from_events(events: list[dict[str, Any]]) -> tuple[bool, str]:
    """Rebuild current fallback prompt state from persisted sanitized events."""
    active = False
    text = PUBLIC_MODEL_FALLBACK_TEXT
    for event in events:
        event_type = event.get("type")
        if event_type == "model_failure":
            active = True
            candidate = str(event.get("text") or "")
            text = candidate if _is_public_model_notice(candidate) else PUBLIC_MODEL_FALLBACK_TEXT
        elif (
            event_type == "model_result"
            and str(event.get("status") or "").lower() == "ok"
            and event.get("agent") in {"narrator", "world_builder"}
        ):
            active = False
    return active, text


def _sanitize_model_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    diagnostics_value = payload.get("diagnostics")
    diagnostics: dict[str, Any] = diagnostics_value if isinstance(diagnostics_value, dict) else {}
    safe_diagnostics = {
        str(key): _safe_int_or_bool(value)
        for key, value in diagnostics.items()
        if isinstance(value, (bool, int, float)) or value is None
    }
    return {
        "agent": str(payload.get("agent") or ""),
        "source": str(payload.get("source") or ""),
        "status": str(payload.get("status") or ""),
        "model_set": bool(payload.get("model_set")),
        "base_url_set": bool(payload.get("base_url_set")),
        "key_set": bool(payload.get("key_set")),
        "config_source": str(payload.get("config_source") or ""),
        "diagnostics": safe_diagnostics,
    }


def _safe_int_or_bool(value: Any) -> int | bool:
    if isinstance(value, bool):
        return value
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _looks_internal_model_error(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in _SECRET_MARKERS):
        return True
    if any(text.startswith(prefix) for prefix in _MODEL_FAILURE_PREFIXES):
        return True
    return bool(re.search(r"https?://\S+", text))


def _is_public_model_notice(text: str) -> bool:
    if _looks_internal_model_error(text):
        return False
    return text in {
        PUBLIC_MODEL_FALLBACK_TEXT,
        public_model_failure_notice("HTTP 404"),
        public_model_failure_notice("HTTP 401"),
        public_model_failure_notice("HTTP 403"),
        public_model_failure_notice("timeout"),
        public_model_failure_notice("AGNES_API_KEY unavailable"),
    }


def _public_event_text(text: str) -> str:
    cleaned = clean_visible_text(text, allow_structured=False)
    internal_notices = (
        "模型状态变更未采用",
        "本回合已按当前局面补齐下一步选择",
        "此事未入正史",
        "按本局因果结算",
        "详见日志",
        "叙述失败",
        "世界生成失败",
        "天道审判失败",
        "突破叙事失败",
        "突破审判失败",
        "模型叙事",
        "模型输出",
        "本地故事",
        "天道紊乱",
        "narrative/state mismatch",
        "state_delta",
        "状态更新格式不完整",
    )
    if any(marker in cleaned for marker in internal_notices):
        return ""
    return cleaned


class WebGameService:
    """Application service for users, sessions, saves, and settings."""

    def __init__(self, db: WebDatabaseProtocol | None = None) -> None:
        self.db = db or PostgresWebDatabase()
        self.runners: dict[str, WebRunner] = {}
        self._runner_last_used: dict[str, float] = {}
        self._model_config = ModelConfigService(self.db)
        self._death_rewards = DeathRewardsService(self.db)
        self._session_locks: dict[str, threading.RLock] = {}
        self._session_locks_guard = threading.Lock()

    def login(self, username: str = "local") -> dict[str, Any]:
        return self.db.upsert_user(username)

    def create_session(
        self,
        user_id: str,
        title: str = "新局",
        guest_token: str = "",
    ) -> dict[str, Any]:
        if not user_id:
            raise ValueError("创建持久会话需要登录用户。")
        session_id = str(uuid.uuid4())
        runner = WebRunner(
            session_id=session_id,
            user_id=user_id,
            guest_token=guest_token,
            db=self.db,
        )
        self._register_runner(session_id, runner)
        runner.record("info", text="新会话已创建。")
        self._persist(runner, title=title)
        return runner.response()

    def authorize_guest_session(self, session_id: str, guest_token: str) -> bool:
        if not guest_token:
            return False
        cached = self.runners.get(session_id)
        if cached is not None and is_guest_user_id(cached.user_id):
            return bool(cached.guest_token and cached.guest_token == guest_token)
        row = self.db.load_guest_session(session_id, hash_guest_token(guest_token))
        if row is None:
            return False
        runner = WebRunner.from_snapshot(
            session_id=session_id,
            user_id=f"{GUEST_USER_PREFIX}{session_id}",
            snapshot=row["snapshot"],
            events=row.get("events", []),
            db=self.db,
            guest_token=guest_token,
            version=int(row.get("version") or 0),
        )
        self._register_runner(session_id, runner)
        return True

    def delete_guest_session(self, guest_token: str) -> int:
        if not guest_token:
            return 0
        token_hash = hash_guest_token(guest_token)
        for session_id, runner in list(self.runners.items()):
            if is_guest_user_id(runner.user_id) and runner.guest_token == guest_token:
                self._drop_runner(session_id)
        return self.db.delete_guest_session(token_hash)

    def get_session(self, session_id: str, user_id: str | None = None) -> dict[str, Any]:
        return self._runner(session_id, user_id=user_id).response()

    def start_session(
        self, session_id: str, profile: dict[str, Any], user_id: str | None = None
    ) -> dict[str, Any]:
        with self._session_lock(session_id):
            runner = self._runner(session_id, user_id=user_id)
            request_id, expected_version = self._mutation_context(runner, profile)
            duplicate = self.db.get_session_mutation(session_id, request_id)
            if duplicate is not None:
                return duplicate
            rollback = self._rollback_state(runner)
            try:
                self._model_config.apply_runner(runner)
                normalized = self._normalize_profile(profile)
                bonuses: list[dict[str, Any]] = []
                if user_id and not is_guest_user_id(user_id):
                    bonuses = self.db.list_legacy_bonuses(user_id)
                    if bonuses:
                        normalized = apply_legacy_bonuses(normalized, bonuses)
                        normalized["_allow_legacy_bonus_attributes"] = True
                runner.engine.start_from_profile(normalized)
                session = runner.engine.game_session
                response = self._commit_runner(
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
                    terminal=self._terminal_bundle(runner),
                )
                return response
            except Exception:
                self._restore_rollback(runner, rollback)
                raise

    def choose(
        self, session_id: str, payload: dict[str, Any], user_id: str | None = None
    ) -> dict[str, Any]:
        with self._session_lock(session_id):
            runner = self._runner(session_id, user_id=user_id)
            action = self._choice_text(runner, payload)
            return self._advance_turn(runner, action, payload)

    def act(
        self,
        session_id: str,
        payload: dict[str, Any],
        user_id: str | None = None,
    ) -> dict[str, Any]:
        with self._session_lock(session_id):
            runner = self._runner(session_id, user_id=user_id)
            return self._advance_turn(runner, str(payload.get("action") or ""), payload)

    def _advance_turn(
        self,
        runner: WebRunner,
        action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        request_id, expected_version = self._mutation_context(runner, payload)
        duplicate = self.db.get_session_mutation(runner.session_id, request_id)
        if duplicate is not None:
            return duplicate
        rollback = self._rollback_state(runner)
        try:
            self._model_config.apply_runner(runner)
            before = _turn_start_snapshot(runner.engine.game_session)
            runner.engine.handle_action(action)
            turn = self._settled_turn_payload(runner, before, action)
            return self._commit_runner(
                runner,
                expected_version=expected_version,
                request_id=request_id,
                operation="turn",
                response=runner.response(),
                turn=turn,
                terminal=self._terminal_bundle(runner),
            )
        except Exception:
            self._restore_rollback(runner, rollback)
            raise

    def save(
        self, session_id: str, payload: dict[str, Any], user_id: str | None = None
    ) -> dict[str, Any]:
        with self._session_lock(session_id):
            runner = self._require_non_guest_runner(session_id, user_id, action="存档")
            request_id, expected_version = self._mutation_context(runner, payload)
            duplicate = self.db.get_session_mutation(session_id, request_id)
            if duplicate is not None:
                return duplicate
            save_name = str(payload.get("name") or "slot_1")
            slot = {
                "name": save_name,
                "snapshot": runner.snapshot(),
                "events": list(runner.events),
            }
            rollback = self._rollback_state(runner)
            try:
                return self._commit_runner(
                    runner,
                    expected_version=expected_version,
                    request_id=request_id,
                    operation="save",
                    response={"save": {}, "session": runner.response()},
                    save_slot=slot,
                )
            except Exception:
                self._restore_rollback(runner, rollback)
                raise

    def load(
        self, session_id: str, payload: dict[str, Any], user_id: str | None = None
    ) -> dict[str, Any]:
        with self._session_lock(session_id):
            runner = self._require_non_guest_runner(session_id, user_id, action="读档")
            request_id, expected_version = self._mutation_context(runner, payload)
            duplicate = self.db.get_session_mutation(session_id, request_id)
            if duplicate is not None:
                return duplicate
            save_name = str(payload.get("name") or "slot_1")
            saved = self.db.load_save(runner.user_id, save_name)
            if saved is None:
                raise KeyError(f"存档不存在: {save_name}")
            restored = WebRunner.from_snapshot(
                session_id=session_id,
                user_id=runner.user_id,
                snapshot=saved["snapshot"],
                events=saved.get("events", []),
                db=self.db,
                version=runner.version,
            )
            response = self._commit_runner(
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
            self._register_runner(session_id, restored)
            return response

    def end_session(
        self, session_id: str, payload: dict[str, Any], user_id: str | None = None
    ) -> dict[str, Any]:
        with self._session_lock(session_id):
            runner = self._runner(session_id, user_id=user_id)
            request_id, expected_version = self._mutation_context(runner, payload)
            duplicate = self.db.get_session_mutation(session_id, request_id)
            if duplicate is not None:
                return duplicate
            rollback = self._rollback_state(runner)
            try:
                session = runner.engine.game_session
                session.game_over = True
                session.finale = False
                session.error = str(payload.get("reason") or "玩家结束本局。")
                if runner.engine.on_game_over is not None:
                    runner.engine.on_game_over(session.error)
                else:
                    runner.record("game_over", text=session.error)
                return self._commit_runner(
                    runner,
                    expected_version=expected_version,
                    request_id=request_id,
                    operation="end",
                    response=runner.response(),
                    terminal=self._terminal_bundle(runner),
                )
            except Exception:
                self._restore_rollback(runner, rollback)
                raise

    def list_saves(self, user_id: str = "") -> list[dict[str, Any]]:
        if not user_id:
            raise PermissionError("读取存档需要登录。")
        return self.db.list_saves(user_id)

    # ── Death rewards (P4) ──────────────────────────────────────────────

    def death_summary(self, session_id: str, user_id: str | None = None) -> dict[str, Any]:
        """Return the most recent death summary for a session.

        Prefer a live rebuild so the UI reflects current achievement rules even
        when older rows were persisted before a rule fix. Fall back to DB rows
        only when the runner/session snapshot is no longer available.
        """
        if is_guest_user_id(user_id) or user_id is None:
            return self._live_death_summary(session_id, user_id=user_id, is_guest=True)

        live = self._try_live_death_summary(session_id, user_id=user_id, is_guest=False)
        if live is not None:
            return live

        return self._death_rewards.stored_summary(session_id, user_id)

    def _live_death_summary(
        self,
        session_id: str,
        *,
        user_id: str | None,
        is_guest: bool,
    ) -> dict[str, Any]:
        runner = self._runner(session_id, user_id=user_id)
        summary = build_death_summary(runner.engine.game_session)
        return {
            "session_id": session_id,
            "is_guest": is_guest,
            "summary": summary or {},
        }

    def _try_live_death_summary(
        self,
        session_id: str,
        *,
        user_id: str,
        is_guest: bool,
    ) -> dict[str, Any] | None:
        live = self._live_death_summary(session_id, user_id=user_id, is_guest=is_guest)
        return live if live["summary"] else None

    def legacy_bonuses(self, user_id: str) -> list[dict[str, Any]]:
        return self._death_rewards.legacy_bonuses(user_id)

    def model_settings(self, user_id: str) -> dict[str, Any]:
        svc = self._model_config
        return svc.public_settings(svc.effective(user_id))

    def update_model_settings(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.db.get_user_model_config(user_id) or {}
        config = self._model_config.build_stored(payload, existing=current)
        self.db.save_user_model_config(user_id, config)
        return self.model_settings(user_id)

    def clear_model_settings(self, user_id: str) -> dict[str, Any]:
        self.db.delete_user_model_config(user_id)
        return self.model_settings(user_id)

    def admin_model_settings(self) -> dict[str, Any]:
        svc = self._model_config
        return svc.public_settings(svc.system())

    def update_admin_model_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.db.get_model_config() or {}
        config = self._model_config.build_stored(payload, existing=current)
        self.db.save_model_config(config)
        return self.admin_model_settings()

    def _session_lock(self, session_id: str) -> threading.RLock:
        with self._session_locks_guard:
            return self._session_locks.setdefault(session_id, threading.RLock())

    def _mutation_context(
        self,
        runner: WebRunner,
        payload: dict[str, Any],
    ) -> tuple[str, int]:
        request_id = str(payload.get("request_id") or uuid.uuid4())
        if self.db.get_session_mutation(runner.session_id, request_id) is not None:
            return request_id, runner.version
        expected_raw = payload.get("expected_version")
        expected = runner.version if expected_raw is None else int(expected_raw)
        if expected != runner.version:
            raise SessionVersionConflict("局面已更新，请刷新后重试。")
        return request_id, expected

    def _commit_runner(
        self,
        runner: WebRunner,
        *,
        expected_version: int,
        request_id: str,
        operation: str,
        response: dict[str, Any],
        title: str | None = None,
        turn: dict[str, Any] | None = None,
        start_run: dict[str, Any] | None = None,
        consume_legacy_bonuses: bool = False,
        terminal: dict[str, Any] | None = None,
        save_slot: dict[str, Any] | None = None,
        rewind_run: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        is_guest = is_guest_user_id(runner.user_id)
        result = self.db.commit_session_mutation(
            session_id=runner.session_id,
            user_id=None if is_guest else runner.user_id,
            title=title or runner.engine.game_session.char_name or "新局",
            snapshot=runner.snapshot(),
            events=runner.events,
            expected_version=expected_version,
            request_id=request_id,
            operation=operation,
            response=response,
            guest_token_hash=hash_guest_token(runner.guest_token) if is_guest else "",
            expires_at=_guest_expiry() if is_guest else None,
            turn=turn,
            start_run=start_run,
            consume_legacy_bonuses=consume_legacy_bonuses,
            terminal=terminal,
            save_slot=save_slot,
            rewind_run=rewind_run,
        )
        session_value = result.get("session")
        session_response: dict[str, Any] = (
            session_value if isinstance(session_value, dict) else result
        )
        runner.version = int(session_response.get("version") or expected_version + 1)
        return result

    @staticmethod
    def _rollback_state(runner: WebRunner) -> dict[str, Any]:
        return {
            "snapshot": runner.snapshot(),
            "events": list(runner.events),
            "version": runner.version,
            "fallback_active": runner.fallback_prompt_active,
            "fallback_text": runner.fallback_prompt_text,
        }

    def _restore_rollback(self, runner: WebRunner, rollback: dict[str, Any]) -> None:
        restored = WebRunner.from_snapshot(
            session_id=runner.session_id,
            user_id=runner.user_id,
            snapshot=rollback["snapshot"],
            events=rollback["events"],
            db=self.db,
            guest_token=runner.guest_token,
            version=int(rollback["version"]),
        )
        restored.fallback_prompt_active = bool(rollback["fallback_active"])
        restored.fallback_prompt_text = str(rollback["fallback_text"])
        self._register_runner(runner.session_id, restored)

    @staticmethod
    def _terminal_bundle(runner: WebRunner) -> dict[str, Any] | None:
        session = runner.engine.game_session
        if not session.game_over:
            return None
        summary = build_death_summary(session) or {}
        return {
            "char_name": session.char_name,
            "realm": session.realm,
            "death_cause": session.error,
            "ascended": bool(session.finale),
            "turn_count": session.turn_count,
            "summary": summary,
            "legacy_bonuses": bonuses_to_legacy(summary.get("rewards", []) or []),
        }

    def _require_non_guest_runner(
        self,
        session_id: str,
        user_id: str | None,
        *,
        action: str,
    ) -> WebRunner:
        """Resolve a runner and reject guest callers for the given action."""
        runner = self._runner(session_id, user_id=user_id)
        if is_guest_user_id(runner.user_id):
            raise PermissionError(f"访客游玩不提供云端{action}，请先注册或登录。")
        return runner

    def _runner(self, session_id: str, user_id: str | None = None) -> WebRunner:
        if session_id in self.runners:
            runner = self.runners[session_id]
            if user_id and runner.user_id != user_id:
                raise PermissionError("无权访问该会话。")
            if not user_id and not is_guest_user_id(runner.user_id):
                raise PermissionError("请先登录。")
            self._runner_last_used[session_id] = time.time()
            return runner
        if not user_id:
            raise KeyError(f"会话不存在: {session_id}")
        row = self.db.load_session(session_id)
        if row is None:
            raise KeyError(f"会话不存在: {session_id}")
        if user_id and row["user_id"] != user_id:
            raise PermissionError("无权访问该会话。")
        runner = WebRunner.from_snapshot(
            session_id=session_id,
            user_id=row["user_id"],
            snapshot=row["snapshot"],
            events=row.get("events", []),
            db=self.db,
            version=int(row.get("version") or 0),
        )
        self._register_runner(session_id, runner)
        return runner

    def _register_runner(self, session_id: str, runner: WebRunner) -> None:
        """Cache a runner and bound the in-memory cache (LRU + idle TTL).

        Registered and guest runners are rebuilt from PostgreSQL on next access,
        subject to ownership checks and the guest-session expiry time.
        """
        self.runners[session_id] = runner
        self._runner_last_used[session_id] = time.time()
        self._prune_runners()

    def _prune_runners(self, max_runners: int = 128, idle_ttl: float = 1800) -> None:
        now = time.time()
        for sid, last_used in list(self._runner_last_used.items()):
            if now - last_used > idle_ttl:
                self._drop_runner(sid)
        if len(self.runners) <= max_runners:
            return
        by_recency = sorted(self._runner_last_used, key=lambda sid: self._runner_last_used[sid])
        for sid in by_recency[: len(self.runners) - max_runners]:
            self._drop_runner(sid)

    def _drop_runner(self, session_id: str) -> None:
        self.runners.pop(session_id, None)
        self._runner_last_used.pop(session_id, None)

    def _persist(self, runner: WebRunner, title: str | None = None) -> None:
        session = runner.engine.game_session
        is_guest = is_guest_user_id(runner.user_id)
        runner.version = self.db.save_session(
            runner.session_id,
            None if is_guest else runner.user_id,
            title or session.char_name or "新局",
            runner.snapshot(),
            runner.events,
            guest_token_hash=hash_guest_token(runner.guest_token) if is_guest else "",
            expires_at=_guest_expiry() if is_guest else None,
        )

    def _settled_turn_payload(
        self,
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
        calendar_summary = str(
            meta.get("calendar_summary")
            or meta.get("turn_summary")
            or _calendar_summary(before, session, elapsed_years)
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
            "calendar_summary": calendar_summary,
            "narrative": str(turn.get("narrative") or ""),
            "event_kind": event_kind,
            "end_reason": session.error if session.game_over else None,
        }

    def _normalize_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(profile)
        if normalized.get("randomize_attributes"):
            if normalized.get("attributes"):
                normalized["attributes"] = normalize_profile_attributes(
                    normalized.get("attributes", {}),
                    random_mode=True,
                )
            else:
                normalized["attributes"] = _random_attributes()
        else:
            normalized["attributes"] = normalize_profile_attributes(
                normalized.get("attributes", {})
            )
        normalized["randomize_attributes"] = bool(normalized.get("randomize_attributes"))

        catalogs = {
            "talent": self._catalog_rows("catalog_talents"),
            "family_background": self._catalog_rows("catalog_family_backgrounds"),
            "spirit_root": self._catalog_rows("catalog_spirit_roots"),
            "difficulty": self._catalog_rows("catalog_difficulties"),
        }
        catalog_talents = _catalog_names(catalogs["talent"])
        catalog_families = _catalog_names(catalogs["family_background"])
        catalog_roots = _catalog_names(catalogs["spirit_root"])
        catalog_difficulties = _catalog_names(catalogs["difficulty"])

        normalized["talent"] = _pick(
            str(normalized.get("talent") or ""), TALENT_OPTIONS + catalog_talents
        )
        normalized["family_background"] = _pick(
            str(normalized.get("family_background") or ""), FAMILY_BACKGROUNDS + catalog_families
        )
        normalized["difficulty"] = _pick(
            str(normalized.get("difficulty") or ""), DIFFICULTY_OPTIONS + catalog_difficulties
        )
        roots = [item["name"] for item in SPIRIT_ROOTS]
        normalized["spirit_root"] = _pick(
            str(normalized.get("spirit_root") or ""), roots + catalog_roots
        )
        if not normalized.get("spirit_root_grade"):
            root = _catalog_entry(catalogs["spirit_root"], normalized["spirit_root"])
            normalized["spirit_root_grade"] = str(root.get("grade") or "")
        semantics = {
            key: _catalog_semantics(_catalog_entry(rows, str(normalized.get(key) or "")))
            for key, rows in catalogs.items()
        }
        normalized["profile_semantics"] = {key: value for key, value in semantics.items() if value}
        return normalized

    def _catalog_rows(self, table: str) -> list[dict[str, Any]]:
        try:
            return [dict(row) for row in self.db.list_catalog(table)]
        except sqlalchemy.exc.SQLAlchemyError as exc:
            logging.getLogger(__name__).warning("catalog %s fetch failed: %s", table, exc)
            return []

    def _choice_text(self, runner: WebRunner, payload: dict[str, Any]) -> str:
        choices = list(runner.engine.game_session.last_choices or [])
        if "choice_index" in payload and payload["choice_index"] is not None:
            index = int(payload["choice_index"])
            if index < 0 or index >= len(choices):
                raise ValueError("选项序号无效。")
            return choice_with_semantic(index, choices[index])

        raw = str(payload.get("choice") or "").strip()
        letter_map = {"A": 0, "B": 1, "C": 2, "D": 3}
        if raw.upper() in letter_map and letter_map[raw.upper()] < len(choices):
            index = letter_map[raw.upper()]
            return choice_with_semantic(index, choices[index])
        if raw in {"1", "2", "3", "4"}:
            index = int(raw) - 1
            if index < len(choices):
                return choice_with_semantic(index, choices[index])
        if raw:
            raise ValueError("请选择 A/B/C/D。")
        raise ValueError("请选择 A/B/C/D。")


def _catalog_names(rows: list[dict[str, Any]]) -> list[str]:
    return [str(row.get("name") or "") for row in rows if str(row.get("name") or "")]


def _catalog_entry(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next((row for row in rows if str(row.get("name") or "") == name), {})


def _catalog_semantics(row: dict[str, Any]) -> dict[str, Any]:
    return {
        field: row[field]
        for field in _PROFILE_SEMANTIC_FIELDS
        if field in row and row[field] not in (None, "", [], {})
    }


def _pick(value: str, options: list[str]) -> str:
    return value if value in options else options[0]


def is_guest_user_id(user_id: str | None) -> bool:
    return bool(user_id and user_id.startswith(GUEST_USER_PREFIX))


def _guest_expiry() -> float:
    try:
        ttl = int(os.environ.get("AGENS_GUEST_SESSION_TTL_SECONDS", "86400"))
    except ValueError:
        ttl = 86400
    return time.time() + max(300, ttl)


def _random_attributes() -> dict[str, int]:
    remaining = 30
    keys = list(ATTRIBUTE_KEYS)
    random.shuffle(keys)
    values: dict[str, int] = {}
    for index, key in enumerate(keys):
        slots_left = len(keys) - index - 1
        if slots_left == 0:
            value = remaining
        else:
            low = max(0, remaining - slots_left * 10)
            high = min(10, remaining)
            value = random.randint(low, high)
        values[key] = value
        remaining -= value
    return {key: values[key] for key in ATTRIBUTE_KEYS}


# ── Death rewards helpers (P4) ──────────────────────────────────────────────


def _turn_start_snapshot(session: GameSession) -> dict[str, Any]:
    return {
        "turn_no": int(session.turn_count or 0),
        "age": int(session.age or 0),
        "lifespan": int(session.lifespan or 0),
    }


def _calendar_summary(
    before: dict[str, Any],
    session: GameSession,
    elapsed_years: int,
) -> str:
    start_age = int(before.get("age") or session.age)
    if elapsed_years > 0:
        return f"本回合流逝 {elapsed_years} 年，年龄 {start_age}→{session.age}。"
    return f"本回合完成关键抉择，年龄 {session.age}。"
