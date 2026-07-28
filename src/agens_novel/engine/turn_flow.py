"""Turn-flow orchestration for GameEngine."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .game_engine import GameEngine

from ..game.constants import format_realm_name
from .action_delta_policy import merge_rule_delta, validate_narrative_delta_consistency
from .choices import fallback_choices
from .model_result import (
    ModelResultKind,
    classify_narrator_result,
    is_retryable_model_request_failure,
)
from .narrative_policy import (
    _generic_distinct_chronicle,
    _has_unapproved_time_span,
    _has_visible_authoritative_delta,
    _is_recent_duplicate_narrative,
    _narrative_conflicts_with_authoritative_realm,
    _narrative_conflicts_with_stage_delta,
    _visible_delta_chronicle,
    narrative_from_rule_delta,
)
from .narrative_policy import (
    _narrative_key as _narrative_key,
)
from .narrative_policy import (
    _narrative_keys_overlap as _narrative_keys_overlap,
)
from .pending_model_failure import PendingModelFailureV1
from .render import format_status_bar
from .turn_rules import settle_turn, settle_turn_outcome

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

        if not result.matched:
            session.last_choices = engine._filter_unavailable_breakthrough_choices(result.choices)
            engine.emit("on_info", result.narrative)
            engine.emit("on_status_bar", format_status_bar(session))
            return

        session.turn_count += 1
        session.realm_turn_count += 1
        rule_delta = settle_turn(text, session)
        result_delta = self._merge_local_story_rule_delta(
            result.delta if isinstance(result.delta, dict) else {},
            rule_delta,
        )
        session.apply_delta(result_delta)
        stage_delta = self._try_emit_stage_advance()
        if stage_delta is not None:
            result_delta = self._merge_state_delta(result_delta, stage_delta)

        if result.breakthrough:
            breakthrough_delta = engine.attempt_local_story_breakthrough()
            if breakthrough_delta:
                session.apply_delta(breakthrough_delta)
                self._emit_local_story_breakthrough_result(breakthrough_delta)
                result_delta = self._merge_state_delta(result_delta, breakthrough_delta)

        if session.game_over:
            session.last_choices = []
        else:
            session.last_choices = engine._filter_unavailable_breakthrough_choices(result.choices)

        narrative = result.narrative
        character_delta = result_delta.get("character")
        recovered = (
            character_delta.get("status_effects_remove", [])
            if isinstance(character_delta, dict)
            else []
        )
        if isinstance(recovered, list) and recovered:
            narrative = (
                f"其暂缓破境，以一段岁月疗伤调息，化去{'、'.join(map(str, recovered))}。"
                f"\n\n{narrative}"
            )

        if narrative:
            engine.emit("on_narrative", narrative, session.turn_count)

        session.record_turn(
            text,
            narrative,
            result_delta,
            local_story={
                "story_id": session.local_story_id,
                "node_id": session.local_story_node_id,
            },
        )
        self._advance_rule_rng_counter()
        engine.emit("on_status_bar", format_status_bar(session))

        engine.check_game_over()

    def handle_action(self, text: str) -> None:
        """Process one ordinary player action through rules and narrator."""
        engine = self.engine
        session = engine.game_session
        if engine.pending_model_failure() is not None:
            engine.emit("on_info", "请先处理上一回合未完成的叙事请求。")
            return
        session.turn_count += 1
        session.realm_turn_count += 1

        engine.emit("on_loading", "天道运转中...")

        outcome = settle_turn_outcome(text, session)
        rule_delta = outcome.state_delta
        turn_summary = outcome.turn_summary

        narrator_result = self._run_narrator(text, turn_summary)

        narrator_status = classify_narrator_result(narrator_result)
        engine.log_model_result(
            agent="narrator",
            source="turn",
            status=narrator_status.kind,
            reason=narrator_status.reason,
            result=narrator_result,
        )
        if narrator_status.kind != ModelResultKind.OK:
            self._hold_pending_failure(
                text,
                rule_delta,
                turn_summary,
                narrator_status,
            )
            return

        self._apply_accepted_turn(text, narrator_result, rule_delta)

    def retry_pending_model(self, pending: PendingModelFailureV1) -> bool:
        """Retry one failed Narrator request using its frozen rule outcome."""
        if pending.stage != "turn":
            return False
        engine = self.engine
        session = engine.game_session
        frozen = pending.frozen_result
        rule_delta = frozen.get("state_delta")
        turn_summary = frozen.get("turn_summary")
        if not isinstance(rule_delta, dict) or not isinstance(turn_summary, str):
            raise ValueError("待处理回合缺少冻结规则结果。")
        engine.replace_pending_model_failure(
            pending.with_status("retrying", request_no=pending.request_no + 1)
        )
        session.turn_count += 1
        session.realm_turn_count += 1
        result = self._run_narrator(pending.action, turn_summary)
        status = classify_narrator_result(result)
        engine.log_model_result(
            agent="narrator",
            source="turn_retry",
            status=status.kind,
            reason=status.reason,
            result=result,
        )
        if status.kind != ModelResultKind.OK:
            self._restore_unsettled_turn()
            engine.replace_pending_model_failure(
                pending.with_status("pending", request_no=pending.request_no + 1)
            )
            engine.emit("on_info", "重试未完成，规则结果仍已冻结，请重新选择处理方式。")
            return False
        self._apply_accepted_turn(pending.action, result, rule_delta)
        return True

    def resolve_pending_with_local_story(self, pending: PendingModelFailureV1) -> bool:
        """Apply the frozen rules once and then enter local story by player choice."""
        if pending.stage != "turn":
            return False
        rule_delta = pending.frozen_result.get("state_delta")
        if not isinstance(rule_delta, dict):
            raise ValueError("待处理回合缺少冻结规则结果。")
        engine = self.engine
        session = engine.game_session
        session.turn_count += 1
        session.realm_turn_count += 1
        applied = self._validate_and_apply_delta(
            pending.action,
            self._narrative_from_rule_delta(rule_delta),
            rule_delta,
            model_state_update_present=False,
        )
        if applied is None:
            return False
        narrative, applied_delta = applied
        meta = applied_delta.setdefault("meta", {})
        if isinstance(meta, dict):
            meta["local_story_fallback"] = True
            meta["fallback_reason"] = pending.error_code
        engine._enter_local_story("player selected local story", emit_narrative=False)
        self._record_and_emit_turn(pending.action, narrative, applied_delta)
        engine.clear_pending_model_failure()
        return True

    def _hold_pending_failure(
        self,
        text: str,
        rule_delta: dict[str, Any],
        turn_summary: str,
        status: Any,
    ) -> None:
        self._restore_unsettled_turn()
        slot = text[:1].upper() if text[:1].upper() in {"A", "B", "C", "D"} else ""
        self.engine.create_pending_model_failure(
            stage="turn",
            action=text,
            slot=slot,
            frozen_result={"state_delta": rule_delta, "turn_summary": turn_summary},
            error_code=_error_code_for_status(status),
        )

    def _restore_unsettled_turn(self) -> None:
        session = self.engine.game_session
        session.turn_count = max(0, session.turn_count - 1)
        session.realm_turn_count = max(0, session.realm_turn_count - 1)

    def _apply_accepted_turn(
        self,
        text: str,
        narrator_result: dict[str, Any],
        rule_delta: dict[str, Any],
    ) -> None:
        engine = self.engine
        session = engine.game_session
        narrative = str(narrator_result.get("narrative") or "")
        raw_state_delta = narrator_result.get("state_delta")
        applied = self._validate_and_apply_delta(
            text,
            narrative,
            rule_delta,
            model_state_update_present=isinstance(raw_state_delta, dict) and bool(raw_state_delta),
        )
        if applied is None:
            return
        narrative, applied_delta = applied
        choices = narrator_result.get("choices")
        if engine.set_choices(choices, source="narrator", require_choice=False):
            raise ValueError("严格 Narrator 输出缺少四个选项。")
        self._record_and_emit_turn(text, narrative, applied_delta)
        engine.clear_pending_model_failure()
        if session.game_over:
            engine.check_game_over()

    def _run_narrator(self, text: str, turn_summary: str) -> dict[str, Any]:
        engine = self.engine
        session = engine.game_session
        narrator_input = text
        if turn_summary:
            narrator_input = f"{text}\n\n[本回合规则结算结果（以此为权威数值）：{turn_summary}]"

        # A failed or incomplete model response is retried once, then frozen for
        # an explicit player decision. The rule outcome is never recomputed.
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
            if _should_retry_incomplete_narrator_result(result):
                log.info("narrator output incomplete; retrying once with strict contract reminder")
                retry_input = (
                    f"{narrator_input}\n\n"
                    "[输出契约提醒：上一轮输出未满足完整三段合同。"
                    "本次必须返回非空编年史叙事、合法状态对象，以及四个非空、互不重复、"
                    "依次对应稳妥/机遇/风险/气运的中文行动选项。"
                    "叙事正文和四个选项不得含任何英文字母、英文缩写或拉丁字母；"
                    "请将上一轮英文内容改写为中文或省略。继续遵守当前传输格式。]"
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
            return {"narrative": "", "choices": [], "state_delta": {}, "llm_error": reason}

    def _validate_and_apply_delta(
        self,
        text: str,
        narrative: str,
        rule_delta: dict[str, Any],
        *,
        model_state_update_present: bool,
    ) -> tuple[str, dict[str, Any]] | None:
        """Apply only the already-computed rule outcome to session state.

        Narrator state updates remain parsed as legacy transport diagnostics, but
        cannot grant rewards, mutate relationships, or alter any other
        authority field. Provider retries therefore reuse one rule outcome.
        """
        engine = self.engine
        session = engine.game_session
        state_delta = self._rule_only_delta(rule_delta, model_state_update_present)
        if _has_unapproved_time_span(narrative, state_delta):
            log.info("narrative exact time span conflicted with rule settlement; using rule chronicle")
            narrative = ""
        consistent, consistency_reason = validate_narrative_delta_consistency(
            narrative,
            state_delta,
        )
        if not consistent:
            log.info("Narrative/state mismatch rejected: %s", consistency_reason)
            narrative = ""
            session.last_choices = engine._filter_unavailable_breakthrough_choices(
                fallback_choices(session)
            )
            state_delta = self._rule_only_delta(rule_delta, model_state_update_present)

        session.apply_delta(state_delta)
        stage_delta = self._try_emit_stage_advance()
        if stage_delta is not None:
            state_delta = self._merge_state_delta(state_delta, stage_delta)
            if _narrative_conflicts_with_stage_delta(narrative, stage_delta, session):
                log.info(
                    "narrative realm stage contradicted post-settlement stage; using rule chronicle"
                )
                narrative = self._narrative_from_rule_delta(state_delta)

        if _narrative_conflicts_with_authoritative_realm(narrative, session):
            log.info("narrative realm claim contradicted authoritative current realm; using rule chronicle")
            narrative = _generic_distinct_chronicle(state_delta, session)

        if not str(narrative or "").strip():
            narrative = self._narrative_from_rule_delta(state_delta)

        return narrative, state_delta

    @staticmethod
    def _rule_only_delta(
        rule_delta: dict[str, Any], model_state_update_present: bool
    ) -> dict[str, Any]:
        """Copy the authoritative delta without accepting model mutations."""
        state_delta = {
            "character": dict(rule_delta.get("character") or {}),
            "world": dict(rule_delta.get("world") or {}),
            "meta": dict(rule_delta.get("meta") or {}),
        }
        if model_state_update_present:
            state_delta["meta"]["model_state_update_ignored"] = True
        return state_delta

    def _record_and_emit_turn(
        self,
        text: str,
        narrative: str,
        state_delta: dict[str, Any],
    ) -> None:
        engine = self.engine
        session = engine.game_session
        if _is_recent_duplicate_narrative(session, narrative):
            replacement = self._narrative_from_rule_delta(state_delta)
            visible_delta = _visible_delta_chronicle(state_delta)
            if visible_delta:
                replacement = f"{replacement}{visible_delta}"
            if replacement and _is_recent_duplicate_narrative(session, replacement):
                replacement = f"{_generic_distinct_chronicle(state_delta, session)}{visible_delta}"
            if (
                replacement
                and not _is_recent_duplicate_narrative(session, replacement)
                and validate_narrative_delta_consistency(replacement, state_delta)[0]
            ):
                log.info("recent duplicate narrative replaced with rule chronicle")
                narrative = replacement
            elif not _has_visible_authoritative_delta(state_delta, narrative):
                narrative = _generic_distinct_chronicle(state_delta, session)
        if _narrative_conflicts_with_stage_delta(narrative, state_delta, session):
            log.info(
                "visible chronicle contradicted final realm stage; using distinct rule chronicle"
            )
            narrative = _generic_distinct_chronicle(state_delta, session)
        session.record_turn(text, narrative, state_delta)
        self._advance_rule_rng_counter()

        if narrative:
            engine.emit("on_narrative", narrative, session.turn_count)

        engine.emit("on_status_bar", format_status_bar(session))

    def _advance_rule_rng_counter(self) -> None:
        """Advance only after the turn record has been created.

        WebGameService restores the whole runner snapshot if its transaction
        fails, so an uncommitted mutation cannot retain this increment.
        """
        session = self.engine.game_session
        if not str(getattr(session, "run_seed", "") or "").strip():
            return
        raw_counter = getattr(session, "rule_rng_counter", 0)
        counter = raw_counter if isinstance(raw_counter, int) and not isinstance(raw_counter, bool) else 0
        session.rule_rng_counter = max(0, counter) + 1

    def _try_emit_stage_advance(self) -> dict[str, Any] | None:
        engine = self.engine
        session = engine.game_session
        stage_delta = engine.realm_system.try_advance_stage(session)
        if stage_delta is not None:
            session.apply_delta(stage_delta)
            new_stage = stage_delta.get("meta", {}).get("new_stage", 0)
            label = format_realm_name(session.realm, int(new_stage or session.realm_stage))
            engine.emit("on_info", f"修为精进，已至{label}。")
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
                engine.emit(
                    "on_info",
                    f"破境已成，已至{format_realm_name(session.realm, session.realm_stage)}。",
                )
        elif result == "failure":
            engine.emit("on_info", "破境未成，需先稳住根基。")

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

    @staticmethod
    def _merge_local_story_rule_delta(
        story_delta: dict[str, Any],
        rule_delta: dict[str, Any],
    ) -> dict[str, Any]:
        """Keep authored local-story gains while applying rule-owned time facts."""
        merged = merge_rule_delta(story_delta, rule_delta)
        story_char = story_delta.get("character") if isinstance(story_delta, dict) else {}
        rule_char = rule_delta.get("character") if isinstance(rule_delta, dict) else {}
        if not isinstance(story_char, dict) or not isinstance(rule_char, dict):
            return merged
        story_attrs = story_char.get("attributes")
        rule_attrs = rule_char.get("attributes")
        if not isinstance(story_attrs, dict) or not isinstance(rule_attrs, dict):
            return merged
        combined = dict(rule_attrs)
        for key, value in story_attrs.items():
            if isinstance(value, int) and not isinstance(value, bool):
                combined[key] = int(combined.get(key) or 0) + value
        character = dict(merged.get("character") or {})
        character["attributes"] = combined
        merged["character"] = character
        return merged

    @staticmethod
    def _narrative_from_rule_delta(rule_delta: dict[str, Any]) -> str:
        return narrative_from_rule_delta(rule_delta)


def _should_retry_narrator_result(result: dict[str, Any]) -> bool:
    """Retry one live narrator request for transient provider failures only."""
    return is_retryable_model_request_failure(result)


def _should_retry_incomplete_narrator_result(result: dict[str, Any]) -> bool:
    """Retry one incomplete response before creating a pending failure."""
    if not isinstance(result, dict) or result.get("llm_error"):
        return False
    status = classify_narrator_result(result)
    if status.kind != ModelResultKind.INCOMPLETE_OUTPUT:
        return False
    return True


def _error_code_for_status(status: Any) -> str:
    kind = getattr(status, "kind", "")
    if kind == ModelResultKind.REQUEST_FAILED:
        return "request_failed"
    if kind == ModelResultKind.INCOMPLETE_OUTPUT:
        return "incomplete_output"
    return "llm_error"
