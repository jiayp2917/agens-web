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

from ..game.realm import RealmSystem
from ..session.game_session import GameSession
from .choices import (
    complete_choices,
    fallback_choices,
    normalize_choices,
)
from .breakthrough_flow import BreakthroughFlow
from .local_story import (
    current_local_story_choices,
    start_local_story,
)
from .model_result import (
    ModelResultKind,
    result_diagnostics,
)
from .model_fallback_policy import (
    MODEL_FAILURE_CONTINUE,
    MODEL_FAILURE_END,
    MODEL_FAILURE_PROMPT,
    ModelFallbackPolicy,
)
from .start_flow import (
    StartFlow,
)
from .turn_runner import run_turn_sync
from .turn_flow import TurnFlow
from .render import (
    format_equipment,
    format_inventory,
    format_log,
    format_map,
    format_quests,
    format_realm,
    format_skills,
    format_status_card,
)

log = logging.getLogger(__name__)

# Type aliases for callbacks.
Callback = Callable[..., None]

def _safe_log_reason(reason: str, limit: int = 220) -> str:
    """Trim and redact failure text before it reaches logcat."""
    text = (reason or "").replace("\n", " ").strip()
    lowered = text.lower()
    if any(marker in lowered for marker in ("sk-", "api_key", "apikey", "authorization")):
        return "redacted model configuration error"
    return text[:limit]


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
        self.on_model_failure_choice: Callable[[str, str], str] | None = None
        self._fallback_policy = ModelFallbackPolicy(
            lambda: self.on_model_failure_choice,
            _safe_log_reason,
        )
        self._start_flow = StartFlow(self)
        self._turn_flow = TurnFlow(self)
        self._breakthrough_flow = BreakthroughFlow(self)

    # ─── Helper to emit callbacks safely ───────────────────────────────

    def _emit(self, attr: str, *args: Any) -> None:
        cb = getattr(self, attr, None)
        if cb is not None:
            cb(*args)


    # ─── Stream callback wrapper ──────────────────────────────────────

    def _stream_callback(self, text: str) -> None:
        """Forward stream chunks to the UI layer."""
        self._emit("on_stream_chunk", text)

    def _run_agent(self, agent_name: str, user_input: str, session: GameSession, **kwargs: Any) -> dict[str, Any]:
        """Call the agent runner through the GameEngine module patch seam."""
        return run_turn_sync(agent_name, user_input, session, **kwargs)

    def _set_choices(
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
            self.game_session.last_choices = choices
            return False

        if require_choice and not self._confirm_local_fallback(source, reason):
            self._end_model_failure_run(reason or "模型未返回可用选项。")
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
            self._emit("on_info", self._fallback_notice_for(reason))
        return True

    def _enter_local_story(self, reason: str = "", *, emit_narrative: bool = True) -> tuple[str, list[str]]:
        """Switch the current run to a preset local story and emit its state."""
        if self.game_session.local_story_active:
            self.game_session.last_choices = current_local_story_choices(self.game_session)
            return "", list(self.game_session.last_choices)
        result = start_local_story(self.game_session)
        self.game_session.last_choices = result.choices
        if emit_narrative and result.narrative:
            self._emit("on_narrative", result.narrative, self.game_session.turn_count)
        if reason:
            log.info("entered local story fallback: reason=%s story=%s node=%s", _safe_log_reason(reason), self.game_session.local_story_id, self.game_session.local_story_node_id)
        return result.narrative, result.choices

    def _fallback_notice_for(self, reason: str = "") -> str:
        """Return a player-visible fallback message without exposing secrets."""
        return self._fallback_policy.notice_for(reason)

    def _log_model_result(
        self,
        *,
        agent: str,
        source: str,
        status: ModelResultKind | str,
        reason: str,
        result: dict[str, Any],
    ) -> None:
        """Write a non-secret model diagnostic line for runtime triage."""
        model = os.environ.get("AGNES_MODEL", "agnes-2.0-flash")
        base_url = os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
        log.info(
            "model_result agent=%s source=%s status=%s model=%s base_url=%s key_set=%s reason=%s diagnostics=%s",
            agent,
            source,
            getattr(status, "value", status),
            model,
            base_url,
            bool(os.environ.get("AGNES_API_KEY")),
            _safe_log_reason(reason),
            result_diagnostics(result),
        )

    def _confirm_local_fallback(self, source: str, reason: str = "") -> bool:
        """Ask the UI whether model failure should continue with local fallback."""
        return self._fallback_policy.should_continue(source, reason)

    def _end_model_failure_run(self, reason: str) -> None:
        """End the current run after the user declines local model fallback."""
        self.game_session.game_over = True
        self.game_session.finale = False
        self.game_session.error = "模型不可用导致本局结束。"
        log.warning("model failure ended run: %s", reason)
        self._emit("on_game_over", self.game_session.error)

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

    def _generate_world_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        """Generate a structured world profile for the character session.

        Uses the model only when explicitly enabled; otherwise falls back to
        a local template. The world profile is stored in the session and
        used to contextualize subsequent turns.
        """
        return self._start_flow.generate_world_profile(profile)

    def _generate_profile_opening(self, profile: dict[str, Any]) -> tuple[str, list[str]]:
        """Ask World Builder for the first scene after form creation."""
        return self._start_flow.generate_profile_opening(profile)

    def handle_action(self, text: str) -> None:
        """Process a player action through Narrator + Judge.

        Supports streaming via ``on_stream_chunk``.
        """

        if not self.game_session.game_started:
            self._emit("on_info", "尚未开始游戏。请返回主页选择新游戏。")
            return

        if self.game_session.game_over:
            self._emit("on_info", f"游戏已结束: {self.game_session.error}\n请使用重新开始或读取存档继续。")
            return

        selected_choice = self._resolve_choice_input(text)
        if selected_choice is not None:
            text = selected_choice

        if self.game_session.local_story_active:
            self._turn_flow.handle_local_story_action(text)
            return

        # Route natural-language breakthrough intent before event resolution
        # so "突破" mid-event is still treated as breakthrough.
        if self._parse_breakthrough_action(text):
            self.attempt_breakthrough()
            return

        self._turn_flow.handle_action(text)

    def _attempt_local_story_breakthrough(self) -> None:
        """Use the existing realm rules for a local-story breakthrough."""
        can, reason = self.realm_system.can_attempt_breakthrough(self.game_session)
        if not can:
            self._emit("on_info", reason)
            return
        delta = self.realm_system.attempt_breakthrough(self.game_session)
        self.game_session.apply_delta(delta)
        result = delta.get("meta", {}).get("breakthrough_result", "")
        if result == "success":
            if self.game_session.finale:
                self._emit("on_finale", self.game_session.error or "飞升成仙，修真之路圆满。")
            else:
                self._emit("on_info", format_realm(self.game_session))
        elif result == "failure":
            self._emit("on_info", "突破失败，受到反噬。")

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
            return choices[index] if index < len(choices) else None

        return None

    # ─── Breakthrough ─────────────────────────────────────────────────

    def attempt_breakthrough(self) -> None:
        """Attempt a realm breakthrough."""
        self._breakthrough_flow.attempt_breakthrough()

    # ─── Game over check ─────────────────────────────────────────────

    def _check_game_over(self) -> bool:
        """Check for game-over conditions (lifespan depletion, finale flag).

        Returns True if game is over.
        """
        if self.game_session.game_over:
            if self.game_session.finale:
                self._emit("on_finale", self.game_session.error or "飞升成仙，修真之路圆满。")
                return True
            self._emit("on_game_over", self.game_session.error or "游戏结束。")
            return True

        return False

    def reset(self) -> None:
        """Reset the game session."""
        self.game_session.reset()
        self._emit("on_info", "游戏已重置。请返回角色创建重新开始。")

    # ─── World expansion ─────────────────────────────────────────────

    def expand(self, gen_type: str = "new_region") -> None:
        """Request world expansion from the World Builder."""
        if not self.game_session.game_started:
            self._emit("on_info", "请先从主页创建角色并开始游戏。")
            return

        if gen_type not in ("new_region", "new_encounter", "new_technique"):
            gen_type = "new_region"

        self._emit("on_loading", "世界扩展中...")

        try:
            result = run_turn_sync(
                "world_builder", gen_type, self.game_session,
                generation_type=gen_type,
            )
        except Exception:
            log.exception("expand error")
            self._emit("on_error", "世界扩展失败（详见日志）")
            return

        if result.get("llm_error"):
            self._emit("on_error", f"扩展失败: {result['llm_error']}")
            return

        desc = result.get("world_description", "")
        if desc:
            self._emit("on_narrative", desc, 0)

        generated = result.get("generated_data", {})
        if generated:
            world = generated.get("world", {})
            if "lore_add" in world:
                self.game_session.lore_facts.extend(world["lore_add"])
            if "discovered_add" in world:
                self.game_session.discovered_locations.extend(world["discovered_add"])

    # ─── Read-only queries ─────────────────────────────────────────────

    def get_status(self) -> str:
        return format_status_card(self.game_session)

    def get_inventory(self) -> str:
        return format_inventory(self.game_session)

    def get_skills(self) -> str:
        return format_skills(self.game_session)

    def get_map(self) -> str:
        return format_map(self.game_session)

    def get_quests(self) -> str:
        return format_quests(self.game_session)

    def get_log(self, count: int = 5) -> str:
        return format_log(self.game_session, count)

    def get_realm_info(self) -> str:
        return format_realm(self.game_session)

    def get_equipment_info(self) -> str:
        return format_equipment(self.game_session)

    # ─── Internal helpers ──────────────────────────────────────────────

    def _record_opening_context(self, opening: str) -> None:
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

    def _should_run_judge(
        self,
        text: str,
        state_delta: dict[str, Any],
        rule_delta: dict[str, Any],
    ) -> bool:
        """Reserve model judging for risky or continuity-sensitive outcomes."""
        if not isinstance(state_delta, dict):
            return False
        meta = state_delta.get("meta") if isinstance(state_delta.get("meta"), dict) else {}
        rule_meta = rule_delta.get("meta") if isinstance(rule_delta.get("meta"), dict) else {}
        if meta.get("game_over") or meta.get("finale") or meta.get("breakthrough_result"):
            return True
        if rule_meta.get("choice_category") == "风险":
            return True
        compact = "".join(text.strip().lower().split())
        if any(word in compact for word in ("突破", "破境", "渡劫", "飞升", "斗法", "禁地", "豪赌")):
            return True

        char_delta = state_delta.get("character")
        if isinstance(char_delta, dict):
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
                "techniques",
                "breakthrough_flags",
            }
            if any(key in char_delta for key in sensitive):
                return True
            additions = char_delta.get("inventory_add")
            if isinstance(additions, list):
                for item in additions:
                    if isinstance(item, dict) and str(item.get("rarity") or "") in {"紫", "橙", "红", "上品", "极品", "仙品"}:
                        return True

        world_delta = state_delta.get("world")
        if isinstance(world_delta, dict):
            for key in ("location", "region", "current_scene"):
                if key in world_delta and self._looks_like_world_reset(world_delta.get(key)):
                    return True
        return False

    def _sanitize_action_delta(self, delta: dict[str, Any]) -> dict[str, Any]:
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
            for key in ("location", "region", "current_scene"):
                value = world_delta.get(key)
                if self._looks_like_world_reset(value):
                    world_delta.pop(key, None)
            sanitized["world"] = world_delta

        return sanitized

    def _looks_like_world_reset(self, value: Any) -> bool:
        """Detect common first-scene resets that contradict an established run."""
        if not isinstance(value, str):
            return True
        if not value.strip():
            return True
        lowered = value.lower()
        reset_markers = ("混沌", "虚空", "未开", "起源", "void", "chaos")
        return any(marker in lowered for marker in reset_markers)

