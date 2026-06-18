"""Service layer that adapts GameEngine to web sessions."""

from __future__ import annotations

import os
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from agens_novel.engine.game_engine import GameEngine, MODEL_FAILURE_CONTINUE
from agens_novel.engine.render import format_status_bar
from agens_novel.game.constants import (
    ATTRIBUTE_KEYS,
    DEFAULT_ATTRIBUTES,
    DIFFICULTY_OPTIONS,
    FAMILY_BACKGROUNDS,
    SPECIAL_START_ATTRIBUTES,
    SPECIAL_START_CODE,
    SPECIAL_START_NAME,
    SPIRIT_ROOTS,
    TALENT_OPTIONS,
)
from agens_novel.session.game_session import GameSession
from agens_novel.settings import Settings

from .database import WebDatabase


@dataclass
class WebRunner:
    """One browser game session with captured engine callbacks."""

    session_id: str
    user_id: str
    engine: GameEngine = field(default_factory=GameEngine)
    events: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.engine.on_narrative = lambda text, turn: self.record("narrative", text=text, turn=turn)
        self.engine.on_status_bar = lambda text: self.record("status", text=text)
        self.engine.on_error = lambda text: self.record("error", text=text)
        self.engine.on_info = lambda text: self.record("info", text=text)
        self.engine.on_game_over = lambda text: self.record("game_over", text=text)
        self.engine.on_finale = lambda text: self.record("finale", text=text)
        self.engine.on_loading = lambda text: self.record("loading", text=text)
        self.engine.on_stream_chunk = lambda text: self.record("stream", text=text)
        self.engine.on_combat_update = lambda combat: self.record("combat", combat=combat)
        self.engine.on_character_created = lambda session: self.record(
            "character_created", state=session.as_game_state()
        )
        self.engine.on_model_failure_choice = self._choose_model_failure

    def _choose_model_failure(self, source: str, reason: str) -> str:
        self.record(
            "model_failure",
            text="模型暂不可用，已切入本地故事兜底。你可以继续本局或结束返回首页。",
            source=source,
            reason=reason,
        )
        return MODEL_FAILURE_CONTINUE

    @classmethod
    def from_snapshot(
        cls,
        session_id: str,
        user_id: str,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]] | None = None,
    ) -> "WebRunner":
        runner = cls(session_id=session_id, user_id=user_id)
        runner.engine.game_session = GameSession.from_save_dict(snapshot)
        runner.events = list(events or [])
        return runner

    def record(self, event_type: str, **payload: Any) -> None:
        self.events.append({"type": event_type, "at": time.time(), **payload})
        self.events = self.events[-120:]

    def response(self) -> dict[str, Any]:
        session = self.engine.game_session
        state = session.as_game_state()
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
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
                "text": "模型暂不可用，当前以本地故事兜底继续；你可以继续本局或结束。",
            },
            "character": state["character"],
            "world": state["world"],
            "events": self.events[-80:],
            "panels": {
                "status_bar": format_status_bar(session),
                "status": self.engine.get_status(),
                "inventory": self.engine.get_inventory(),
                "skills": self.engine.get_skills(),
                "map": self.engine.get_map(),
                "quests": self.engine.get_quests(),
                "realm": self.engine.get_realm_info(),
                "equipment": self.engine.get_equipment_info(),
            },
        }

    def snapshot(self) -> dict[str, Any]:
        return self.engine.game_session.to_save_dict()


