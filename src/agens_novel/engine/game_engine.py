"""UI-agnostic game engine for the xianxia cultivation simulator.

The class emits events via callbacks. UI adapters can register
callbacks and drive the game without knowing about the other layers.

All agent calls go through ``run_turn_sync`` which internally uses
``asyncio.run()`` — this must be called from a thread that has no running
event loop.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from agens_novel.settings import Settings

from ..game.realm import RealmSystem, breakthrough_blocking_effects
from ..session.game_session import GameSession
from .breakthrough_flow import BreakthroughFlow
from .choices import (
    choice_with_semantic,
    complete_choices,
    fallback_choices,
    has_visible_english,
    normalize_choices,
)
from .local_story import (
    current_local_story_choices,
    start_local_story,
)
from .model_fallback_policy import (
    SECRET_MARKERS,
    ModelFallbackPolicy,
)
from .model_result import (
    ModelResultKind,
    result_diagnostics,
)
from .start_flow import (
    StartFlow,
)
from .turn_flow import TurnFlow
from .turn_runner import run_turn_sync

log = logging.getLogger(__name__)

# Type aliases for callbacks.
Callback = Callable[..., None]

def _safe_log_reason(reason: str, limit: int = 220) -> str:
    """Trim and redact failure text before it reaches logcat."""
    text = (reason or "").replace("\n", " ").strip()
    lowered = text.lower()
    if any(marker in lowered for marker in SECRET_MARKERS):
        return "redacted model configuration error"
    if "http://" in lowered or "https://" in lowered:
        return "redacted model configuration error"
    return text[:limit]


def _is_sensitive_inventory_item(item: dict[str, Any]) -> bool:
    """Return True for inventory grants that should receive Judge review."""
    rarity = str(item.get("rarity") or item.get("grade") or "")
    if rarity in {"紫", "橙", "红", "上品", "极品", "仙品"}:
        return True
    if bool(item.get("key_item") or item.get("quest_item")):
        return True
    text = f"{item.get('name') or ''} {item.get('type') or ''} {item.get('tags') or ''}"
    markers = ("筑基", "金丹", "元婴", "破境", "延寿", "续命", "法宝", "秘籍", "玉简", "传承")
    return any(marker in text for marker in markers)


def _has_sensitive_character_delta(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    sensitive = {
        "name",
        "realm",
        "realm_stage",
        "spirit_root",
        "spirit_root_grade",
        "talent",
        "family_background",
        "difficulty",
        "inventory",
        "relationship_add",
        "relationships",
        "techniques",
        "techniques_add",
        "breakthrough_flags",
        "breakthrough_flags_add",
        "lifespan",
        "status_effects",
        "status_effects_add",
        "title_add",
        "titles",
    }
    if any(key in value for key in sensitive):
        return True
    additions = value.get("inventory_add")
    return isinstance(additions, list) and any(
        isinstance(item, dict) and _is_sensitive_inventory_item(item) for item in additions
    )


def _has_authoritative_world_delta(value: Any, looks_like_reset: Callable[[Any], bool]) -> bool:
    if not isinstance(value, dict):
        return False
    authoritative = {
        "active_quests",
        "active_quests_add",
        "discovered_add",
        "discovered_locations",
        "npcs_present",
        "npcs_present_add",
    }
    if any(key in value for key in authoritative):
        return True
    return any(
        key in value and looks_like_reset(value.get(key))
        for key in ("location", "region", "current_scene")
    )


class GameEngine:
    """UI-agnostic game logic service.

    Emits events via optional callbacks so any UI can render them.

    Callback attributes (set by UI layer):
        on_narrative(narrative: str, turn: int)
        on_status_bar(text: str)
        on_error(message: str)
        on_info(message: str)
        on_game_over(reason: str)
        on_character_created(session: GameSession)
        on_loading(message: str)
        on_stream_chunk(text: str)
    """

    def __init__(self) -> None:
        self.game_session = GameSession()
        self.realm_system = RealmSystem()

        # Callbacks — set by the UI layer.
        self.on_narrative: Callback | None = None
        self.on_status_bar: Callback | None = None
        self.on_error: Callback | None = None
        self.on_info: Callback | None = None
        self.on_game_over: Callback | None = None
        self.on_character_created: Callback | None = None
        self.on_loading: Callback | None = None
        self.on_stream_chunk: Callback | None = None
        self.on_finale: Callback | None = None
        self.on_model_result: Callback | None = None
        self.on_model_failure_choice: Callable[[str, str], str] | None = None
        self.model_config: dict[str, Any] = {}
        self._fallback_policy = ModelFallbackPolicy(
            lambda: self.on_model_failure_choice,
            _safe_log_reason,
        )
        self._start_flow = StartFlow(self)
        self._turn_flow = TurnFlow(self)
        self._breakthrough_flow = BreakthroughFlow(self)

    # ─── Helper to emit callbacks safely ───────────────────────────────

    def emit(self, attr: str, *args: Any) -> None:
        cb = getattr(self, attr, None)
        if cb is not None:
            cb(*args)


    # ─── Stream callback wrapper ──────────────────────────────────────

    def stream_callback(self, text: str) -> None:
        """Forward stream chunks to the UI layer."""
        self.emit("on_stream_chunk", text)

    def run_agent(self, agent_name: str, user_input: str, session: GameSession, **kwargs: Any) -> dict[str, Any]:
        """Call the agent runner through the GameEngine module patch seam."""
        model_config = self.model_config if isinstance(self.model_config, dict) else {}
        for key in (
            "provider",
            "model",
            "base_url",
            "api_key",
            "api_key_set",
            "source",
            "key_error",
        ):
            if key in model_config:
                kwargs.setdefault(key, model_config.get(key))
        return run_turn_sync(agent_name, user_input, session, **kwargs)

    def set_choices(
        self,
        raw_choices: Any,
        *,
        source: str,
        fallback_notice: bool = False,
        require_choice: bool = False,
        reason: str = "",
        emit_local_story_narrative: bool = False,
    ) -> bool:
        """Set current choices from model output, falling back only when empty."""
        choices = complete_choices(raw_choices, self.game_session)
        if choices:
            semantic_fallbacks = fallback_choices(self.game_session)
            choices = [
                semantic_fallbacks[index] if has_visible_english(choice) else choice
                for index, choice in enumerate(choices)
            ]
            choices = self._filter_unavailable_breakthrough_choices(choices)
            self.game_session.last_choices = choices
            return False

        if require_choice and not self.confirm_local_fallback(source, reason):
            self.end_model_failure_run(reason or "模型未返回可用选项。")
            return False

        if require_choice:
            self._enter_local_story(reason, emit_narrative=emit_local_story_narrative)
        else:
            self.game_session.last_choices = fallback_choices(self.game_session)
        log.info(
            "choice fallback used: source=%s reason=%s local_story=%s",
            source,
            _safe_log_reason(reason),
            self.game_session.local_story_active,
        )
        if fallback_notice:
            self.emit("on_info", self.fallback_notice_for(reason))
        return True

    def _enter_local_story(self, reason: str = "", *, emit_narrative: bool = True) -> tuple[str, list[str]]:
        """Switch the current run to a preset local story and emit its state."""
        if self.game_session.local_story_active:
            self.game_session.last_choices = self._filter_unavailable_breakthrough_choices(
                current_local_story_choices(self.game_session)
            )
            return "", list(self.game_session.last_choices)
        result = start_local_story(self.game_session)
        self.game_session.last_choices = self._filter_unavailable_breakthrough_choices(result.choices)
        if emit_narrative and result.narrative:
            self.emit("on_narrative", result.narrative, self.game_session.turn_count)
        if reason:
            log.info("entered local story fallback: reason=%s story=%s node=%s", _safe_log_reason(reason), self.game_session.local_story_id, self.game_session.local_story_node_id)
        return result.narrative, result.choices

    def fallback_notice_for(self, reason: str = "") -> str:
        """Return a player-visible fallback message without exposing secrets."""
        return self._fallback_policy.notice_for(reason)

    def log_model_result(
        self,
        *,
        agent: str,
        source: str,
        status: ModelResultKind | str,
        reason: str,
        result: dict[str, Any],
    ) -> None:
        """Write a non-secret model diagnostic line for runtime triage."""
        model_config = self.model_config if isinstance(self.model_config, dict) else {}
        model = model_config.get("model") or os.environ.get("AGNES_MODEL", Settings().model)
        base_url = model_config.get("base_url") or os.environ.get("AGNES_BASE_URL", Settings().base_url)
        diagnostics = result_diagnostics(result)
        log.info(
            "model_result agent=%s source=%s status=%s model_set=%s base_url_set=%s key_set=%s config_source=%s reason=%s diagnostics=%s",
            agent,
            source,
            getattr(status, "value", status),
            bool(model),
            bool(base_url),
            bool(model_config.get("api_key_set")),
            model_config.get("source") or "env",
            _safe_log_reason(reason),
            diagnostics,
        )
        self.emit(
            "on_model_result",
            agent,
            source,
            getattr(status, "value", status),
            bool(model),
            bool(base_url),
            bool(model_config.get("api_key_set")),
            model_config.get("source") or "env",
            diagnostics,
        )

    def confirm_local_fallback(self, source: str, reason: str = "") -> bool:
        """Ask the UI whether model failure should continue with local fallback."""
        return self._fallback_policy.should_continue(source, reason)

    def end_model_failure_run(self, reason: str) -> None:
        """End the current run after the user declines local model fallback."""
        self.game_session.game_over = True
        self.game_session.finale = False
        self.game_session.error = "模型不可用导致本局结束。"
        log.warning("model failure ended run: %s", reason)
        self.emit("on_game_over", self.game_session.error)

    # ─── Game commands ─────────────────────────────────────────────────

    def new_game(self, concept: str) -> None:
        """Create a new character via the World Builder agent."""
        self._start_flow.new_game(concept)

    def start_from_profile(self, profile: dict[str, Any]) -> None:
        """Create a deterministic game from the character form.

        This keeps character creation on the same engine path as every other
        UI operation. Public Alpha starts from local templates by default so
        the first screen is not blocked by model latency; model-generated
        world/opening can be opted into with runtime env switches.
        """
        self._start_flow.start_from_profile(profile)

    def handle_action(self, text: str) -> None:
        """Process a player action through Narrator + Judge.

        Supports streaming via ``on_stream_chunk``.
        """

        if not self.game_session.game_started:
            self.emit("on_info", "尚未开始游戏。请返回主页选择新游戏。")
            return

        if self.game_session.game_over:
            self.emit("on_info", f"游戏已结束: {self.game_session.error}\n请使用重新开始或读取存档继续。")
            return

        selected_choice = self._resolve_choice_input(text)
        if selected_choice is not None:
            text = selected_choice

        if self.game_session.local_story_active:
            self._turn_flow.handle_local_story_action(text)
            return

        # Route natural-language breakthrough intent only when the realm rules
        # allow a real breakthrough. Otherwise the chosen button still settles
        # as an ordinary turn instead of returning 200 with no progression.
        if self._should_route_breakthrough_action(text):
            self.attempt_breakthrough()
            return

        self._turn_flow.handle_action(text)

    def attempt_local_story_breakthrough(self) -> dict[str, Any]:
        """Use the existing realm rules for a local-story breakthrough."""
        can, reason = self.realm_system.can_attempt_breakthrough(self.game_session)
        if not can:
            self.emit("on_info", reason)
            return {}
        delta = self.realm_system.attempt_breakthrough(self.game_session)
        return delta

    def _parse_breakthrough_action(self, text: str) -> bool:
        """Detect natural-language breakthrough intent.

        Allows option text to include "突破", "尝试突破", "冲击筑基",
        "准备渡劫飞升", etc. without relying on a command syntax.
        """
        compact = "".join(text.strip().lower().split())
        keywords = (
            "突破", "尝试突破", "冲击下一境界", "准备渡劫",
            "冲关", "破境", "渡劫飞升",
            "冲击筑基", "冲击金丹", "冲击元婴", "冲击化神",
            "冲击合体", "冲击大乘", "冲击渡劫", "冲击飞升",
            "准备突破",
        )
        return any(kw in compact for kw in keywords)

    def _should_route_breakthrough_action(self, text: str) -> bool:
        if not self._parse_breakthrough_action(text):
            return False
        can, reason = self.realm_system.can_attempt_breakthrough(self.game_session)
        if can:
            return True
        if reason:
            self.emit("on_info", f"{reason} 本次行动按修炼/探索继续推进。")
        return False

    def _filter_unavailable_breakthrough_choices(self, choices: list[str]) -> list[str]:
        """Keep breakthrough actions in the C slot and aligned with realm rules."""
        can, _reason = self.realm_system.can_attempt_breakthrough(self.game_session)
        fallbacks = fallback_choices(self.game_session)
        blockers = breakthrough_blocking_effects(self.game_session.status_effects)

        if can:
            rewritten = [
                fallbacks[index]
                if index != 2 and self._parse_breakthrough_action(choice)
                else choice
                for index, choice in enumerate(choices)
            ]
            if len(rewritten) > 2 and not self._parse_breakthrough_action(rewritten[2]):
                next_realm = self.realm_system.get_next_realm(self.game_session.realm)
                target = next_realm or "下一境界"
                rewritten[2] = f"正式冲击{target}，承担破境失败风险"
            return rewritten

        if blockers:
            choices = list(choices)
            choices[0] = f"疗伤调息，先化解{'、'.join(blockers)}并稳住根基"
        if not any(self._parse_breakthrough_action(choice) for choice in choices):
            return choices
        filtered: list[str] = []
        for index, choice in enumerate(choices):
            if self._parse_breakthrough_action(choice):
                filtered.append(fallbacks[index] if index < len(fallbacks) else fallbacks[-1])
            else:
                filtered.append(choice)
        return filtered

    def _resolve_choice_input(self, text: str) -> str | None:
        """Map A/B/C/D or 1/2/3/4 input to the current model choice.

        Game mode: A/B/C/D are 4 fixed buttons. D = 气运/天命 (fixed semantics).
        """
        raw = text.strip()
        if not raw:
            return None

        normalized = raw.upper().replace("．", ".").replace("：", ":")
        choices = normalize_choices(self.game_session.last_choices)

        key = normalized.rstrip(".:、)） ").strip()
        mapping = {"A": 0, "B": 1, "C": 2, "D": 3, "1": 0, "2": 1, "3": 2, "4": 3}
        if key in mapping:
            index = mapping[key]
            return choice_with_semantic(index, choices[index]) if index < len(choices) else None

        return None

    # ─── Breakthrough ─────────────────────────────────────────────────

    def attempt_breakthrough(self) -> None:
        """Attempt a realm breakthrough."""
        self._breakthrough_flow.attempt_breakthrough()

    # ─── Game over check ─────────────────────────────────────────────

    def check_game_over(self) -> bool:
        """Check for game-over conditions (lifespan depletion, finale flag).

        Returns True if game is over.
        """
        if self.game_session.game_over:
            if self.game_session.finale:
                self.emit("on_finale", self.game_session.error or "飞升成仙，修真之路圆满。")
                return True
            self.emit("on_game_over", self.game_session.error or "游戏结束。")
            return True

        return False

    def reset(self) -> None:
        """Reset the game session."""
        self.game_session.reset()
        self.emit("on_info", "游戏已重置。请返回角色创建重新开始。")

    # ─── Internal helpers ──────────────────────────────────────────────

    def record_opening_context(self, opening: str) -> None:
        """Seed chat history so the first player action cannot look like a blank world."""
        if not opening:
            return
        self.game_session.chat_history = [
            {
                "role": "assistant",
                "content": (
                    "开局已经建立，当前角色、地点和世界状态以当前状态 JSON 为准。\n"
                    f"{opening}"
                ),
            }
        ]

    def should_run_judge(
        self,
        text: str,
        state_delta: dict[str, Any],
        rule_delta: dict[str, Any],
    ) -> bool:
        """Reserve model judging for risky or continuity-sensitive outcomes."""
        if not isinstance(state_delta, dict):
            return False
        meta_value = state_delta.get("meta")
        meta: dict[str, Any] = meta_value if isinstance(meta_value, dict) else {}
        if meta.get("game_over") or meta.get("finale") or meta.get("breakthrough_result"):
            return True
        compact = "".join(text.strip().lower().split())
        if any(word in compact for word in ("突破", "破境", "渡劫", "飞升")):
            return True

        if _has_sensitive_character_delta(state_delta.get("character")):
            return True
        return _has_authoritative_world_delta(state_delta.get("world"), self._looks_like_world_reset)

    def sanitize_action_delta(self, delta: dict[str, Any]) -> dict[str, Any]:
        """Drop ordinary-turn updates that reset character identity or continuity.

        LLM output is intentionally high variance, but web free actions must
        not re-open the world or replace the player's established profile.
        Breakthroughs use a dedicated engine path.
        """
        if not isinstance(delta, dict):
            return {}

        sanitized: dict[str, Any] = dict(delta)
        char_delta = sanitized.get("character")
        if isinstance(char_delta, dict):
            char_delta = dict(char_delta)
            for key in (
                "name",
                "realm",
                "realm_stage",
                "spirit_root",
                "spirit_root_grade",
                "talent",
                "family_background",
                "difficulty",
                "attributes",
                "lifespan",
                "inventory",
                "techniques",
                "experience",
                "experience_to_next",
                "insight",
                "gold",
                "combat",
                "hp",
                "hp_max",
                "mp",
                "mp_max",
            ):
                char_delta.pop(key, None)
            sanitized["character"] = char_delta

        world_delta = sanitized.get("world")
        if isinstance(world_delta, dict):
            world_delta = dict(world_delta)
            world_delta.pop("story_update", None)
            for key in ("location", "region", "current_scene"):
                value = world_delta.get(key)
                if self._looks_like_world_reset(value):
                    world_delta.pop(key, None)
            sanitized["world"] = world_delta

        return sanitized

    def action_delta_resets_world(self, delta: Any) -> bool:
        """Return whether model output tries to replace the established world."""
        if not isinstance(delta, dict):
            return False
        world = delta.get("world")
        if not isinstance(world, dict):
            return False
        return any(
            key in world and self._looks_like_world_reset(world.get(key))
            for key in ("location", "region", "current_scene")
        )

    def _looks_like_world_reset(self, value: Any) -> bool:
        """Detect common first-scene resets that contradict an established run."""
        if not isinstance(value, str):
            return True
        if not value.strip():
            return True
        lowered = value.lower()
        reset_markers = ("混沌", "虚空", "未开", "起源", "void", "chaos")
        return any(marker in lowered for marker in reset_markers)
