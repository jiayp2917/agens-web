"""UI-agnostic game engine for the xianxia cultivation simulator.

The class emits events via callbacks. Android/Kivy UI can register
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

from ..game.combat import CombatEngine
from ..game.constants import (
    DEFAULT_ATTRIBUTES,
    DEFAULT_GAME_MODE,
    DIFFICULTY_OPTIONS,
    FAMILY_BACKGROUNDS,
    SPECIAL_START_ATTRIBUTES,
    SPECIAL_START_NAME,
    SPIRIT_ROOTS,
    TALENT_OPTIONS,
)
from ..game.realm import RealmSystem
from ..session.game_session import GameSession
from ..persistence.save_manager import delete_save, list_saves, load_game, rename_save, save_game
from .action_delta_policy import (
    INSIGHT_BASE_GAIN,
    apply_breakthrough_flag_rule,
    apply_cultivation_limit,
    apply_insight_rule,
    is_pure_cultivation,
    validate_narrative_delta_consistency,
)
from .choices import (
    CHOICE_FALLBACK_NOTICE,
    fallback_choices,
    normalize_choices,
)
from .model_result import (
    ModelResultKind,
    classify_judge_result,
    classify_narrator_result,
    classify_world_builder_result,
)
from .profile_opening import (
    luck_from_attributes,
    profile_concept,
    profile_default_world,
    profile_opening,
)
from .turn_runner import run_turn_sync
from .render import (
    format_combat,
    format_equipment,
    format_inventory,
    format_log,
    format_map,
    format_quests,
    format_realm,
    format_skills,
    format_status_bar,
    format_status_card,
)

log = logging.getLogger(__name__)

# Type aliases for callbacks.
Callback = Callable[..., None]

MODEL_FAILURE_PROMPT = "天道紊乱，是否以因果残影继续推演？"
MODEL_FAILURE_CONTINUE = "fallback"
MODEL_FAILURE_END = "end"


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
        on_combat_update(combat_state: dict | None)
    """

    def __init__(self) -> None:
        self.game_session = GameSession()
        self.combat_engine = CombatEngine()
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
        self.on_combat_update: Callback | None = None
        self.on_finale: Callback | None = None
        self.on_model_failure_choice: Callable[[str, str], str] | None = None

    # ─── Helper to emit callbacks safely ───────────────────────────────

    def _emit(self, attr: str, *args: Any) -> None:
        cb = getattr(self, attr, None)
        if cb is not None:
            cb(*args)

    def _has_api_key(self) -> bool:
        """Let agent nodes report missing API keys as normal LLM failures."""
        return True

    # ─── Stream callback wrapper ──────────────────────────────────────

    def _stream_callback(self, text: str) -> None:
        """Forward stream chunks to the UI layer."""
        self._emit("on_stream_chunk", text)

    def _set_choices(
        self,
        raw_choices: Any,
        *,
        source: str,
        fallback_notice: bool = False,
        require_choice: bool = False,
        reason: str = "",
    ) -> bool:
        """Set current choices from model output, falling back only when empty."""
        choices = normalize_choices(raw_choices)
        if choices:
            self.game_session.last_choices = choices
            return False

        if require_choice and not self._confirm_local_fallback(source, reason):
            self._end_model_failure_run(reason or "模型未返回可用选项。")
            return False

        self.game_session.last_choices = fallback_choices(self.game_session)
        log.info("choice fallback used: source=%s", source)
        if fallback_notice:
            self._emit("on_info", self._fallback_notice_for(reason))
        return True

    def _fallback_notice_for(self, reason: str = "") -> str:
        """Return a player-visible fallback message without exposing secrets."""
        reason = (reason or "").strip()
        if "不完整" in reason or "未返回" in reason or "格式" in reason:
            return reason
        return CHOICE_FALLBACK_NOTICE

    def _confirm_local_fallback(self, source: str, reason: str = "") -> bool:
        """Ask the UI whether model failure should continue with local fallback."""
        callback = self.on_model_failure_choice
        if callback is None:
            return True
        try:
            decision = callback(source, reason or "模型输出不可用。")
        except Exception:
            log.exception("model failure choice callback failed")
            return True
        return decision != MODEL_FAILURE_END

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
        concept = concept.strip()
        if not concept:
            self._emit("on_info", "已取消。")
            return

        # Reset session.
        self.game_session.reset()

        self._emit("on_loading", "天道初开，世界生成中...")

        try:
            result = run_turn_sync(
                "world_builder", concept, self.game_session,
                generation_type="new_game",
            )
        except Exception:
            log.exception("world_builder error")
            reason = "世界生成失败（详见日志）"
            self._emit("on_error", reason)
            if self._confirm_local_fallback("world_builder_exception", reason):
                self._set_choices(None, source="world_builder_exception", fallback_notice=True)
            else:
                self._end_model_failure_run(reason)
            return

        if result.get("llm_error"):
            reason = f"世界生成失败: {result['llm_error']}"
            self._emit("on_error", reason)
            if self._confirm_local_fallback("world_builder_error", reason):
                self._set_choices(None, source="world_builder_error", fallback_notice=True)
            else:
                self._end_model_failure_run(reason)
            return

        # Extract generated data.
        generated = result.get("generated_data", {})
        if not generated:
            self._emit("on_info", "世界数据为空，请重试。")
            return

        # Apply character data.
        char_data = generated.get("character", {})
        if char_data:
            self.game_session.char_name = char_data.get("name", "无名")
            self.game_session.realm = char_data.get("realm", "练气")
            self.game_session.realm_stage = char_data.get("realm_stage", 1)
            self.game_session.hp = char_data.get("hp", 100)
            self.game_session.hp_max = char_data.get("hp_max", 100)
            self.game_session.mp = char_data.get("mp", 50)
            self.game_session.mp_max = char_data.get("mp_max", 50)
            self.game_session.spirit_root = char_data.get("spirit_root", "")
            self.game_session.spirit_root_grade = char_data.get("spirit_root_grade", "")
            self.game_session.age = char_data.get("age", self.game_session.age)
            self.game_session.talent = char_data.get("talent", self.game_session.talent)
            self.game_session.family_background = char_data.get("family_background", self.game_session.family_background)
            self.game_session.luck = char_data.get("luck", self.game_session.luck)
            self.game_session.difficulty = char_data.get("difficulty", self.game_session.difficulty)
            self.game_session.game_mode = DEFAULT_GAME_MODE
            attrs = char_data.get("attributes")
            if isinstance(attrs, dict):
                merged_attrs = dict(self.game_session.attributes)
                for key, value in attrs.items():
                    if isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool):
                        merged_attrs[key] = max(0, min(100, value))
                self.game_session.attributes = merged_attrs
            self.game_session.experience = char_data.get("experience", 0)
            self.game_session.experience_to_next = char_data.get("experience_to_next", 100)
            self.game_session.gold = char_data.get("gold", 0)
            self.game_session.techniques = char_data.get("techniques", [])
            self.game_session.inventory = char_data.get("inventory", [])
            self.game_session.status_effects = char_data.get("status_effects", [])
            self.game_session.lifespan = char_data.get("lifespan", 100)
            # New fields.
            if "equipment_slots" in char_data:
                self.game_session.equipment_slots = char_data["equipment_slots"]

        # Apply world data.
        world_data = generated.get("world", {})
        if world_data:
            self.game_session.current_scene = world_data.get("current_scene", "")
            self.game_session.location = world_data.get("location", "")
            self.game_session.region = world_data.get("region", "")
            self.game_session.npcs_present = world_data.get("npcs_present", [])
            self.game_session.active_quests = world_data.get("active_quests", [])
            self.game_session.discovered_locations = world_data.get("discovered_locations", [])
            self.game_session.lore_facts = world_data.get("lore_facts", [])
            self.game_session.day_count = world_data.get("day_count", 1)

        self.game_session.game_started = True
        self.game_session.turn_count = 0

        # Display opening narrative.
        opening = generated.get("opening_narrative", result.get("opening_narrative", ""))
        if not opening:
            desc = result.get("world_description", "")
            opening = desc or "世界已生成。"

        if self._set_choices(
            generated.get("choices"),
            source="world_builder",
            fallback_notice=True,
            require_choice=True,
            reason="世界生成未返回可用选项。",
        ) is False and self.game_session.game_over:
            return
        self._emit("on_narrative", opening, 0)
        self._emit("on_character_created", self.game_session)
        self._emit("on_status_bar", format_status_bar(self.game_session))
        self._record_opening_context(opening)
        self._auto_save()

    def start_from_profile(self, profile: dict[str, Any]) -> None:
        """Create a deterministic mobile game from the character form.

        This keeps the Kivy character-creation screen on the same engine path
        as every other UI operation. When the profile does not already carry
        opening choices, the engine asks World Builder for a first 天道 scene;
        local fallback is used only if that model call fails.
        """
        special = bool(profile.get("special_start"))
        attrs = dict(SPECIAL_START_ATTRIBUTES if special else DEFAULT_ATTRIBUTES)
        incoming_attrs = profile.get("attributes", {})
        if isinstance(incoming_attrs, dict):
            for key, value in incoming_attrs.items():
                if isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool):
                    attrs[key] = max(0, min(100, value))

        self.game_session.reset()
        self.game_session.game_started = True
        self.game_session.game_over = False
        self.game_session.turn_count = 0
        self.game_session.char_name = str(profile.get("char_name") or (SPECIAL_START_NAME if special else "无名"))
        self.game_session.realm = "练气"
        self.game_session.realm_stage = 1
        self.game_session.age = int(profile.get("age") or 16)
        self.game_session.talent = str(profile.get("talent") or TALENT_OPTIONS[0])
        self.game_session.spirit_root = str(profile.get("spirit_root") or SPIRIT_ROOTS[0]["name"])
        self.game_session.spirit_root_grade = str(profile.get("spirit_root_grade") or "")
        self.game_session.family_background = str(profile.get("family_background") or FAMILY_BACKGROUNDS[0])
        self.game_session.difficulty = str(profile.get("difficulty") or DIFFICULTY_OPTIONS[1])
        self.game_session.luck = str(profile.get("luck") or luck_from_attributes(attrs))
        self.game_session.game_mode = DEFAULT_GAME_MODE
        self.game_session.attributes = attrs
        self.game_session.hp = int(profile.get("hp") or (999 if special else 100))
        self.game_session.hp_max = int(profile.get("hp_max") or self.game_session.hp)
        self.game_session.mp = int(profile.get("mp") or (999 if special else 50))
        self.game_session.mp_max = int(profile.get("mp_max") or self.game_session.mp)
        self.game_session.gold = int(profile.get("gold") or (9999 if special else 20))
        self.game_session.techniques = list(profile.get("techniques") or [{"name": "基础吐纳术", "level": 1, "type": "内功"}])
        self.game_session.inventory = list(profile.get("inventory") or [{"name": "粗布道袍", "quantity": 1, "type": "防具"}])
        default_scene, default_location, default_region, default_lore = profile_default_world(profile)
        self.game_session.current_scene = str(profile.get("current_scene") or default_scene)
        self.game_session.location = str(profile.get("location") or default_location)
        self.game_session.region = str(profile.get("region") or default_region)
        self.game_session.discovered_locations = [self.game_session.location]
        self.game_session.lore_facts = [default_lore]

        profile_choices = normalize_choices(profile.get("choices"))
        self._emit("on_loading", "天道推演开局中...")
        generated_opening, generated_choices = self._generate_profile_opening(profile, special)
        if self.game_session.game_over:
            return
        opening = str(
            profile.get("opening_narrative")
            or generated_opening
            or profile_opening(
                self.game_session,
                special=special,
                game_name=str(profile.get("game_name") or "").strip(),
            )
        )
        if self._set_choices(
            generated_choices or profile_choices,
            source="profile_opening",
            fallback_notice=True,
            require_choice=True,
            reason="开场推演未返回可用选项。",
        ) is False and self.game_session.game_over:
            return
        self._emit("on_narrative", opening, 0)
        self._emit("on_character_created", self.game_session)
        self._emit("on_status_bar", format_status_bar(self.game_session))
        self._record_opening_context(opening)
        self._auto_save()

    def _generate_profile_opening(self, profile: dict[str, Any], special: bool) -> tuple[str, list[str]]:
        """Ask World Builder for the first mobile scene after form creation."""
        if not os.environ.get("AGNES_API_KEY"):
            reason = "AGNES_API_KEY 未设置。"
            if self._confirm_local_fallback("profile_opening_missing_key", reason):
                self._emit("on_info", CHOICE_FALLBACK_NOTICE)
                return "", normalize_choices(profile.get("choices")) or fallback_choices(self.game_session)
            self._end_model_failure_run(reason)
            return "", []

        concept = profile_concept(profile, special=special)
        try:
            result = run_turn_sync(
                "world_builder", concept, self.game_session,
                generation_type="new_game",
            )
        except Exception:
            log.exception("profile opening world_builder error")
            if self._confirm_local_fallback("profile_opening_exception", "开场推演失败（详见日志）。"):
                self._emit("on_info", CHOICE_FALLBACK_NOTICE)
                return "", normalize_choices(profile.get("choices")) or fallback_choices(self.game_session)
            else:
                self._end_model_failure_run("开场推演失败（详见日志）。")
            return "", []

        world_status = classify_world_builder_result(result)
        if world_status.kind == ModelResultKind.REQUEST_FAILED:
            log.warning("profile opening world_builder failed: %s", result["llm_error"])
            reason = world_status.reason.replace("世界生成失败", "开场推演失败", 1)
            if self._confirm_local_fallback("profile_opening_error", reason):
                self._emit("on_info", CHOICE_FALLBACK_NOTICE)
                return "", normalize_choices(profile.get("choices")) or fallback_choices(self.game_session)
            else:
                self._end_model_failure_run(reason)
            return "", []

        generated = result.get("generated_data", {})
        if world_status.kind == ModelResultKind.INCOMPLETE_OUTPUT or not isinstance(generated, dict):
            reason = world_status.reason or "开场推演数据不可用。"
            if self._confirm_local_fallback("profile_opening_empty", reason):
                self._emit("on_info", CHOICE_FALLBACK_NOTICE)
                return "", normalize_choices(profile.get("choices")) or fallback_choices(self.game_session)
            else:
                self._end_model_failure_run(reason)
            return "", []

        world = generated.get("world", {})
        if isinstance(world, dict):
            self.game_session.current_scene = world.get("current_scene", self.game_session.current_scene)
            self.game_session.location = world.get("location", self.game_session.location)
            self.game_session.region = world.get("region", self.game_session.region)
            self.game_session.npcs_present = world.get("npcs_present", self.game_session.npcs_present)
            self.game_session.active_quests = world.get("active_quests", self.game_session.active_quests)
            self.game_session.discovered_locations = world.get(
                "discovered_locations", self.game_session.discovered_locations,
            )
            self.game_session.lore_facts = world.get("lore_facts", self.game_session.lore_facts)
            self.game_session.day_count = world.get("day_count", self.game_session.day_count)

        opening = str(generated.get("opening_narrative") or result.get("opening_narrative") or "")
        return opening, normalize_choices(generated.get("choices"))

    def handle_action(self, text: str) -> None:
        """Process a player action through Narrator + Judge.

        Supports streaming (via on_stream_chunk callback) and combat detection.
        """
        if not self._has_api_key():
            self._emit("on_error", "AGNES_API_KEY 未设置。请先配置 API Key。")
            return

        if not self.game_session.game_started:
            self._emit("on_info", "尚未开始游戏。请返回主页选择新游戏。")
            return

        if self.game_session.game_over:
            self._emit("on_info", f"游戏已结束: {self.game_session.error}\n请使用重新开始或读取存档继续。")
            return

        selected_choice = self._resolve_choice_input(text)
        if selected_choice is not None:
            text = selected_choice

        # Route natural-language breakthrough intent before combat check
        # so "突破" during combat is still treated as breakthrough.
        if self._parse_breakthrough_action(text):
            self.attempt_breakthrough()
            return

        combat_action = self._parse_typed_combat_action(text)
        if combat_action is not None:
            action, target = combat_action
            self.handle_combat_action(action, target)
            return

        self.game_session.turn_count += 1

        self._emit("on_loading", "天道运转中...")

        # Step 1: Run narrator with stream callback.
        try:
            narrator_result = run_turn_sync(
                "narrator", text, self.game_session,
                stream_callback=self._stream_callback if self.on_stream_chunk else None,
            )
        except Exception:
            log.exception("narrator error")
            reason = "叙述失败（详见日志）"
            self._emit("on_error", reason)
            self._set_choices(
                None,
                source="narrator_exception",
                fallback_notice=True,
                require_choice=True,
                reason=reason,
            )
            self.game_session.turn_count -= 1
            return

        narrator_status = classify_narrator_result(narrator_result)
        if narrator_status.kind == ModelResultKind.REQUEST_FAILED:
            reason = narrator_status.reason
            self._emit("on_error", reason)
            self._set_choices(
                None,
                source="narrator_error",
                fallback_notice=True,
                require_choice=True,
                reason=reason,
            )
            self.game_session.turn_count -= 1
            return

        narrative = narrator_result.get("narrative", "")
        state_delta = narrator_result.get("state_delta", {})
        if not isinstance(state_delta, dict):
            state_delta = {}
        choices = narrator_result.get("choices", [])
        if narrator_status.kind == ModelResultKind.INCOMPLETE_OUTPUT:
            self._emit("on_info", narrator_status.reason)
        if self._set_choices(
            choices,
            source="narrator",
            fallback_notice=True,
            require_choice=True,
            reason=narrator_status.reason if narrator_status.kind == ModelResultKind.INCOMPLETE_OUTPUT else "叙事模型未返回可用选项。",
        ) is False and self.game_session.game_over:
            self.game_session.turn_count -= 1
            return

        # Step 2: Run judge (if there is a delta to validate).
        if state_delta:
            self._emit("on_loading", "天道审判中...")
            try:
                judge_result = run_turn_sync(
                    "judge", text, self.game_session,
                    narrative=narrative,
                    state_delta=state_delta,
                )
            except Exception:
                log.exception("judge error")
                reason = "天道审判失败（详见日志）"
                if not self._confirm_local_fallback("judge_exception", reason):
                    self.game_session.turn_count -= 1
                    self._end_model_failure_run(reason)
                    return
                # On judge error, default to NOT approving (safe default).
                judge_result = {"approved": False, "corrected_delta": {}, "judgment_note": reason}

            judge_status = classify_judge_result(judge_result)
            if judge_status.kind == ModelResultKind.JUDGE_FAILED:
                reason = judge_status.reason
                if not self._confirm_local_fallback("judge_error", reason):
                    self.game_session.turn_count -= 1
                    self._end_model_failure_run(reason)
                    return
                judge_result = {"approved": False, "corrected_delta": {}, "judgment_note": reason}

            if judge_result.get("approved") is False:
                corrected = judge_result.get("corrected_delta", {})
                if corrected:
                    state_delta = corrected
                else:
                    # Judge rejected and no corrected delta — skip applying.
                    note = judge_result.get("judgment_note", "")
                    log.info("Judge rejected (no corrected delta): %s", note)
                    self._emit("on_info", "天道审判未通过，行动结果暂不生效。")
                    self._emit("on_status_bar", format_status_bar(self.game_session))
                    self._auto_save()
                    return
                note = judge_result.get("judgment_note", "")
                if note:
                    log.info("Judge corrected: %s", note)

        consistent, consistency_reason = validate_narrative_delta_consistency(narrative, state_delta)
        if not consistent:
            log.info("Narrative/state mismatch rejected: %s", consistency_reason)
            self._emit("on_info", consistency_reason)
            self._emit("on_status_bar", format_status_bar(self.game_session))
            self._auto_save()
            return

        state_delta = self._sanitize_action_delta(state_delta)

        # Apply the 感悟 (insight) rule: pure cultivation grants no insight;
        # any other action gains a baseline (plus whatever the LLM granted).
        is_cultivation = self._is_pure_cultivation(text)
        state_delta = self._apply_cultivation_limit(state_delta, is_cultivation)
        state_delta = self._apply_insight_rule(text, state_delta)
        state_delta = self._apply_breakthrough_flag_rule(text, state_delta, is_cultivation)

        combat_delta_seen = False
        combat_delta = None
        char_delta = state_delta.get("character")
        if isinstance(char_delta, dict) and "combat" in char_delta:
            combat_delta_seen = True
            char_delta = dict(char_delta)
            combat_delta = char_delta.pop("combat")
            state_delta = {**state_delta, "character": char_delta}

        # Step 3: Apply non-combat delta.
        self.game_session.apply_delta(state_delta)

        # Step 3.5: Auto-advance small layers — chain until no more advancement.
        while True:
            stage_delta = self.realm_system.try_advance_stage(self.game_session)
            if stage_delta is None:
                break
            self.game_session.apply_delta(stage_delta)
            new_stage = stage_delta.get("meta", {}).get("new_stage", 0)
            max_stage = stage_delta.get("meta", {}).get("max_stage", 0)
            self._emit("on_info", f"修为精进！{self.game_session.realm}第{new_stage}层（{new_stage}/{max_stage}）")

        # Step 3.6: Nudge players who keep meditating at max layer — pure
        # cultivation alone cannot break through; they need 感悟 from real deeds.
        self._maybe_emit_insight_hint(is_cultivation)

        # Step 4: Handle combat state changes.
        if combat_delta_seen:
            self._handle_combat_start_or_update(combat_delta)

        # Step 5: Check game over.
        if self._check_game_over():
            return

        # Step 6: Record turn.
        self.game_session.turn_history.append({
            "turn": self.game_session.turn_count,
            "input": text,
            "narrative": narrative,
            "delta": state_delta,
            "choices": self.game_session.last_choices,
        })
        self.game_session.chat_history.append({"role": "user", "content": text})
        self.game_session.chat_history.append({"role": "assistant", "content": narrative})
        if len(self.game_session.chat_history) > 20:
            self.game_session.chat_history = self.game_session.chat_history[-20:]

        # Step 7: Emit events.
        if narrative:
            self._emit("on_narrative", narrative, self.game_session.turn_count)

        self._emit("on_status_bar", format_status_bar(self.game_session))

        # Step 8: Auto-save.
        self._auto_save()

        # Final game over check after all updates.
        if self.game_session.game_over:
            self._emit("on_game_over", self.game_session.error or "游戏结束。")

    # ─── Combat handling ──────────────────────────────────────────────

    def handle_combat_action(self, action: str, target: str = "") -> None:
        """Process a player combat action.

        Called when player text is recognized as a structured combat move.
        """
        combat = self.game_session.combat
        if combat is None:
            self._emit("on_info", "当前不在战斗中。")
            return

        try:
            # Player action.
            combat = self.combat_engine.player_action(combat, action, target)
            self.game_session.combat = combat

            # Check if combat ended after player action (victory/fled).
            if combat.get("phase") in ("victory", "idle") or combat.get("result") in ("victory", "fled"):
                self._resolve_combat()
                return

            # Enemy turn.
            combat = self.combat_engine.enemy_turn(combat)
            self.game_session.combat = combat

            # Check if player died.
            if combat.get("phase") == "defeat" or combat.get("result") == "defeat":
                self._resolve_combat()
                return

            # Combat continues — notify UI.
            self._emit("on_combat_update", combat)
            self._emit("on_status_bar", format_status_bar(self.game_session))

        except Exception:
            log.exception("Combat error")
            # Reset combat state on error.
            self.game_session.combat = None
            self._emit("on_error", "战斗异常，已退出战斗状态。")
            self._emit("on_combat_update", None)

    def _parse_breakthrough_action(self, text: str) -> bool:
        """Detect natural-language breakthrough intent.

        Allows players to type "突破", "尝试突破", "冲击筑基",
        "准备渡劫飞升", etc. instead of relying on a command syntax.
        """
        if self.game_session.combat:
            return False  # can't attempt breakthrough during combat

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
        """Map A/B/C or 1/2/3 input to the current model choice.

        D is the free-input branch. ``D: xxx``/``D.xxx`` submit only ``xxx``;
        plain text is already free input and returns ``None``.
        """
        raw = text.strip()
        if not raw:
            return None

        normalized = raw.upper().replace("．", ".").replace("：", ":")
        choices = normalize_choices(self.game_session.last_choices)

        key = normalized.rstrip(".:、)） ").strip()
        mapping = {"A": 0, "B": 1, "C": 2, "1": 0, "2": 1, "3": 2}
        if key in mapping:
            index = mapping[key]
            return choices[index] if index < len(choices) else None

        for prefix in ("D:", "D.", "D、", "4:", "4.", "4、"):
            if normalized.startswith(prefix):
                return raw[len(prefix):].strip()

        return None

    def _is_pure_cultivation(self, text: str) -> bool:
        """Return True if the typed action is pure meditation/cultivation."""
        return is_pure_cultivation(text)

    def _apply_insight_rule(self, text: str, delta: dict[str, Any]) -> dict[str, Any]:
        """Enforce the 感悟 gate on an action's state delta."""
        return apply_insight_rule(text, delta)

    def _apply_cultivation_limit(self, delta: dict[str, Any], is_cultivation: bool) -> dict[str, Any]:
        """Cap pure-cultivation XP so one meditation turn cannot skip the journey."""
        return apply_cultivation_limit(
            delta,
            is_cultivation=is_cultivation,
            session=self.game_session,
            realm_system=self.realm_system,
        )

    def _apply_breakthrough_flag_rule(
        self,
        text: str,
        delta: dict[str, Any],
        is_cultivation: bool,
    ) -> dict[str, Any]:
        """Let meaningful deeds earn lightweight breakthrough preparation flags."""
        return apply_breakthrough_flag_rule(
            text,
            delta,
            is_cultivation=is_cultivation,
            session=self.game_session,
        )

    def _maybe_emit_insight_hint(self, is_cultivation: bool) -> None:
        """Nudge the player when stuck at max layer — only after pure cultivation."""
        if not is_cultivation:
            return
        cfg = self.realm_system.get_realm_config(self.game_session.realm)
        if cfg is None:
            return
        if self.game_session.realm_stage < cfg.stages:
            return  # still has layers to gain via cultivation
        insight = self.game_session.insight
        if insight >= cfg.insight_required:
            can, reason = self.realm_system.can_attempt_breakthrough(self.game_session)
            if can:
                self._emit("on_info", "修为圆满、感悟通透，可尝试突破。")
            else:
                self._emit("on_info", reason)
        else:
            self._emit(
                "on_info",
                f"修为已满，然闭门造车难以寸进。需外出历练、参悟机缘，"
                f"积累感悟（{insight}/{cfg.insight_required}）方可突破。",
            )

    def _parse_typed_combat_action(self, text: str) -> tuple[str, str] | None:
        """Map natural-language combat input onto the structured combat engine.

        The mobile UI is input-first: a player can type "攻击", "防御",
        "施展火球术", "使用回春丹" or "逃跑" instead of pressing combat
        buttons. Inputs that are not clearly combat commands stay on the LLM
        narrator path so the player can still observe, negotiate, feint, etc.
        """
        combat = self.game_session.combat
        if not combat:
            return None

        raw = text.strip()
        if not raw:
            return None
        compact = "".join(raw.lower().split())

        if any(word in compact for word in ("逃跑", "逃走", "撤退", "脱身", "遁走", "离开战斗")):
            return "flee", ""

        if any(word in compact for word in ("服用", "吞服", "使用丹药", "用药", "吃药")):
            return "item", self._extract_named_combat_target(raw, "consumables", ("服用", "吞服", "使用", "用", "吃"))

        if any(word in compact for word in ("防御", "格挡", "护体", "闪避", "躲避", "防守", "守住")):
            return "defend", ""

        if any(word in compact for word in ("施展", "催动", "运转", "功法", "法术", "术法", "剑诀")):
            return "technique", self._extract_named_combat_target(raw, "techniques", ("施展", "催动", "运转", "使用"))

        if any(word in compact for word in ("攻击", "普攻", "进攻", "挥剑", "出剑", "斩", "刺", "劈", "砍")):
            return "attack", ""

        return None

    def _extract_named_combat_target(
        self,
        text: str,
        collection_key: str,
        verbs: tuple[str, ...],
    ) -> str:
        """Return a named technique/item if the typed text mentions one."""
        combat = self.game_session.combat or {}
        player = combat.get("player", {})
        for item in player.get(collection_key, []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            if name and name in text:
                return name

        target = text.strip()
        for verb in verbs:
            target = target.replace(verb, "")
        for filler in ("我", "你", "向", "对", "朝", "敌人", "妖兽", "一下"):
            target = target.replace(filler, "")
        return target.strip()

    def _handle_combat_start_or_update(self, combat_delta: Any) -> None:
        """Process combat state changes from narrator delta."""
        if combat_delta is None or combat_delta == {}:
            self.game_session.combat = None
            self._emit("on_combat_update", None)
            return

        if isinstance(combat_delta, dict):
            current = self.game_session.combat

            if current is None or current.get("phase") == "idle":
                # New combat — initialize.
                if combat_delta.get("enemy"):
                    enemy_data = combat_delta["enemy"]
                    combat_state = self.combat_engine.start_combat(
                        self.game_session, enemy_data
                    )
                    self.game_session.combat = combat_state
                    self._emit("on_combat_update", combat_state)
                    self._emit("on_info", format_combat(self.game_session))
                else:
                    # Merge partial combat delta.
                    self.game_session.combat = combat_delta
                    self._emit("on_combat_update", combat_delta)
            else:
                # Update existing combat.
                current.update(combat_delta)
                self.game_session.combat = current
                self._emit("on_combat_update", current)

    def _resolve_combat(self) -> None:
        """Resolve the current combat and apply results."""
        combat = self.game_session.combat
        if combat is None:
            return

        delta = self.combat_engine.resolve(combat)
        self.game_session.apply_delta(delta)
        self.game_session.combat = None

        # Notify UI.
        self._emit("on_combat_update", None)

        result = combat.get("result", "")
        if result == "victory":
            exp = delta.get("meta", {}).get("exp_gained", 0)
            gold = delta.get("meta", {}).get("gold_gained", 0)
            self._emit("on_info", f"战斗胜利！获得 {exp} 经验，{gold} 灵石。")
        elif result == "defeat":
            self._emit("on_game_over", self.game_session.error or "战斗失败，修真之路就此终结。")
        elif result == "fled":
            self._emit("on_info", "成功逃离战斗。")

        self._emit("on_narrative", combat.get("narrative", ""), self.game_session.turn_count)
        self._emit("on_status_bar", format_status_bar(self.game_session))
        self._auto_save()

    # ─── Breakthrough ─────────────────────────────────────────────────

    def attempt_breakthrough(self) -> None:
        """Attempt a realm breakthrough."""
        if not self.game_session.game_started:
            self._emit("on_info", "尚未开始游戏。")
            return

        if self.game_session.game_over:
            self._emit("on_info", "游戏已结束。")
            return

        can, reason = self.realm_system.can_attempt_breakthrough(self.game_session)
        if not can:
            self._emit("on_info", reason)
            return

        rate = self.realm_system.calculate_breakthrough_rate(self.game_session)
        self._emit("on_info", f"突破概率: {rate:.0%}，开始突破...")

        self._emit("on_loading", "突破中...")

        # Use narrator to describe the breakthrough process.
        action_text = f"尝试从{self.game_session.realm}突破到更高境界"
        try:
            result = run_turn_sync(
                "narrator", action_text, self.game_session,
                stream_callback=self._stream_callback if self.on_stream_chunk else None,
            )
        except Exception:
            log.exception("breakthrough narrator error")
            reason = "突破叙事失败"
            self._emit("on_error", reason)
            self._set_choices(
                None,
                source="breakthrough_narrator_exception",
                fallback_notice=True,
                require_choice=True,
                reason=reason,
            )
            return

        if result.get("llm_error"):
            reason = f"突破叙事失败: {result['llm_error']}"
            self._emit("on_error", reason)
            self._set_choices(
                None,
                source="breakthrough_narrator_error",
                fallback_notice=True,
                require_choice=True,
                reason=reason,
            )
            return

        narrative = result.get("narrative", "")
        state_delta = result.get("state_delta", {})
        if self._set_choices(
            result.get("choices"),
            source="breakthrough_narrator",
            fallback_notice=True,
            require_choice=True,
            reason="突破叙事未返回可用选项。",
        ) is False and self.game_session.game_over:
            return

        # Apply realm system breakthrough logic.
        breakthrough_delta = self.realm_system.attempt_breakthrough(self.game_session)
        bt_result = breakthrough_delta.get("meta", {}).get("breakthrough_result", "")

        # Merge breakthrough delta into narrator delta.
        if bt_result == "success":
            # Override realm change from realm system (authoritative).
            if "character" not in state_delta:
                state_delta["character"] = {}
            state_delta["character"].update(breakthrough_delta.get("character", {}))
            state_delta.setdefault("meta", {}).update(breakthrough_delta.get("meta", {}))
        elif bt_result == "failure":
            if "character" not in state_delta:
                state_delta["character"] = {}
            state_delta["character"].update(breakthrough_delta.get("character", {}))
            state_delta.setdefault("meta", {}).update(breakthrough_delta.get("meta", {}))

        # Run judge on the combined delta.
        if state_delta:
            try:
                judge_result = run_turn_sync(
                    "judge", action_text, self.game_session,
                    narrative=narrative,
                    state_delta=state_delta,
                )
                if judge_result.get("llm_error"):
                    reason = f"突破审判失败: {judge_result['llm_error']}"
                    if not self._confirm_local_fallback("breakthrough_judge_error", reason):
                        self._end_model_failure_run(reason)
                        return
                    judge_result = {"approved": False, "corrected_delta": {}}
                if judge_result.get("approved") is False:
                    corrected = judge_result.get("corrected_delta", {})
                    if corrected:
                        state_delta = corrected
            except Exception:
                log.exception("breakthrough judge error")
                reason = "突破审判失败（详见日志）"
                if not self._confirm_local_fallback("breakthrough_judge_exception", reason):
                    self._end_model_failure_run(reason)
                    return

        self.game_session.apply_delta(state_delta)

        # Detect ascension finale (飞升).
        is_finale = self.game_session.finale

        if bt_result == "success":
            if is_finale:
                # Epic ending narrative for ascension.
                self._emit("on_narrative",
                           narrative or "天地轰鸣，金光万丈！你超脱凡尘，飞升成仙！",
                           self.game_session.turn_count)
                self._emit("on_finale", "飞升成仙，超脱凡尘，修真之路圆满。")
            else:
                self._emit("on_narrative", narrative or "突破成功！天地灵气涌动，境界提升！", self.game_session.turn_count)
                self._emit("on_info", format_realm(self.game_session))
        elif bt_result == "failure":
            self._emit("on_narrative", narrative or "突破失败...修为受损。", self.game_session.turn_count)
            self._emit("on_info", "突破失败，受到反噬。")
        else:
            self._emit("on_narrative", narrative, self.game_session.turn_count)

        self._emit("on_status_bar", format_status_bar(self.game_session))
        self._auto_save()

        if is_finale:
            return

        if self._check_game_over():
            return

    # ─── Game over check ─────────────────────────────────────────────

    def _check_game_over(self) -> bool:
        """Check for game-over conditions (HP ≤ 0, explicit flag).

        Returns True if game is over.
        """
        if self.game_session.game_over:
            if self.game_session.finale:
                self._emit("on_finale", self.game_session.error or "飞升成仙，修真之路圆满。")
                return True
            self._emit("on_game_over", self.game_session.error or "游戏结束。")
            return True

        if self.game_session.hp <= 0 and self.game_session.game_started:
            self.game_session.game_over = True
            self.game_session.hp = 0
            self.game_session.error = "生命值归零，修真之路就此终结。"
            self._emit("on_game_over", self.game_session.error)
            return True

        return False

    # ─── Save/Load ────────────────────────────────────────────────────

    def save(self, name: str = "autosave") -> None:
        """Save current game."""
        if not self.game_session.game_started:
            self._emit("on_info", "没有进行中的游戏。")
            return
        name = name.strip() or "autosave"
        try:
            save_game(self.game_session, name)
            self._emit("on_info", f"进度已保存: {name}")
        except Exception as e:
            self._emit("on_error", f"保存失败: {e}")

    def load(self, name: str = "autosave") -> None:
        """Load a saved game."""
        name = name.strip() or "autosave"
        try:
            loaded = load_game(name)
            if loaded is None:
                self._emit("on_info", f"存档已损坏，无法加载: {name}")
                return
            self.game_session = loaded
            self._emit("on_info", f"已加载存档: {name}")
            self._emit("on_status_bar", format_status_bar(self.game_session))
            # If combat was active, notify UI.
            if self.game_session.combat:
                self._emit("on_combat_update", self.game_session.combat)
        except FileNotFoundError as e:
            self._emit("on_info", str(e))
        except Exception as e:
            self._emit("on_error", f"加载失败: {e}")

    def reset(self) -> None:
        """Reset the game session."""
        self.game_session.reset()
        self._emit("on_info", "游戏已重置。请返回角色创建重新开始。")
        self._emit("on_combat_update", None)

    # ─── Multi-slot save management ──────────────────────────────────

    def list_saves(self) -> list[dict[str, Any]]:
        """Return a list of available saves with metadata."""
        return list_saves()

    def delete_save(self, name: str) -> None:
        """Delete a save file."""
        try:
            delete_save(name)
            self._emit("on_info", f"已删除存档: {name}")
        except FileNotFoundError:
            self._emit("on_info", f"存档不存在: {name}")
        except Exception as e:
            self._emit("on_error", f"删除失败: {e}")

    def rename_save(self, old_name: str, new_name: str) -> None:
        """Rename a save file."""
        try:
            rename_save(old_name, new_name)
            self._emit("on_info", f"已重命名存档: {old_name} → {new_name}")
        except Exception as e:
            self._emit("on_error", f"重命名失败: {e}")

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

    def _auto_save(self) -> None:
        """Auto-save if game is active."""
        if self.game_session.game_started:
            try:
                save_game(self.game_session, "autosave")
            except Exception:
                log.warning("Auto-save failed", exc_info=True)

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

    def _sanitize_action_delta(self, delta: dict[str, Any]) -> dict[str, Any]:
        """Drop ordinary-turn updates that reset character identity or continuity.

        LLM output is intentionally high variance, but mobile free actions must
        not re-open the world or replace the player's established profile.
        Breakthroughs and combat resolution use dedicated engine paths.
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
                "luck",
                "difficulty",
                "game_mode",
                "attributes",
                "inventory",
                "techniques",
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


_luck_from_attributes = luck_from_attributes
_profile_opening = profile_opening
_profile_concept = profile_concept