class WebGameService:
    """Application service for users, sessions, saves, and settings."""

    def __init__(self, db: WebDatabase | None = None) -> None:
        self.db = db or WebDatabase()
        self.runners: dict[str, WebRunner] = {}

    def login(self, username: str = "local") -> dict[str, Any]:
        return self.db.upsert_user(username)

    def create_session(self, user_id: str = "", title: str = "新局") -> dict[str, Any]:
        user = self._ensure_user(user_id)
        session_id = str(uuid.uuid4())
        runner = WebRunner(session_id=session_id, user_id=user["id"])
        self.runners[session_id] = runner
        runner.record("info", text="新会话已创建。")
        self._persist(runner, title=title)
        return runner.response()

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._runner(session_id).response()

    def start_session(self, session_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        runner = self._runner(session_id)
        runner.engine.start_from_profile(self._normalize_profile(profile))
        self._persist(runner, title=runner.engine.game_session.char_name or "新局")
        return runner.response()

    def choose(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        runner = self._runner(session_id)
        action = self._choice_text(runner, payload)
        runner.engine.handle_action(action)
        self._persist(runner)
        return runner.response()

    def act(self, session_id: str, action: str) -> dict[str, Any]:
        runner = self._runner(session_id)
        runner.engine.handle_action(action)
        self._persist(runner)
        return runner.response()

    def save(self, session_id: str, save_name: str = "slot_1") -> dict[str, Any]:
        runner = self._runner(session_id)
        save = self.db.save_game_slot(
            runner.user_id,
            save_name,
            runner.snapshot(),
            runner.events,
        )
        runner.record("info", text=f"进度已保存: {save['name']}")
        self._persist(runner)
        return {"save": save, "session": runner.response()}

    def load(self, session_id: str, save_name: str = "slot_1") -> dict[str, Any]:
        runner = self._runner(session_id)
        saved = self.db.load_save(runner.user_id, save_name)
        if saved is None:
            raise KeyError(f"存档不存在: {save_name}")
        restored = WebRunner.from_snapshot(
            session_id=session_id,
            user_id=runner.user_id,
            snapshot=saved["snapshot"],
            events=saved.get("events", []),
        )
        restored.record("info", text=f"已加载存档: {saved['name']}")
        self.runners[session_id] = restored
        self._persist(restored, title=restored.engine.game_session.char_name or saved["name"])
        return restored.response()

    def end_session(self, session_id: str, reason: str = "玩家结束本局。") -> dict[str, Any]:
        runner = self._runner(session_id)
        session = runner.engine.game_session
        session.game_over = True
        session.finale = False
        session.error = reason or "玩家结束本局。"
        runner.record("game_over", text=session.error)
        self._persist(runner)
        return runner.response()

    def list_saves(self, user_id: str = "") -> list[dict[str, Any]]:
        user = self._ensure_user(user_id)
        return self.db.list_saves(user["id"])

    def model_settings(self) -> dict[str, Any]:
        stored = self.db.get_model_config() or {}
        settings = Settings()
        api_key_set = bool(os.environ.get("AGNES_API_KEY")) or bool(stored.get("api_key_set"))
        return {
            "provider": stored.get("provider") or "Agens",
            "base_url": os.environ.get("AGNES_BASE_URL") or stored.get("base_url") or settings.base_url,
            "model": os.environ.get("AGNES_MODEL") or stored.get("model") or settings.model,
            "api_key_set": api_key_set,
            "api_key_masked": settings.public_summary()["api_key"]
            if os.environ.get("AGNES_API_KEY")
            else stored.get("api_key_masked", "<unset>"),
        }

    def update_model_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        base_url = str(payload.get("base_url") or "https://apihub.agnes-ai.com/v1").strip()
        model = str(payload.get("model") or "agnes-2.0-flash").strip()
        provider = str(payload.get("provider") or "Agens").strip()
        api_key = str(payload.get("api_key") or "").strip()

        os.environ["AGNES_BASE_URL"] = base_url
        os.environ["AGNES_MODEL"] = model
        if api_key:
            os.environ["AGNES_API_KEY"] = api_key

        summary = Settings().public_summary()
        self.db.save_model_config(
            {
                "provider": provider,
                "base_url": base_url,
                "model": model,
                "api_key_set": bool(os.environ.get("AGNES_API_KEY")),
                "api_key_masked": summary["api_key"],
            }
        )
        return self.model_settings()

    def _runner(self, session_id: str) -> WebRunner:
        if session_id in self.runners:
            return self.runners[session_id]
        row = self.db.load_session(session_id)
        if row is None:
            raise KeyError(f"会话不存在: {session_id}")
        runner = WebRunner.from_snapshot(
            session_id=session_id,
            user_id=row["user_id"],
            snapshot=row["snapshot"],
            events=row.get("events", []),
        )
        self.runners[session_id] = runner
        return runner

    def _persist(self, runner: WebRunner, title: str | None = None) -> None:
        session = runner.engine.game_session
        self.db.save_session(
            runner.session_id,
            runner.user_id,
            title or session.char_name or "新局",
            runner.snapshot(),
            runner.events,
        )

    def _ensure_user(self, user_id: str = "") -> dict[str, Any]:
        if user_id:
            return {"id": user_id, "username": "local"}
        return self.login("local")

    def _normalize_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(profile)
        game_name = str(normalized.get("game_name") or "").strip()
        special = game_name == SPECIAL_START_CODE
        if special:
            normalized["special_start"] = True
            normalized["char_name"] = SPECIAL_START_NAME
            normalized["attributes"] = dict(SPECIAL_START_ATTRIBUTES)
        elif normalized.get("randomize_attributes"):
            normalized["attributes"] = _random_attributes()
        else:
            attrs = normalized.get("attributes")
            if not isinstance(attrs, dict):
                normalized["attributes"] = dict(DEFAULT_ATTRIBUTES)

        normalized["talent"] = _pick(str(normalized.get("talent") or ""), TALENT_OPTIONS)
        normalized["family_background"] = _pick(
            str(normalized.get("family_background") or ""), FAMILY_BACKGROUNDS
        )
        normalized["difficulty"] = _pick(str(normalized.get("difficulty") or ""), DIFFICULTY_OPTIONS)
        roots = [item["name"] for item in SPIRIT_ROOTS]
        normalized["spirit_root"] = _pick(str(normalized.get("spirit_root") or ""), roots)
        return normalized

    def _choice_text(self, runner: WebRunner, payload: dict[str, Any]) -> str:
        choices = list(runner.engine.game_session.last_choices or [])
        if "choice_index" in payload and payload["choice_index"] is not None:
            index = int(payload["choice_index"])
            if index < 0 or index >= len(choices):
                raise ValueError("选项序号无效。")
            return choices[index]

        raw = str(payload.get("choice") or "").strip()
        letter_map = {"A": 0, "B": 1, "C": 2}
        if raw.upper() in letter_map and letter_map[raw.upper()] < len(choices):
            return choices[letter_map[raw.upper()]]
        if raw:
            return raw
        raise ValueError("请选择 A/B/C 或提交行动文本。")


def _pick(value: str, options: list[str]) -> str:
    return value if value in options else options[0]


def _random_attributes() -> dict[str, int]:
    heroic = random.random() < 0.08
    low, high = (75, 99) if heroic else (35, 88)
    return {key: random.randint(low, high) for key in ATTRIBUTE_KEYS}
