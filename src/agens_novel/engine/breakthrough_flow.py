"""Breakthrough-flow orchestration for GameEngine."""

from __future__ import annotations

import logging
import re
from typing import Any

from .render import format_realm, format_status_bar

log = logging.getLogger(__name__)
_BREAKTHROUGH_FAILURE_WORDS = ("修为尽废", "修为未复", "重伤垂死", "未能突破", "突破失败", "功亏一篑")
_BREAKTHROUGH_SUCCESS_WORDS = ("突破成功", "功成", "踏入", "晋入", "进阶", "破境已成")


class BreakthroughFlow:
    """Owns realm breakthrough progression for ``GameEngine``."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def attempt_breakthrough(self) -> None:
        """Attempt a realm breakthrough while preserving GameEngine callbacks."""
        engine = self.engine
        session = engine.game_session

        if not session.game_started:
            engine._emit("on_info", "尚未开始游戏。")
            return

        if session.game_over:
            engine._emit("on_info", "游戏已结束。")
            return

        can, reason = engine.realm_system.can_attempt_breakthrough(session)
        if not can:
            engine._emit("on_info", reason)
            return

        rate = engine.realm_system.calculate_breakthrough_rate(session)
        engine._emit("on_info", f"突破概率: {rate:.0%}，开始突破...")

        engine._emit("on_loading", "突破中...")

        breakthrough_delta = engine.realm_system.attempt_breakthrough(session)
        bt_result = breakthrough_delta.get("meta", {}).get("breakthrough_result", "")
        action_text = self._breakthrough_action_text(breakthrough_delta)
        result = self._run_breakthrough_narrator(action_text)
        narrative = ""
        state_delta: dict[str, Any] = breakthrough_delta
        choices: Any = []
        if result is None:
            state_delta = breakthrough_delta
        elif result.get("llm_error"):
            log.info("breakthrough narrator unavailable after rule settlement: %s", result.get("llm_error"))
            state_delta = breakthrough_delta
        else:
            narrative = str(result.get("narrative") or "")
            raw_delta = result.get("state_delta", {})
            state_delta = raw_delta if isinstance(raw_delta, dict) else {}
            choices = result.get("choices")
            state_delta = self._merge_breakthrough_delta(state_delta, breakthrough_delta, bt_result)

        state_delta = self._judge_breakthrough_delta(action_text, narrative, state_delta)
        if state_delta is None:
            return

        session.turn_count += 1
        self._ensure_breakthrough_meta(state_delta, bt_result)
        session.apply_delta(state_delta)
        narrative = self._coerce_breakthrough_narrative(narrative, bt_result)
        if engine._set_choices(
            choices,
            source="breakthrough_narrator",
            fallback_notice=False,
            require_choice=False,
            reason="突破叙事未返回可用选项。",
        ) is False and session.game_over:
            return

        is_finale = session.finale
        self._record_breakthrough_turn(action_text, narrative, state_delta)
        self._emit_breakthrough_result(bt_result, narrative, is_finale)

        engine._emit("on_status_bar", format_status_bar(session))

        if is_finale:
            return

        if engine._check_game_over():
            return

    def _run_breakthrough_narrator(self, action_text: str) -> dict[str, Any] | None:
        engine = self.engine
        try:
            return engine._run_agent(
                "narrator",
                action_text,
                engine.game_session,
                stream_callback=engine._stream_callback if engine.on_stream_chunk else None,
                repair_incomplete_output=True,
            )
        except Exception:
            log.exception("breakthrough narrator error")
            return {"narrative": "", "state_delta": {}, "choices": [], "llm_error": "突破叙事失败"}

    def _merge_breakthrough_delta(
        self,
        state_delta: dict[str, Any],
        breakthrough_delta: dict[str, Any],
        bt_result: str,
    ) -> dict[str, Any]:
        if bt_result not in {"success", "failure"}:
            return state_delta
        if "character" not in state_delta:
            state_delta["character"] = {}
        if bt_result == "failure" and isinstance(state_delta.get("character"), dict):
            state_delta["character"].pop("realm", None)
            state_delta["character"].pop("realm_stage", None)
        state_delta["character"].update(breakthrough_delta.get("character", {}))
        state_delta.setdefault("meta", {}).update(breakthrough_delta.get("meta", {}))
        return state_delta

    def _breakthrough_action_text(self, breakthrough_delta: dict[str, Any]) -> str:
        session = self.engine.game_session
        meta = breakthrough_delta.get("meta") if isinstance(breakthrough_delta.get("meta"), dict) else {}
        result = str(meta.get("breakthrough_result") or "")
        target = str(meta.get("new_realm") or self.engine.realm_system.get_next_realm(session.realm) or "更高境界")
        if result == "success":
            return f"规则判定：本次突破成功，从{session.realm}突破至{target}。请只写成功叙事。"
        if result == "failure":
            effect = str(meta.get("status_effect_add") or "走火入魔")
            return f"规则判定：本次突破失败，反噬结果为{effect}。请只写失败叙事，不得提升境界。"
        return f"尝试从{session.realm}突破到更高境界"

    def _coerce_breakthrough_narrative(self, narrative: str, bt_result: str) -> str:
        text = re.sub(r"\s+", " ", str(narrative or "")).strip()
        if bt_result == "success":
            if not text or any(word in text for word in _BREAKTHROUGH_FAILURE_WORDS):
                return "破境已成，灵机贯通，境界向前推进。"
        elif bt_result == "failure":
            if not text or any(word in text for word in _BREAKTHROUGH_SUCCESS_WORDS):
                return "破境未成，灵机反噬，需先稳住根基再图后续。"
        return text

    def _ensure_breakthrough_meta(self, state_delta: dict[str, Any], bt_result: str) -> None:
        meta = state_delta.setdefault("meta", {})
        if not isinstance(meta, dict):
            meta = {}
            state_delta["meta"] = meta
        meta.setdefault("elapsed_years", 0)
        meta.setdefault("choice_category", "breakthrough")
        if bt_result:
            meta.setdefault("breakthrough_result", bt_result)
        if bt_result == "success":
            meta.setdefault("calendar_summary", "破境成功，境界向前推进。")
        elif bt_result == "failure":
            meta.setdefault("calendar_summary", "破境失败，本回合以反噬结果结算。")
        else:
            meta.setdefault("calendar_summary", "完成一次破境判定。")

    def _record_breakthrough_turn(
        self,
        action_text: str,
        narrative: str,
        state_delta: dict[str, Any],
    ) -> None:
        session = self.engine.game_session
        session.record_turn(action_text, narrative, state_delta)

    def _judge_breakthrough_delta(
        self,
        action_text: str,
        narrative: str,
        state_delta: dict[str, Any],
    ) -> dict[str, Any] | None:
        engine = self.engine
        if not state_delta:
            return state_delta

        try:
            judge_result = engine._run_agent(
                "judge",
                action_text,
                engine.game_session,
                narrative=narrative,
                state_delta=state_delta,
            )
            if judge_result.get("llm_error"):
                reason = f"突破审判失败: {judge_result['llm_error']}"
                if not engine._confirm_local_fallback("breakthrough_judge_error", reason):
                    engine._end_model_failure_run(reason)
                    return None
                judge_result = {"approved": False, "corrected_delta": {}}
            if judge_result.get("approved") is False:
                corrected = judge_result.get("corrected_delta", {})
                if corrected and not _conflicts_with_breakthrough_result(corrected, state_delta):
                    state_delta = corrected
        except Exception:
            log.exception("breakthrough judge error")
            reason = "突破审判失败（详见日志）"
            if not engine._confirm_local_fallback("breakthrough_judge_exception", reason):
                engine._end_model_failure_run(reason)
                return None

        return state_delta

    def _emit_breakthrough_result(
        self,
        bt_result: str,
        narrative: str,
        is_finale: bool,
    ) -> None:
        engine = self.engine
        session = engine.game_session
        if bt_result == "success":
            if is_finale:
                engine._emit(
                    "on_narrative",
                    narrative or "天地轰鸣，金光万丈！你超脱凡尘，飞升成仙！",
                    session.turn_count,
                )
                engine._emit("on_finale", "飞升成仙，超脱凡尘，修真之路圆满。")
            else:
                engine._emit(
                    "on_narrative",
                    narrative or "突破成功！天地灵气涌动，境界提升！",
                    session.turn_count,
                )
                engine._emit("on_info", format_realm(session))
        elif bt_result == "failure":
            engine._emit("on_narrative", narrative or "突破失败...修为受损。", session.turn_count)
            engine._emit("on_info", "突破失败，受到反噬。")
        else:
            engine._emit("on_narrative", narrative, session.turn_count)


def _conflicts_with_breakthrough_result(corrected: dict[str, Any], original: dict[str, Any]) -> bool:
    original_meta = original.get("meta") if isinstance(original.get("meta"), dict) else {}
    corrected_meta = corrected.get("meta") if isinstance(corrected.get("meta"), dict) else {}
    original_result = original_meta.get("breakthrough_result")
    if not original_result:
        return False
    if corrected_meta.get("breakthrough_result") != original_result:
        return True

    original_character = original.get("character") if isinstance(original.get("character"), dict) else {}
    corrected_character = corrected.get("character") if isinstance(corrected.get("character"), dict) else {}
    if not isinstance(corrected_character, dict):
        return False
    for key in ("realm", "realm_stage", "lifespan"):
        if key in original_character and corrected_character.get(key) != original_character.get(key):
            return True
    return False
