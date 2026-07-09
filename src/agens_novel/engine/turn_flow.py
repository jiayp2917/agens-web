"""Turn-flow orchestration for GameEngine."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .game_engine import GameEngine

from .action_delta_policy import (
    apply_breakthrough_flag_rule,
    is_pure_cultivation,
    merge_rule_delta,
    validate_narrative_delta_consistency,
)
from .choices import fallback_choices, normalize_choices
from .choices import clean_visible_text
from .model_result import (
    ModelResultKind,
    classify_judge_result,
    classify_narrator_result,
    is_retryable_model_request_failure,
)
from .render import format_realm, format_status_bar
from .turn_rules import settle_turn

log = logging.getLogger(__name__)


class TurnFlow:
    """Owns ordinary and local-story turn progression for ``GameEngine``."""

    def __init__(self, engine: GameEngine) -> None:
        self.engine = engine

    def handle_local_story_action(self, text: str) -> None:
        """Process one turn in the local preset story fallback."""
        engine = self.engine
        session = engine.game_session
        from .local_story import advance_local_story

        result = advance_local_story(session, text)
        session.last_choices = engine._filter_unavailable_breakthrough_choices(result.choices)

        if not result.matched:
            engine.emit("on_info", result.narrative)
            engine.emit("on_status_bar", format_status_bar(session))
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
            breakthrough_delta = engine.attempt_local_story_breakthrough()
            if breakthrough_delta:
                session.apply_delta(breakthrough_delta)
                self._emit_local_story_breakthrough_result(breakthrough_delta)
                result_delta = self._merge_state_delta(result_delta, breakthrough_delta)

        if result.narrative:
            engine.emit("on_narrative", result.narrative, session.turn_count)

        session.record_turn(
            text,
            result.narrative,
            result_delta,
            local_story={
                "story_id": session.local_story_id,
                "node_id": session.local_story_node_id,
            },
        )
        engine.emit("on_status_bar", format_status_bar(session))

        if engine.check_game_over():
            return

    def handle_action(self, text: str) -> None:
        """Process one ordinary player action through rules, narrator and judge."""
        engine = self.engine
        session = engine.game_session
        session.turn_count += 1

        engine.emit("on_loading", "天道运转中...")

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
        engine.log_model_result(
            agent="narrator",
            source="turn",
            status=narrator_status.kind,
            reason=narrator_status.reason,
            result=narrator_result,
        )
        if narrator_status.kind == ModelResultKind.REQUEST_FAILED:
            reason = narrator_status.reason
            engine.emit("on_error", reason)
            engine.set_choices(
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
        if narrator_status.kind == ModelResultKind.INCOMPLETE_OUTPUT:
            if (
                not str(narrative or "").strip()
                and isinstance(state_delta, dict)
                and _has_nonempty_structured_delta(state_delta)
                and not normalize_choices(choices)
            ):
                log.info("narrator returned JSON-only delta; rejecting model delta and settling by rules")
                narrative = self._narrative_from_rule_delta(rule_delta)
                state_delta = self._empty_delta_from_rule(rule_delta)
                choices = fallback_choices(session)
                malformed_state_delta = False
            if not str(narrative or "").strip() and isinstance(state_delta, dict) and normalize_choices(choices):
                narrative = self._narrative_from_rule_delta(rule_delta)
                state_delta = self._empty_delta_from_rule(rule_delta)
                malformed_state_delta = False
            recovered_choices = self._recover_incomplete_narrator_choices(narrative, choices)
            if recovered_choices:
                choices = recovered_choices
                log.info("narrator choices recovered from rule context")
                if malformed_state_delta:
                    state_delta = self._empty_delta_from_rule(rule_delta)
                    malformed_state_delta = False
            else:
                choices = []
                engine.emit("on_info", narrator_status.reason)
        is_terminal_delta = _is_terminal_state_delta(state_delta)
        if is_terminal_delta:
            session.last_choices = []
        else:
            fallback_used = engine.set_choices(
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
                engine.emit("on_status_bar", format_status_bar(session))
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
            engine.emit("on_game_over", session.error or "游戏结束。")

    def _run_narrator(self, text: str, turn_summary: str) -> dict[str, Any] | None:
        engine = self.engine
        session = engine.game_session
        narrator_input = text
        if turn_summary:
            narrator_input = f"{text}\n\n[本回合规则结算结果（以此为权威数值）：{turn_summary}]"

        # Ordinary turns avoid a second model call for repair. If the live
        # narrator gives narrative and usable choices but misses state_update,
        # TurnFlow can keep the turn moving with the rule-engine delta below.
        try:
            result = engine.run_agent(
                "narrator",
                narrator_input,
                session,
                stream_callback=engine.stream_callback if engine.on_stream_chunk else None,
                repair_incomplete_output=False,
            )
            if _should_retry_narrator_result(result):
                log.info("narrator request failed with retryable provider error; retrying once")
                retry_result = engine.run_agent(
                    "narrator",
                    narrator_input,
                    session,
                    stream_callback=engine.stream_callback if engine.on_stream_chunk else None,
                    repair_incomplete_output=False,
                )
                if not retry_result.get("llm_error"):
                    retry_result["retried_after_request_failed"] = True
                return retry_result
            if _should_retry_unrecoverable_narrator_result(result):
                log.info("narrator output incomplete and unrecoverable; retrying once with strict contract reminder")
                retry_input = (
                    f"{narrator_input}\n\n"
                    "[输出契约提醒：上一轮可能缺少叙事或四个选项。本次必须输出："
                    "编年史叙事正文、<state_update>JSON</state_update>、"
                    "<choices>四个中文行动选项JSON数组</choices>。]"
                )
                retry_result = engine.run_agent(
                    "narrator",
                    retry_input,
                    session,
                    stream_callback=engine.stream_callback if engine.on_stream_chunk else None,
                    repair_incomplete_output=False,
                )
                if not retry_result.get("llm_error"):
                    retry_result["retried_after_incomplete_output"] = True
                return retry_result
            return result
        except Exception:
            log.exception("narrator error")
            reason = "叙述失败（详见日志）"
            engine.emit("on_error", reason)
            engine.set_choices(
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
        if not state_delta or not engine.should_run_judge(text, state_delta, rule_delta):
            return {}

        engine.emit("on_loading", "天道审判中...")
        try:
            judge_result = engine.run_agent(
                "judge",
                text,
                session,
                narrative=narrative,
                state_delta=state_delta,
            )
        except Exception:
            log.exception("judge error")
            reason = "天道审判失败（详见日志）"
            judge_result = {"approved": False, "corrected_delta": {}, "judgment_note": reason}

        judge_status = classify_judge_result(judge_result)
        engine.log_model_result(
            agent="judge",
            source="turn",
            status=judge_status.kind,
            reason=judge_status.reason,
            result=judge_result,
        )
        if judge_status.kind == ModelResultKind.JUDGE_FAILED:
            reason = judge_status.reason
            log.info("Judge failed; rejecting model delta and continuing with rule settlement")
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
                narrative = ""
                state_delta = {"character": {}, "world": {}, "meta": {}}
            note = judge_result.get("judgment_note", "")
            if note:
                log.info("Judge corrected: %s", note)
        return clean_visible_text(narrative, allow_structured=False), state_delta

    def _validate_and_apply_delta(
        self,
        text: str,
        narrative: str,
        state_delta: dict[str, Any],
        rule_delta: dict[str, Any],
    ) -> tuple[str, dict[str, Any]] | None:
        engine = self.engine
        session = engine.game_session
        state_delta = engine.sanitize_action_delta(state_delta)

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
        consistent, consistency_reason = validate_narrative_delta_consistency(
            narrative,
            state_delta,
        )
        if not consistent:
            log.info("Narrative/state mismatch rejected: %s", consistency_reason)
            narrative = ""
            session.last_choices = engine._filter_unavailable_breakthrough_choices(fallback_choices(session))
            state_delta = merge_rule_delta({"character": {}, "world": {}, "meta": {}}, rule_delta)

        session.apply_delta(state_delta)
        stage_delta = self._try_emit_stage_advance()
        if stage_delta is not None:
            state_delta = self._merge_state_delta(state_delta, stage_delta)

        if engine.check_game_over():
            return None

        if not str(narrative or "").strip():
            narrative = self._narrative_from_rule_delta(state_delta)

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
        session.record_turn(
            text,
            narrative,
            state_delta,
            local_story={
                "story_id": session.local_story_id,
                "node_id": session.local_story_node_id,
            },
        )

    def _record_and_emit_turn(
        self,
        text: str,
        narrative: str,
        state_delta: dict[str, Any],
    ) -> None:
        engine = self.engine
        session = engine.game_session
        session.record_turn(text, narrative, state_delta)

        if narrative:
            engine.emit("on_narrative", narrative, session.turn_count)

        engine.emit("on_status_bar", format_status_bar(session))

    def _try_emit_stage_advance(self) -> dict[str, Any] | None:
        engine = self.engine
        session = engine.game_session
        stage_delta = engine.realm_system.try_advance_stage(session)
        if stage_delta is not None:
            session.apply_delta(stage_delta)
            new_stage = stage_delta.get("meta", {}).get("new_stage", 0)
            max_stage = stage_delta.get("meta", {}).get("max_stage", 0)
            if session.realm == "练气":
                label = f"{session.realm}第{new_stage}层"
            else:
                label = format_realm(session)
            engine.emit("on_info", f"修为精进！{label}（{new_stage}/{max_stage}）")
            return stage_delta
        return None

    def _emit_local_story_breakthrough_result(self, breakthrough_delta: dict[str, Any]) -> None:
        engine = self.engine
        session = engine.game_session
        result = breakthrough_delta.get("meta", {}).get("breakthrough_result", "")
        if result == "success":
            if session.finale:
                engine.emit("on_finale", session.error or "飞升成仙，修真之路圆满。")
            else:
                engine.emit("on_info", format_realm(session))
        elif result == "failure":
            engine.emit("on_info", "突破失败，受到反噬。")

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

    @staticmethod
    def _empty_delta_from_rule(rule_delta: dict[str, Any]) -> dict[str, Any]:
        """Supply a model-empty delta while preserving rule-owned turn facts."""
        meta: dict[str, Any] = {}
        if isinstance(rule_delta, dict) and isinstance(rule_delta.get("meta"), dict):
            for key in ("game_over", "game_over_reason", "elapsed_years", "choice_category"):
                if key in rule_delta["meta"]:
                    meta[key] = rule_delta["meta"][key]
        return {"character": {}, "world": {}, "meta": meta}

    @staticmethod
    def _narrative_from_rule_delta(rule_delta: dict[str, Any]) -> str:
        """Build a short chronicle narrative when the model returns JSON-only output."""
        meta = rule_delta.get("meta") if isinstance(rule_delta, dict) else {}
        world = rule_delta.get("world") if isinstance(rule_delta, dict) else {}
        elapsed = 0
        stage_goal = ""
        lore = ""
        if isinstance(meta, dict):
            elapsed = int(meta.get("elapsed_years") or 0)
            lore = str(meta.get("event_lore") or "").strip()
            stage_goal = str(meta.get("stage_goal") or "").strip()
        if isinstance(world, dict) and isinstance(world.get("lore_add"), list) and world["lore_add"]:
            lore = str(world["lore_add"][0] or "").strip()
        years = f"{elapsed}年间，" if elapsed > 0 else ""
        if lore:
            return f"{years}{lore}"
        if stage_goal:
            return f"{years}其沿所选道路推进，{stage_goal}。"
        return f"{years}其按所选道路修行，外界局势仍在暗中变化。"


def _should_retry_narrator_result(result: dict[str, Any]) -> bool:
    """Retry one live narrator request for transient provider failures only."""
    return is_retryable_model_request_failure(result)


def _should_retry_unrecoverable_narrator_result(result: dict[str, Any]) -> bool:
    """Retry one live narrator request when TurnFlow cannot recover the shape."""
    if not isinstance(result, dict) or result.get("llm_error"):
        return False
    if _has_nonempty_structured_delta(result.get("state_delta")):
        return False
    if str(result.get("narrative") or "").strip():
        return False
    if normalize_choices(result.get("choices")):
        return False
    return classify_narrator_result(result).kind == ModelResultKind.INCOMPLETE_OUTPUT


def _has_nonempty_structured_delta(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    for section in ("character", "world", "meta"):
        section_value = value.get(section)
        if isinstance(section_value, dict) and section_value:
            return True
    return False


def _is_terminal_state_delta(state_delta: Any) -> bool:
    if not isinstance(state_delta, dict):
        return False
    meta_delta = state_delta.get("meta")
    return isinstance(meta_delta, dict) and bool(meta_delta.get("game_over") or meta_delta.get("finale"))
