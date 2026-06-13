"""UI-agnostic game engine for the xianxia cultivation simulator.

Extracts all game logic from ``repl.loop.Repl`` into a class that emits events
via callbacks.  Any UI (terminal Rich, Kivy mobile, web) can register callbacks
and drive the game without knowing about the other layers.

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
from ..repl.game_session import GameSession
from ..repl.save_manager import delete_save, list_saves, load_game, rename_save, save_game
from ..repl.turn_runner import run_turn_sync
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

    # ─── Helper to emit callbacks safely ───────────────────────────────

    def _emit(self, attr: str, *args: Any) -> None:
        cb = getattr(self, attr, None)
        if cb is not None:
            cb(*args)

    def _has_api_key(self) -> bool:
        """Always returns True — built-in key is the fallback."""
        return bool(os.environ.get("AGNES_API_KEY", "")) or True

    # ─── Stream callback wrapper ──────────────────────────────────────

    def _stream_callback(self, text: str) -> None:
        """Forward stream chunks to the UI layer."""
        self._emit("on_stream_chunk", text)

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
            self._emit("on_error", "世界生成失败（详见日志）")
            return

        if result.get("llm_error"):
            self._emit("on_error", f"世界生成失败: {result['llm_error']}")
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
            self.game_session.game_mode = char_data.get("game_mode", self.game_session.game_mode)
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

        self.game_session.last_choices = _default_choices(self.game_session)
        self._emit("on_narrative", opening, 0)
        self._emit("on_character_created", self.game_session)
        self._emit("on_status_bar", format_status_bar(self.game_session))
        self._auto_save()

    def start_from_profile(self, profile: dict[str, Any]) -> None:
        """Create a deterministic mobile game from the character form.

        This keeps the Kivy character-creation screen on the same engine path
        as every other UI operation while avoiding an LLM call before the first
        playable screen is available.
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
        self.game_session.luck = str(profile.get("luck") or _luck_from_attributes(attrs))
        self.game_session.game_mode = str(profile.get("game_mode") or DEFAULT_GAME_MODE)
        self.game_session.attributes = attrs
        self.game_session.hp = int(profile.get("hp") or (999 if special else 100))
        self.game_session.hp_max = int(profile.get("hp_max") or self.game_session.hp)
        self.game_session.mp = int(profile.get("mp") or (999 if special else 50))
        self.game_session.mp_max = int(profile.get("mp_max") or self.game_session.mp)
        self.game_session.gold = int(profile.get("gold") or (9999 if special else 20))
        self.game_session.techniques = list(profile.get("techniques") or [{"name": "基础吐纳术", "level": 1, "type": "内功"}])
        self.game_session.inventory = list(profile.get("inventory") or [{"name": "粗布道袍", "quantity": 1, "type": "防具"}])
        self.game_session.current_scene = str(profile.get("current_scene") or "青玄宗山门")
        self.game_session.location = str(profile.get("location") or "青玄宗山门")
        self.game_session.region = str(profile.get("region") or "东荒")
        self.game_session.discovered_locations = [self.game_session.location]
        self.game_session.lore_facts = ["青玄宗立于东荒云脉之上，山门深处常有灵雾不散。"]

        opening = str(profile.get("opening_narrative") or _profile_opening(self.game_session, special))
        self.game_session.last_choices = _default_choices(self.game_session)
        self._emit("on_narrative", opening, 0)
        self._emit("on_character_created", self.game_session)
        self._emit("on_status_bar", format_status_bar(self.game_session))
        self._auto_save()

    def handle_action(self, text: str) -> None:
        """Process a player action through Narrator + Judge.

        Supports streaming (via on_stream_chunk callback) and combat detection.
        """
        if not self._has_api_key():
            self._emit("on_error", "AGNES_API_KEY 未设置。请先配置 API Key。")
            return

        if not self.game_session.game_started:
            self._emit("on_info", "尚未开始游戏。输入 /new 开始新游戏。")
            return

        if self.game_session.game_over:
            self._emit("on_info", f"游戏已结束: {self.game_session.error}\n输入 /new 开始新游戏，或 /reset 重置。")
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
            self._emit("on_error", "叙述失败（详见日志）")
            self.game_session.turn_count -= 1
            return

        if narrator_result.get("llm_error"):
            self._emit("on_error", f"叙述失败: {narrator_result['llm_error']}")
            self.game_session.turn_count -= 1
            return

        narrative = narrator_result.get("narrative", "")
        state_delta = narrator_result.get("state_delta", {})
        choices = narrator_result.get("choices", [])
        self.game_session.last_choices = choices or _default_choices(self.game_session)

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
                # On judge error, default to NOT approving (safe default).
                judge_result = {"approved": False, "corrected_delta": {}}

            if judge_result.get("approved") is False:
                corrected = judge_result.get("corrected_delta", {})
                if corrected:
                    state_delta = corrected
                else:
                    # Judge rejected and no corrected delta — skip applying.
                    note = judge_result.get("judgment_note", "")
                    log.info("Judge rejected (no corrected delta): %s", note)
                    self._emit("on_info", "天道审判未通过，行动结果暂不生效。")
                    self._emit("on_narrative", narrative, self.game_session.turn_count)
                    self._emit("on_status_bar", format_status_bar(self.game_session))
                    self._auto_save()
                    return
                note = judge_result.get("judgment_note", "")
                if note:
                    log.info("Judge corrected: %s", note)

        # Step 3: Apply delta.
        self.game_session.apply_delta(state_delta)

        # Step 4: Handle combat state changes.
        combat_delta = state_delta.get("character", {}).get("combat")
        if combat_delta is not None:
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

        Called by UI when player taps a combat button (attack/technique/item/defend/flee).
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

    def _handle_combat_start_or_update(self, combat_delta: Any) -> None:
        """Process combat state changes from narrator delta."""
        if combat_delta is None:
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
            self._emit("on_error", "突破叙事失败")
            return

        narrative = result.get("narrative", "")
        state_delta = result.get("state_delta", {})

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
                if judge_result.get("approved") is False:
                    corrected = judge_result.get("corrected_delta", {})
                    if corrected:
                        state_delta = corrected
            except Exception:
                log.exception("breakthrough judge error")

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

        if self._check_game_over():
            return

    # ─── Game over check ─────────────────────────────────────────────

    def _check_game_over(self) -> bool:
        """Check for game-over conditions (HP ≤ 0, explicit flag).

        Returns True if game is over.
        """
        if self.game_session.game_over:
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
            self.game_session = load_game(name)
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
        self._emit("on_info", "游戏已重置。输入 /new 开始新游戏。")
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
            self._emit("on_info", "请先输入 /new 开始游戏。")
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


