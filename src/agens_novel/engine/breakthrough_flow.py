"""Breakthrough-flow orchestration for GameEngine."""

from __future__ import annotations

import logging
from typing import Any

from .render import format_realm, format_status_bar

log = logging.getLogger(__name__)


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

        action_text = f"尝试从{session.realm}突破到更高境界"
        result = self._run_breakthrough_narrator(action_text)
        if result is None:
            return

        if result.get("llm_error"):
            reason = f"突破叙事失败: {result['llm_error']}"
            engine._emit("on_error", reason)
            engine._set_choices(
                None,
                source="breakthrough_narrator_error",
                fallback_notice=True,
                require_choice=True,
                reason=reason,
            )
            return

        narrative = result.get("narrative", "")
        state_delta = result.get("state_delta", {})
        if engine._set_choices(
            result.get("choices"),
            source="breakthrough_narrator",
            fallback_notice=True,
            require_choice=True,
            reason="突破叙事未返回可用选项。",
        ) is False and session.game_over:
            return

        breakthrough_delta = engine.realm_system.attempt_breakthrough(session)
        bt_result = breakthrough_delta.get("meta", {}).get("breakthrough_result", "")
        state_delta = self._merge_breakthrough_delta(state_delta, breakthrough_delta, bt_result)

        state_delta = self._judge_breakthrough_delta(action_text, narrative, state_delta)
        if state_delta is None:
            return

        session.apply_delta(state_delta)

        is_finale = session.finale
        self._emit_breakthrough_result(bt_result, narrative, is_finale)

        engine._emit("on_status_bar", format_status_bar(session))
        engine._auto_save()

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
            )
        except Exception:
            log.exception("breakthrough narrator error")
            reason = "突破叙事失败"
            engine._emit("on_error", reason)
            engine._set_choices(
                None,
                source="breakthrough_narrator_exception",
                fallback_notice=True,
                require_choice=True,
                reason=reason,
            )
            return None

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
        state_delta["character"].update(breakthrough_delta.get("character", {}))
        state_delta.setdefault("meta", {}).update(breakthrough_delta.get("meta", {}))
        return state_delta

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
                if corrected:
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
