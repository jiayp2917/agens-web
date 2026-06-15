"""Bridge between GameEngine and Kivy's main thread.

GameEngine calls run_turn_sync which uses asyncio.run() internally.
Kivy runs its own event loop via SDL2. asyncio.run() cannot be called
from within an already-running event loop, so we run game engine calls
in a background thread and post results back to Kivy via Clock.schedule_once.
"""

from __future__ import annotations

import threading
import logging
from collections.abc import Callable
from typing import Any

from kivy.clock import Clock

from agens_novel.engine.game_engine import GameEngine

log = logging.getLogger(__name__)


class EngineAdapter:
    """Thread-safe bridge: GameEngine → Kivy UI.

    Supports streaming (on_stream_chunk) and combat (on_combat_update)
    callbacks in addition to the original set.

    Usage:
        adapter = EngineAdapter()
        adapter.on_narrative = lambda text, turn: label.text += text
        adapter.on_stream_chunk = lambda text: narrative_view.append_chunk(text)
        adapter.new_game("我叫许满")
    """

    def __init__(self) -> None:
        self.engine = GameEngine()
        self._thread: threading.Thread | None = None

        # Register engine callbacks that schedule UI updates on Kivy thread.
        self.engine.on_narrative = lambda text, turn: Clock.schedule_once(
            lambda dt: self._emit("on_narrative", text, turn))
        self.engine.on_status_bar = lambda text: Clock.schedule_once(
            lambda dt: self._emit("on_status_bar", text))
        self.engine.on_error = lambda msg: Clock.schedule_once(
            lambda dt: self._emit("on_error", msg))
        self.engine.on_info = lambda msg: Clock.schedule_once(
            lambda dt: self._emit("on_info", msg))
        self.engine.on_game_over = lambda reason: Clock.schedule_once(
            lambda dt: self._emit("on_game_over", reason))
        self.engine.on_character_created = lambda session: Clock.schedule_once(
            lambda dt: self._emit("on_character_created", session))
        self.engine.on_loading = lambda msg: Clock.schedule_once(
            lambda dt: self._emit("on_loading", msg))
        self.engine.on_finale = lambda reason: Clock.schedule_once(
            lambda dt: self._emit("on_finale", reason))
        self.engine.on_stream_chunk = lambda text: Clock.schedule_once(
            lambda dt: self._emit("on_stream_chunk", text))
        self.engine.on_combat_update = lambda combat_state: Clock.schedule_once(
            lambda dt: self._emit("on_combat_update", combat_state))

        # UI callbacks — set by the screen.
        self.on_narrative: Callable | None = None
        self.on_status_bar: Callable | None = None
        self.on_error: Callable | None = None
        self.on_info: Callable | None = None
        self.on_game_over: Callable | None = None
        self.on_character_created: Callable | None = None
        self.on_loading: Callable | None = None
        self.on_stream_chunk: Callable | None = None
        self.on_combat_update: Callable | None = None
        self.on_finale: Callable | None = None

    def _emit(self, event: str, *args: Any) -> None:
        cb = getattr(self, event, None)
        if cb is not None:
            cb(*args)

    @property
    def game_session(self):
        return self.engine.game_session

    def _run_in_thread(self, fn: Any, *args: Any, **kwargs: Any) -> None:
        """Run a blocking game-engine call in a background thread."""
        if self._thread and self._thread.is_alive():
            self._emit("on_info", "请等待当前操作完成...")
            return

        def target():
            try:
                fn(*args, **kwargs)
            except Exception as exc:
                log.exception("Game engine worker failed")
                message = str(exc)
                if "maximum recursion depth exceeded" in message:
                    message = "内部日志系统异常，请重试或查看运行日志。"
                Clock.schedule_once(lambda dt: self._emit("on_error", message))

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def new_game(self, concept: str) -> None:
        self._run_in_thread(self.engine.new_game, concept)

    def start_from_profile(self, profile: dict[str, Any]) -> None:
        self._run_in_thread(self.engine.start_from_profile, profile)

    def handle_action(self, text: str) -> None:
        self._run_in_thread(self.engine.handle_action, text)

    def handle_combat_action(self, action: str, target: str = "") -> None:
        self._run_in_thread(self.engine.handle_combat_action, action, target)

    def attempt_breakthrough(self) -> None:
        self._run_in_thread(self.engine.attempt_breakthrough)

    def save(self, name: str = "autosave") -> None:
        # Save is fast, can run on main thread.
        self.engine.save(name)
        self._emit("on_info", f"进度已保存: {name}")

    def load(self, name: str = "autosave") -> None:
        self.engine.load(name)

    def reset(self) -> None:
        self.engine.reset()

    def list_saves(self) -> list[dict[str, Any]]:
        return self.engine.list_saves()

    def delete_save(self, name: str) -> None:
        self.engine.delete_save(name)

    def get_status(self) -> str:
        return self.engine.get_status()

    def get_inventory(self) -> str:
        return self.engine.get_inventory()

    def get_skills(self) -> str:
        return self.engine.get_skills()

    def get_map(self) -> str:
        return self.engine.get_map()

    def get_quests(self) -> str:
        return self.engine.get_quests()

    def get_log(self) -> str:
        return self.engine.get_log()

    def get_realm_info(self) -> str:
        return self.engine.get_realm_info()

    def get_equipment_info(self) -> str:
        return self.engine.get_equipment_info()