def _luck_from_attributes(attributes: dict[str, int]) -> str:
    """Map numeric creation luck to a compact display label."""
    value = attributes.get("luck", DEFAULT_ATTRIBUTES["luck"])
    if value >= 90:
        return "天眷"
    if value >= 70:
        return "中上"
    if value >= 45:
        return "平稳"
    if value >= 25:
        return "起伏"
    return "低迷"


def _profile_opening(session: GameSession, special: bool = False) -> str:
    """Opening text for deterministic character creation."""
    if special:
        return (
            "云海倒悬，九峰钟声同时响起。你睁眼时，掌门与诸峰长老已经等在殿外，"
            "无人敢高声言语。一枚无主仙令悬在你掌心，像是早已等了很多年。"
        )
    return (
        f"晨雾漫过{session.location}，{session.char_name or '无名'}踏上山门石阶。"
        f"{session.family_background or '凡俗出身'}的旧事仍在身后，"
        f"{session.spirit_root or '未明灵根'}却已在丹田深处泛起微光。"
    )


def _default_choices(session: GameSession) -> list[str]:
    """Generate grounded fallback choices for UI modes when the LLM omits them."""
    location = session.location or "当前地点"
    if session.combat:
        return ["谨慎防守并观察敌人破绽", "施展最熟悉的功法", "寻找脱身路线"]
    return [
        f"在{location}静心修炼，稳固气息",
        "寻找附近修士交谈，打听消息",
        "检查随身物品与当前状态",
    ]
