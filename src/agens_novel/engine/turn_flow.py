"""Turn-flow orchestration for GameEngine."""

from __future__ import annotations

import logging
from typing import Any

from .action_delta_policy import (
    PLAYER_NARRATIVE_MISMATCH_NOTICE,
    apply_breakthrough_flag_rule,
    is_pure_cultivation,
    merge_rule_delta,
    validate_narrative_delta_consistency,
)
from .choices import fallback_choices, normalize_choices
from .model_result import (
    ModelResultKind,
    classify_judge_result,
    classify_narrator_result,
)
from .render import format_realm, format_status_bar
from .turn_rules import settle_turn

log = logging.getLogger(__name__)


class TurnFlow:
    """Owns ordinary and local-story turn progression for ``GameEngine``."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def handle_local_story_action(self, text: str) -> None:
        """Process one turn in the local preset story fallback."""
        engine = self.engine
        session = engine.game_session
        from .local_story import advance_local_story

        result = advance_local_story(session, text)
        session.last_choices = result.choices

        if not result.matched:
            engine._emit("on_info", result.narrative)
            engine._emit("on_status_bar", format_status_bar(session))
            return

        session.turn_count += 1

        if result.delta:
            session.apply_delta(result.delta)
            stage_delta = self._try_emit_stage_advance()
            if stage_delta is not None:
                result_delta = self._merge_state_delta(result.delta, stage_delta)
            else:
                result_delta = result.delta
        else:
            result_delta = result.delta

        if result.breakthrough:
            breakthrough_delta = engine._attempt_local_story_breakthrough()
            if breakthrough_delta:
                result_delta = self._merge_state_delta(result_delta, breakthrough_delta)

        if result.narrative:
            engine._emit("on_narrative", result.narrative, session.turn_count)

        session.turn_history.append({
            "turn": session.turn_count,
            "input": text,
            "narrative": result.narrative,
            "delta": result_delta,
            "choices": session.last_choices,
            "local_story": {
                "story_id": session.local_story_id,
                "node_id": session.local_story_node_id,
            },
        })
        engine._emit("on_status_bar", format_status_bar(session))

        if engine._check_game_over():
            return

    def handle_action(self, text: str) -> None:
        """Process one ordinary player action through rules, narrator and judge."""
        engine = self.engine
        session = engine.game_session
        session.turn_count += 1

        engine._emit("on_loading", "天道运转中...")

        rule_delta = settle_turn(text, session)
        turn_summary = (
            rule_delta.get("meta", {}).get("turn_summary", "")
            if isinstance(rule_delta.get("meta"), dict) else ""
        )

        narrator_result = self._run_narrator(text, turn_summary)
        if narrator_result is None:
            session.turn_count -= 1
            return

        narrator_status = classify_narrator_result(narrator_result)
        engine._log_model_result(
            agent="narrator",
            source="turn",
            status=narrator_status.kind,
            reason=narrator_status.reason,
            result=narrator_result,
        )
        if narrator_status.kind == ModelResultKind.REQUEST_FAILED:
            reason = narrator_status.reason
            engine._emit("on_error", reason)
            engine._set_choices(
                None,
                source="narrator_error",
                fallback_notice=True,
                require_choice=True,
                reason=reason,
            )
            session.turn_count -= 1
            return

        narrative = narrator_result.get("narrative", "")
        raw_state_delta = narrator_result.get("state_delta", {})
        malformed_state_delta = raw_state_delta is None or not isinstance(raw_state_delta, dict)
        state_delta = raw_state_delta if isinstance(raw_state_delta, dict) else {}
        choices = narrator_result.get("choices", [])
        meta_delta = state_delta.get("meta") if isinstance(state_delta, dict) else {}
        is_terminal_delta = isinstance(meta_delta, dict) and bool(
            meta_delta.get("game_over") or meta_delta.get("finale")
        )
        if narrator_status.kind == ModelResultKind.INCOMPLETE_OUTPUT:
            recovered_choices = [] if malformed_state_delta else self._recover_incomplete_narrator_choices(narrative, choices)
            if recovered_choices:
                choices = recovered_choices
                engine._emit("on_info", "叙事模型选项格式不完整，已按本回合局面补齐下一步选择。")
            else:
                choices = []
                engine._emit("on_info", narrator_status.reason)
        if is_terminal_delta:
            session.last_choices = []
        else:
            fallback_used = engine._set_choices(
                choices,
                source="narrator",
                fallback_notice=True,
                require_choice=True,
                reason=narrator_status.reason if narrator_status.kind == ModelResultKind.INCOMPLETE_OUTPUT else "叙事模型未返回可用选项。",
                emit_local_story_narrative=True,
            )
            if fallback_used:
                self._record_local_story_fallback_turn(
                    text,
                    rule_delta,
                    reason=narrator_status.reason,
                )
                engine._emit("on_status_bar", format_status_bar(session))
                return
            if session.game_over:
                session.turn_count -= 1
                return

        judge_result = self._run_judge_if_needed(text, narrative, state_delta, rule_delta)
        if judge_result is None and session.game_over:
            return
        if isinstance(judge_result, dict):
            narrative, state_delta = self._apply_judge_result(narrative, state_delta, judge_result)

        applied = self._validate_and_apply_delta(text, narrative, state_delta, rule_delta)
        if applied is None:
            return
        narrative, applied_delta = applied

        self._record_and_emit_turn(text, narrative, applied_delta)

        if session.game_over:
            engine._emit("on_game_over", session.error or "游戏结束。")

    def _run_narrator(self, text: str, turn_summary: str) -> dict[str, Any] | None:
        engine = self.engine
        session = engine.game_session
        narrator_input = text
        if turn_summary:
            narrator_input = f"{text}\n\n[本回合规则结算结果（以此为权威数值）：{turn_summary}]"

        # The model chronically emits narrative without <state_update>/<choices>
        # tags; without repair that forces a local-story fallback. The narrator's
        # focused repair pass recovers the tags on a second call (repaired_output
        # is recorded in diagnostics), turning fallback into genuine model success.
        try:
            return engine._run_agent(
                "narrator",
                narrator_input,
                session,
                stream_callback=engine._stream_callback if engine.on_stream_chunk else None,
                repair_incomplete_output=True,
            )
        except Exception:
            log.exception("narrator error")
            reason = "叙述失败（详见日志）"
            engine._emit("on_error", reason)
            engine._set_choices(
                None,
                source="narrator_exception",
                fallback_notice=True,
                require_choice=True,
                reason=reason,
            )
            return None

    def _run_judge_if_needed(
        self,
        text: str,
        narrative: str,
        state_delta: dict[str, Any],
        rule_delta: dict[str, Any],
    ) -> tuple[str, dict[str, Any]] | None:
        engine = self.engine
        session = engine.game_session
        if not state_delta or not engine._should_run_judge(text, state_delta, rule_delta):
            return {}

        engine._emit("on_loading", "天道审判中...")
        try:
            judge_result = engine._run_agent(
                "judge",
                text,
                session,
                narrative=narrative,
                state_delta=state_delta,
            )
        except Exception:
            log.exception("judge error")
            reason = "天道审判失败（详见日志）"
            if not engine._confirm_local_fallback("judge_exception", reason):
                session.turn_count -= 1
                engine._end_model_failure_run(reason)
                return None
            judge_result = {"approved": False, "corrected_delta": {}, "judgment_note": reason}

        judge_status = classify_judge_result(judge_result)
        engine._log_model_result(
            agent="judge",
            source="turn",
            status=judge_status.kind,
            reason=judge_status.reason,
            result=judge_result,
        )
        if judge_status.kind == ModelResultKind.JUDGE_FAILED:
            reason = judge_status.reason
            if not engine._confirm_local_fallback("judge_error", reason):
                session.turn_count -= 1
                engine._end_model_failure_run(reason)
                return None
            judge_result = {"approved": False, "corrected_delta": {}, "judgment_note": reason}

        return judge_result

    def _apply_judge_result(
        self,
        narrative: str,
        state_delta: dict[str, Any],
        judge_result: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        engine = self.engine
        if judge_result.get("approved") is False:
            corrected = judge_result.get("corrected_delta", {})
            if corrected:
                state_delta = corrected
            else:
                note = judge_result.get("judgment_note", "")
                log.info("Judge rejected (no corrected delta): %s", note)
                engine._emit("on_info", "本回合以基础规则结算，模型状态变更未采用。")
                narrative = ""
                state_delta = {"character": {}, "world": {}, "meta": {}}
            note = judge_result.get("judgment_note", "")
            if note:
                log.info("Judge corrected: %s", note)
        return narrative, state_delta

    def _validate_and_apply_delta(
        self,
        text: str,
        narrative: str,
        state_delta: dict[str, Any],
        rule_delta: dict[str, Any],
    ) -> tuple[str, dict[str, Any]] | None:
        engine = self.engine
        session = engine.game_session
        consistent, consistency_reason = validate_narrative_delta_consistency(
            narrative,
            state_delta,
        )
        if not consistent:
            log.info("Narrative/state mismatch rejected: %s", consistency_reason)
            engine._emit("on_info", PLAYER_NARRATIVE_MISMATCH_NOTICE)
            narrative = ""
            state_delta = {"character": {}, "world": {}, "meta": {}}
            session.last_choices = fallback_choices(session)

        state_delta = engine._sanitize_action_delta(state_delta)

        is_cultivation = is_pure_cultivation(text)
        state_delta = apply_breakthrough_flag_rule(
            text, state_delta, is_cultivation=is_cultivation, session=session
        )

        char_delta = state_delta.get("character")
        if isinstance(char_delta, dict) and "combat" in char_delta:
            char_delta = dict(char_delta)
            char_delta.pop("combat", None)
            state_delta = {**state_delta, "character": char_delta}

        state_delta = merge_rule_delta(state_delta, rule_delta)
        session.apply_delta(state_delta)
        stage_delta = self._try_emit_stage_advance()
        if stage_delta is not None:
            state_delta = self._merge_state_delta(state_delta, stage_delta)

        if engine._check_game_over():
            return None

        return narrative, state_delta

    def _record_local_story_fallback_turn(
        self,
        text: str,
        rule_delta: dict[str, Any],
        *,
        reason: str,
    ) -> None:
        session = self.engine.game_session
        narrative = "模型叙事不完整，本回合已切换为本地故事继续。"
        fallback_meta = {
            "elapsed_years": 0,
            "calendar_summary": "模型输出不完整，转入本地故事。",
            "choice_category": "fallback",
            "local_story_fallback": True,
            "fallback_reason": reason,
        }
        state_delta = {
            "character": {},
            "world": {},
            "meta": fallback_meta,
        }
        session.turn_history.append({
            "turn": session.turn_count,
            "input": text,
            "narrative": narrative,
            "delta": state_delta,
            "choices": session.last_choices,
            "local_story": {
                "story_id": session.local_story_id,
                "node_id": session.local_story_node_id,
            },
        })
        session.chat_history.append({"role": "user", "content": text})
        session.chat_history.append({"role": "assistant", "content": narrative})
        if len(session.chat_history) > 20:
            session.chat_history = session.chat_history[-20:]

    def _record_and_emit_turn(
        self,
        text: str,
        narrative: str,
        state_delta: dict[str, Any],
    ) -> None:
        engine = self.engine
        session = engine.game_session
        session.turn_history.append({
            "turn": session.turn_count,
            "input": text,
            "narrative": narrative,
            "delta": state_delta,
            "choices": session.last_choices,
        })
        session.chat_history.append({"role": "user", "content": text})
        session.chat_history.append({"role": "assistant", "content": narrative})
        if len(session.chat_history) > 20:
            session.chat_history = session.chat_history[-20:]

        if narrative:
            engine._emit("on_narrative", narrative, session.turn_count)

        engine._emit("on_status_bar", format_status_bar(session))

    def _try_emit_stage_advance(self) -> dict[str, Any] | None:
        engine = self.engine
        session = engine.game_session
        stage_delta = engine.realm_system.try_advance_stage(session)
        if stage_delta is not None:
            session.apply_delta(stage_delta)
            new_stage = stage_delta.get("meta", {}).get("new_stage", 0)
            max_stage = stage_delta.get("meta", {}).get("max_stage", 0)
            engine._emit("on_info", f"修为精进！{session.realm}第{new_stage}层（{new_stage}/{max_stage}）")
            return stage_delta
        return None

    @staticmethod
    def _merge_state_delta(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base) if isinstance(base, dict) else {}
        for section, value in extra.items():
            if isinstance(value, dict) and isinstance(merged.get(section), dict):
                section_delta = dict(merged[section])
                section_delta.update(value)
                merged[section] = section_delta
            else:
                merged[section] = value
        return merged

    def _recover_incomplete_narrator_choices(self, narrative: str, choices: Any) -> list[str]:
        """Use semantic local choices only when the live narrator produced narrative."""
        if not str(narrative or "").strip():
            return []
        session = self.engine.game_session
        recovered = normalize_choices(choices)
        if recovered:
            fallbacks = fallback_choices(session)
            while len(recovered) < len(fallbacks):
                recovered.append(fallbacks[len(recovered)])
            return recovered[:len(fallbacks)]
        return fallback_choices(session)
