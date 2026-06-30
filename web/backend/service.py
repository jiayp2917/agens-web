"""Service layer that adapts GameEngine to web sessions."""

from __future__ import annotations

import os
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from agens_novel.engine.death_rewards import (
    apply_legacy_bonuses,
    bonuses_to_legacy,
)
from agens_novel.engine.game_engine import GameEngine, MODEL_FAILURE_CONTINUE
from agens_novel.engine.render import format_status_bar
from agens_novel.engine.start_flow import normalize_profile_attributes
from agens_novel.game.constants import (
    ATTRIBUTE_KEYS,
    DIFFICULTY_OPTIONS,
    FAMILY_BACKGROUNDS,
    SPIRIT_ROOTS,
    TALENT_OPTIONS,
)
from agens_novel.session.game_session import GameSession
from agens_novel.settings import Settings

from .model_config_security import (
    ModelConfigSecretError,
    decrypt_api_key,
    encrypt_api_key,
    mask_api_key,
)

from .database import WebDatabaseProtocol
from .database_postgres import PostgresWebDatabase
from .service_summaries import build_death_summary

PUBLIC_MODEL_FALLBACK_TEXT = "模型暂不可用，当前以本地故事继续。"
_MODEL_FAILURE_PREFIXES = (
    "世界生成失败:",
    "叙述失败:",
    "天道审判失败:",
    "突破叙事失败:",
    "突破审判失败:",
)
_SECRET_MARKERS = ("sk-", "api_key", "apikey", "authorization", "database_url", "postgresql://")
GUEST_USER_PREFIX = "guest:"


@dataclass
class WebRunner:
    """One browser game session with captured engine callbacks."""

    session_id: str
    user_id: str
    engine: GameEngine = field(default_factory=GameEngine)
    events: list[dict[str, Any]] = field(default_factory=list)
    guest_token: str = ""
    db: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.engine.on_narrative = lambda text, turn: self.record("narrative", text=text, turn=turn)
        self.engine.on_status_bar = lambda text: self.record("status", text=text)
        self.engine.on_error = lambda text: self.record("error", text=text)
        self.engine.on_info = lambda text: self.record("info", text=text)
        self.engine.on_game_over = lambda text: self._on_game_over(text)
        self.engine.on_finale = lambda text: self.record("finale", text=text)
        self.engine.on_loading = lambda text: self.record("loading", text=text)
        self.engine.on_stream_chunk = lambda text: None
        self.engine.on_character_created = lambda session: self.record(
            "character_created", state=session.as_game_state()
        )
        self.engine.on_model_failure_choice = self._choose_model_failure

    def _on_game_over(self, text: str) -> None:
        """Record game-over and evaluate rewards (P4).

        Evaluates achievements/rewards even for guest sessions (in-memory only).
        Registered users get the results persisted to the database.
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
        # Persist for registered users only.
        if not is_guest_user_id(self.user_id):
            try:
                self._persist_death_rewards(
                    self.engine.game_session,
                    self.user_id,
                    self.session_id,
                    summary,
                )
            except Exception:
                log.exception("death rewards persistence failed")

    def _choose_model_failure(self, source: str, reason: str) -> str:
        self.record(
            "model_failure",
            text=PUBLIC_MODEL_FALLBACK_TEXT,
            source=source,
        )
        return MODEL_FAILURE_CONTINUE

    @classmethod
    def from_snapshot(
        cls,
        session_id: str,
        user_id: str,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]] | None = None,
        db: Any = None,
    ) -> "WebRunner":
        runner = cls(session_id=session_id, user_id=user_id, db=db)
        runner.engine.game_session = GameSession.from_save_dict(snapshot)
        runner.events = list(events or [])
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
                "active": session.local_story_active and not session.game_over,
                "text": PUBLIC_MODEL_FALLBACK_TEXT,
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

    def _persist_death_rewards(
        self,
        session: GameSession,
        user_id: str,
        session_id: str,
        summary: dict[str, Any],
    ) -> None:
        """Write achievements, account rewards, and legacy bonuses to the DB."""
        if self.db is None:
            return
        db = self.db
        existing_rewards = [
            reward
            for reward in db.list_account_rewards(user_id)
            if reward.get("source_session_id") == session_id
        ]
        if db.list_run_achievements(user_id, session_id) or existing_rewards:
            return
        db.record_game_run(
            user_id=user_id,
            run_id=session_id,
            session_id=session_id,
            char_name=session.char_name,
            realm=session.realm,
            death_cause=str(summary.get("death_cause") or ""),
            ascended=bool(session.finale),
            turn_count=int(session.turn_count or 0),
        )
        for achievement in summary.get("achievements", []) or []:
            db.save_run_achievement(
                user_id=user_id,
                session_id=session_id,
                achievement_key=str(achievement.get("key") or ""),
                achievement_name=str(achievement.get("name") or ""),
                description=str(achievement.get("description") or ""),
                death_cause=str(summary.get("death_cause") or ""),
            )
        for reward in summary.get("rewards", []) or []:
            db.save_account_reward(
                user_id=user_id,
                reward_type=str(reward.get("type") or ""),
                reward_value=str(reward.get("value") or ""),
                label=str(reward.get("label") or ""),
                source_session_id=session_id,
            )
        for bonus in bonuses_to_legacy(summary.get("rewards", []) or []):
            db.save_legacy_bonus(
                user_id=user_id,
                bonus_type=str(bonus.get("bonus_type") or ""),
                bonus_value=str(bonus.get("bonus_value") or ""),
                label=str(bonus.get("label") or ""),
                source_session_id=session_id,
                runs_remaining=int(bonus.get("runs_remaining") or 1),
            )


def _sanitize_event_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(payload)
    if event_type == "model_failure":
        sanitized.pop("reason", None)
        sanitized["text"] = PUBLIC_MODEL_FALLBACK_TEXT
        return sanitized
    if event_type == "error":
        text = str(sanitized.get("text") or "")
        if _looks_internal_model_error(text):
            sanitized["text"] = PUBLIC_MODEL_FALLBACK_TEXT
    return sanitized


def _looks_internal_model_error(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in _SECRET_MARKERS):
        return True
    if any(text.startswith(prefix) for prefix in _MODEL_FAILURE_PREFIXES):
        return True
    return bool(re.search(r"https?://\S+", text))


class WebGameService:
    """Application service for users, sessions, saves, and settings."""

    def __init__(self, db: WebDatabaseProtocol | None = None) -> None:
        self.db = db or PostgresWebDatabase()
        self.runners: dict[str, WebRunner] = {}
        self._runner_last_used: dict[str, float] = {}

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

    def get_session(self, session_id: str, user_id: str | None = None) -> dict[str, Any]:
        return self._runner(session_id, user_id=user_id).response()

    def start_session(
        self, session_id: str, profile: dict[str, Any], user_id: str | None = None
    ) -> dict[str, Any]:
        runner = self._runner(session_id, user_id=user_id)
        self._apply_runner_model_config(runner)
        normalized = self._normalize_profile(profile)
        # Apply legacy bonuses from prior runs (P4) — registered users only.
        if user_id and not is_guest_user_id(user_id):
            bonuses = self.db.list_legacy_bonuses(user_id)
            if bonuses:
                normalized = apply_legacy_bonuses(
                    normalized,
                    [
                        {
                            "bonus_type": b["bonus_type"],
                            "bonus_value": b["bonus_value"],
                            "label": b.get("label", ""),
                        }
                        for b in bonuses
                    ],
                )
                normalized["_allow_legacy_bonus_attributes"] = True
                self.db.consume_legacy_bonuses(user_id)
        runner.engine.start_from_profile(normalized)
        self._persist(runner, title=runner.engine.game_session.char_name or "新局")
        return runner.response()

    def choose(
        self, session_id: str, payload: dict[str, Any], user_id: str | None = None
    ) -> dict[str, Any]:
        runner = self._runner(session_id, user_id=user_id)
        action = self._choice_text(runner, payload)
        return self._advance_turn(runner, action)

    def act(self, session_id: str, action: str, user_id: str | None = None) -> dict[str, Any]:
        runner = self._runner(session_id, user_id=user_id)
        return self._advance_turn(runner, action)

    def _advance_turn(self, runner: WebRunner, action: str) -> dict[str, Any]:
        self._apply_runner_model_config(runner)
        before = _turn_start_snapshot(runner.engine.game_session)
        runner.engine.handle_action(action)
        self._record_settled_turn(runner, before, action)
        self._persist(runner)
        return runner.response()

    def save(
        self, session_id: str, save_name: str = "slot_1", user_id: str | None = None
    ) -> dict[str, Any]:
        runner = self._require_non_guest_runner(session_id, user_id, action="存档")
        save = self.db.save_game_slot(
            runner.user_id,
            save_name,
            runner.snapshot(),
            runner.events,
        )
        runner.record("info", text=f"进度已保存: {save['name']}")
        self._persist(runner)
        return {"save": save, "session": runner.response()}

    def load(
        self, session_id: str, save_name: str = "slot_1", user_id: str | None = None
    ) -> dict[str, Any]:
        runner = self._require_non_guest_runner(session_id, user_id, action="读档")
        saved = self.db.load_save(runner.user_id, save_name)
        if saved is None:
            raise KeyError(f"存档不存在: {save_name}")
        restored = WebRunner.from_snapshot(
            session_id=session_id,
            user_id=runner.user_id,
            snapshot=saved["snapshot"],
            events=saved.get("events", []),
            db=self.db,
        )
        restored.record("info", text=f"已加载存档: {saved['name']}")
        self._register_runner(session_id, restored)
        self._persist(restored, title=restored.engine.game_session.char_name or saved["name"])
        return restored.response()

    def end_session(
        self, session_id: str, reason: str = "玩家结束本局。", user_id: str | None = None
    ) -> dict[str, Any]:
        runner = self._runner(session_id, user_id=user_id)
        session = runner.engine.game_session
        session.game_over = True
        session.finale = False
        session.error = reason or "玩家结束本局。"
        # Reuse the engine's on_game_over hook so P4 rewards fire on manual end too.
        if runner.engine.on_game_over is not None:
            runner.engine.on_game_over(session.error)
        else:
            runner.record("game_over", text=session.error)
        self._persist(runner)
        return runner.response()

    def list_saves(self, user_id: str = "") -> list[dict[str, Any]]:
        if not user_id:
            raise PermissionError("读取存档需要登录。")
        return self.db.list_saves(user_id)

    # ── Death rewards (P4) ──────────────────────────────────────────────

    def death_summary(
        self, session_id: str, user_id: str | None = None
    ) -> dict[str, Any]:
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

        return self._stored_death_summary(session_id, user_id)

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

    def _stored_death_summary(self, session_id: str, user_id: str) -> dict[str, Any]:
        achievements = self.db.list_run_achievements(user_id, session_id)
        rewards = [
            r
            for r in self.db.list_account_rewards(user_id)
            if r.get("source_session_id") == session_id
        ]
        if not achievements and not rewards:
            return {"session_id": session_id, "is_guest": False, "summary": {}}
        death_cause = achievements[0].get("death_cause", "") if achievements else ""
        headline_parts = [a.get("achievement_name") for a in achievements[:3] if a.get("achievement_name")]
        headline = "、".join(headline_parts) if headline_parts else ""
        return {
            "session_id": session_id,
            "is_guest": False,
            "summary": {
                "death_cause": death_cause,
                "achievements": [
                    {
                        "key": a.get("achievement_key", ""),
                        "name": a.get("achievement_name", ""),
                        "description": a.get("description", ""),
                    }
                    for a in achievements
                ],
                "rewards": [
                    {
                        "type": r.get("reward_type", ""),
                        "value": r.get("reward_value", ""),
                        "label": r.get("label", ""),
                    }
                    for r in rewards
                ],
                "headline": headline,
            },
        }

    def legacy_bonuses(self, user_id: str) -> list[dict[str, Any]]:
        if not user_id or is_guest_user_id(user_id):
            return []
        return self.db.list_legacy_bonuses(user_id)

    def model_settings(self, user_id: str) -> dict[str, Any]:
        return self._public_model_settings(self._effective_model_config(user_id))

    def update_model_settings(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.db.get_user_model_config(user_id) or {}
        config = self._build_stored_model_config(payload, existing=current)
        self.db.save_user_model_config(user_id, config)
        return self.model_settings(user_id)

    def clear_model_settings(self, user_id: str) -> dict[str, Any]:
        self.db.delete_user_model_config(user_id)
        return self.model_settings(user_id)

    def admin_model_settings(self) -> dict[str, Any]:
        return self._public_model_settings(self._system_model_config())

    def update_admin_model_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.db.get_model_config() or {}
        config = self._build_stored_model_config(payload, existing=current)
        self.db.save_model_config(config)
        return self.admin_model_settings()

    def _build_stored_model_config(
        self,
        payload: dict[str, Any],
        *,
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing = existing or {}
        base_url = str(payload.get("base_url") or "https://apihub.agnes-ai.com/v1").strip()
        model = str(payload.get("model") or "agnes-2.0-flash").strip()
        provider = str(payload.get("provider") or "Agens").strip()
        api_key = str(payload.get("api_key") or "").strip()
        encrypted = str(existing.get("api_key_encrypted") or "")
        masked = str(existing.get("api_key_masked") or "<unset>")
        if api_key:
            try:
                encrypted = encrypt_api_key(api_key)
            except ModelConfigSecretError as exc:
                raise ValueError("MODEL_CONFIG_SECRET is required to save model keys.") from exc
            masked = mask_api_key(api_key)
        api_key_set = bool(encrypted)
        return {
            "provider": provider,
            "base_url": base_url,
            "model": model,
            "api_key_set": api_key_set,
            "api_key_masked": masked if api_key_set else "<unset>",
            "api_key_encrypted": encrypted,
        }

    def _public_model_settings(self, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider": config.get("provider") or "Agens",
            "base_url": config.get("base_url") or "https://apihub.agnes-ai.com/v1",
            "model": config.get("model") or "agnes-2.0-flash",
            "api_key_set": bool(config.get("api_key_set")),
            "api_key_masked": str(config.get("api_key_masked") or "<unset>"),
            "source": config.get("source") or "system",
        }

    def _system_model_config(self) -> dict[str, Any]:
        stored = self.db.get_model_config() or {}
        settings = Settings()
        source = "system"
        if stored:
            config = {
                "provider": stored.get("provider") or "Agens",
                "base_url": stored.get("base_url") or settings.base_url,
                "model": stored.get("model") or settings.model,
                "api_key_set": bool(stored.get("api_key_encrypted")),
                "api_key_masked": stored.get("api_key_masked") if stored.get("api_key_encrypted") else "<unset>",
                "api_key_encrypted": stored.get("api_key_encrypted") or "",
                "source": source,
            }
        else:
            env_key = os.environ.get("AGNES_API_KEY", "")
            config = {
                "provider": "Agens",
                "base_url": os.environ.get("AGNES_BASE_URL") or settings.base_url,
                "model": os.environ.get("AGNES_MODEL") or settings.model,
                "api_key_set": bool(env_key),
                "api_key_masked": mask_api_key(env_key) if env_key else "<unset>",
                "api_key_encrypted": "",
                "source": source,
                "api_key": env_key,
            }
        return config

    def _effective_model_config(self, user_id: str | None) -> dict[str, Any]:
        if user_id and not is_guest_user_id(user_id):
            personal = self.db.get_user_model_config(user_id)
            if personal is not None:
                return {
                    "provider": personal.get("provider") or "Agens",
                    "base_url": personal.get("base_url") or "https://apihub.agnes-ai.com/v1",
                    "model": personal.get("model") or "agnes-2.0-flash",
                    "api_key_set": bool(personal.get("api_key_encrypted")),
                    "api_key_masked": personal.get("api_key_masked") if personal.get("api_key_encrypted") else "<unset>",
                    "api_key_encrypted": personal.get("api_key_encrypted") or "",
                    "source": "user",
                }
        return self._system_model_config()

    def _runtime_model_config(self, user_id: str | None) -> dict[str, Any]:
        effective = self._effective_model_config(user_id)
        encrypted = str(effective.get("api_key_encrypted") or "")
        api_key = str(effective.get("api_key") or "")
        key_error = ""
        if encrypted:
            try:
                api_key = decrypt_api_key(encrypted)
            except ModelConfigSecretError:
                api_key = ""
                key_error = "MODEL_CONFIG_SECRET unavailable"
        return {
            "provider": effective.get("provider") or "Agens",
            "base_url": effective.get("base_url") or "https://apihub.agnes-ai.com/v1",
            "model": effective.get("model") or "agnes-2.0-flash",
            "api_key": api_key,
            "api_key_set": bool(api_key),
            "source": effective.get("source") or "system",
            "key_error": key_error,
        }

    def _apply_runner_model_config(self, runner: WebRunner) -> None:
        runner.engine.model_config = self._runtime_model_config(runner.user_id)

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
        )
        self._register_runner(session_id, runner)
        return runner

    def _register_runner(self, session_id: str, runner: WebRunner) -> None:
        """Cache a runner and bound the in-memory cache (LRU + idle TTL).

        Registered-user runners are rebuilt from the DB on next access, so
        eviction is near-lossless. Guest runners are not persisted, so evicting
        one ends that ephemeral session.
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
        if is_guest_user_id(runner.user_id):
            return
        session = runner.engine.game_session
        self.db.save_session(
            runner.session_id,
            runner.user_id,
            title or session.char_name or "新局",
            runner.snapshot(),
            runner.events,
        )

    def _record_settled_turn(
        self,
        runner: WebRunner,
        before: dict[str, Any],
        choice_taken: str,
    ) -> None:
        """Persist the latest settled turn for registered users.

        This is telemetry/progression state for GAME_MODE_SPEC §8.3; a write
        failure must not block play because the authoritative session snapshot
        is still saved through _persist().
        """
        if is_guest_user_id(runner.user_id):
            return
        session = runner.engine.game_session
        if session.turn_count <= int(before.get("turn_no") or 0):
            return
        if not session.turn_history:
            return
        turn = session.turn_history[-1]
        if int(turn.get("turn") or 0) != session.turn_count:
            return

        delta = turn.get("delta") if isinstance(turn.get("delta"), dict) else {}
        meta = delta.get("meta") if isinstance(delta, dict) else {}
        if not isinstance(meta, dict):
            meta = {}
        elapsed_years = int(meta.get("elapsed_years") or max(0, session.age - int(before.get("age") or session.age)))
        calendar_summary = str(
            meta.get("calendar_summary")
            or meta.get("turn_summary")
            or _calendar_summary(before, session, elapsed_years)
        )
        event_kind = str(meta.get("choice_category") or turn.get("event_kind") or "event")
        try:
            self.db.record_game_turn(
                runner.session_id,
                session.turn_count,
                start_age=int(before.get("age") or session.age),
                elapsed_years=elapsed_years,
                end_age=int(session.age),
                lifespan=int(session.lifespan),
                remaining_lifespan=session.remaining_lifespan,
                choice_taken=choice_taken,
                choices=list(turn.get("choices") or session.last_choices or []),
                state_delta=delta,
                state_after=session.as_game_state(),
                calendar_summary=calendar_summary,
                narrative=str(turn.get("narrative") or ""),
                event_kind=event_kind,
                end_reason=session.error if session.game_over else None,
            )
        except Exception:
            log.exception("game turn persistence failed")

    def _normalize_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(profile)
        if normalized.get("randomize_attributes"):
            normalized["attributes"] = _random_attributes()
        else:
            normalized["attributes"] = normalize_profile_attributes(normalized.get("attributes", {}))
        normalized["randomize_attributes"] = bool(normalized.get("randomize_attributes"))

        catalog_talents = self._catalog_names("catalog_talents")
        catalog_families = self._catalog_names("catalog_family_backgrounds")
        catalog_roots = self._catalog_names("catalog_spirit_roots")
        catalog_difficulties = self._catalog_names("catalog_difficulties")

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
            normalized["spirit_root_grade"] = self._catalog_spirit_root_grade(
                normalized["spirit_root"]
            )
        return normalized

    def _catalog_names(self, table: str) -> list[str]:
        try:
            return [
                str(row.get("name") or "")
                for row in self.db.list_catalog(table)
                if str(row.get("name") or "")
            ]
        except Exception:
            return []

    def _catalog_spirit_root_grade(self, name: str) -> str:
        try:
            for row in self.db.list_catalog("catalog_spirit_roots"):
                if row.get("name") == name:
                    return str(row.get("grade") or "")
        except Exception:
            return ""
        return ""

    def _choice_text(self, runner: WebRunner, payload: dict[str, Any]) -> str:
        choices = list(runner.engine.game_session.last_choices or [])
        if "choice_index" in payload and payload["choice_index"] is not None:
            index = int(payload["choice_index"])
            if index < 0 or index >= len(choices):
                raise ValueError("选项序号无效。")
            return choices[index]

        raw = str(payload.get("choice") or "").strip()
        letter_map = {"A": 0, "B": 1, "C": 2, "D": 3}
        if raw.upper() in letter_map and letter_map[raw.upper()] < len(choices):
            return choices[letter_map[raw.upper()]]
        if raw:
            raise ValueError("请选择 A/B/C/D。")
        raise ValueError("请选择 A/B/C/D。")


def _pick(value: str, options: list[str]) -> str:
    return value if value in options else options[0]


def is_guest_user_id(user_id: str | None) -> bool:
    return bool(user_id and user_id.startswith(GUEST_USER_PREFIX))


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

import logging  # noqa: E402

log = logging.getLogger(__name__)


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
