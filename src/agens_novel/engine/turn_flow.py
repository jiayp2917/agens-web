"""Turn-flow orchestration for GameEngine."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .game_engine import GameEngine

from ..agents.contracts import JudgeDecisionV1
from ..game.constants import format_realm_name
from .action_delta_policy import merge_rule_delta, validate_narrative_delta_consistency
from .choices import clean_visible_text, fallback_choices, normalize_choices
from .model_result import (
    ModelResultKind,
    classify_judge_result,
    classify_narrator_result,
    is_retryable_model_request_failure,
)
from .narrative_policy import (
    _generic_distinct_chronicle,
    _has_nonempty_structured_delta,
    _has_unapproved_time_span,
    _has_visible_authoritative_delta,
    _has_visible_contract_violation,
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
        """Process one ordinary player action through rules, narrator and judge."""
        engine = self.engine
        session = engine.game_session
        session.turn_count += 1
        session.realm_turn_count += 1

        engine.emit("on_loading", "天道运转中...")

        outcome = settle_turn_outcome(text, session)
        rule_delta = outcome.state_delta
        turn_summary = outcome.turn_summary

        narrator_result = self._run_narrator(text, turn_summary)
        if narrator_result is None:
            session.turn_count -= 1
            session.realm_turn_count = max(0, session.realm_turn_count - 1)
            engine.emit("on_info", "本回合记录暂未续上，已切换本地故事，请直接选择下方选项继续。")
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
            session.realm_turn_count = max(0, session.realm_turn_count - 1)
            return

        narrative = narrator_result.get("narrative", "")
        raw_state_delta = narrator_result.get("state_delta", {})
        malformed_state_delta = raw_state_delta is None or not isinstance(raw_state_delta, dict)
        state_delta = raw_state_delta if isinstance(raw_state_delta, dict) else {}
        model_state_update_present = bool(state_delta)
        choices = narrator_result.get("choices", [])
        if narrator_status.kind == ModelResultKind.INCOMPLETE_OUTPUT:
            if _has_visible_contract_violation(narrator_result):
                narrative = ""
                state_delta = {}
                choices = []
                malformed_state_delta = False
            narrative, state_delta, choices = self._recover_incomplete_payload(
                narrative,
                state_delta,
                choices,
                malformed_state_delta,
                rule_delta,
                narrator_status.reason,
            )
        judge_result = self._run_judge_if_needed(text, narrative, state_delta, rule_delta)
        if judge_result:
            narrative, state_delta = self._apply_judge_result(narrative, state_delta, judge_result)
        applied = self._validate_and_apply_delta(
            text,
            narrative,
            rule_delta,
            model_state_update_present=model_state_update_present,
        )
        if applied is None:
            return
        narrative, applied_delta = applied

        self._commit_turn_choices(choices, narrator_status, applied_delta)

        self._record_and_emit_turn(text, narrative, applied_delta)

        if session.game_over:
            engine.check_game_over()

    def _recover_incomplete_payload(
        self,
        narrative: Any,
        state_delta: dict[str, Any],
        choices: Any,
        malformed_state_delta: bool,
        rule_delta: dict[str, Any],
        failure_reason: str,
    ) -> tuple[str, dict[str, Any], Any]:
        has_narrative = bool(str(narrative or "").strip())
        normalized_choices = normalize_choices(choices)
        if (
            not has_narrative
            and _has_nonempty_structured_delta(state_delta)
            and not normalized_choices
        ):
            log.info(
                "narrator returned JSON-only delta; rejecting model delta and settling by rules"
            )
            narrative = self._narrative_from_rule_delta(rule_delta)
            state_delta = self._empty_delta_from_rule(rule_delta)
            choices = fallback_choices(self.engine.game_session)
            malformed_state_delta = False
        elif not has_narrative and normalized_choices:
            narrative = self._narrative_from_rule_delta(rule_delta)
            state_delta = self._empty_delta_from_rule(rule_delta)
            malformed_state_delta = False
        recovered = self._recover_incomplete_narrator_choices(str(narrative or ""), choices)
        if recovered:
            log.info("narrator choices recovered from rule context")
            if malformed_state_delta:
                state_delta = self._empty_delta_from_rule(rule_delta)
            return str(narrative or ""), state_delta, recovered
        self.engine.emit("on_info", failure_reason)
        return str(narrative or ""), state_delta, []

    def _commit_turn_choices(
        self, choices: Any, narrator_status: Any, applied_delta: dict[str, Any]
    ) -> None:
        engine = self.engine
        if engine.game_session.game_over:
            engine.game_session.last_choices = []
            return
        reason = (
            narrator_status.reason
            if narrator_status.kind == ModelResultKind.INCOMPLETE_OUTPUT
            else "叙事模型未返回可用选项。"
        )
        if not engine.set_choices(
            choices,
            source="narrator",
            fallback_notice=True,
            require_choice=True,
            reason=reason,
            emit_local_story_narrative=True,
        ):
            return
        meta = applied_delta.setdefault("meta", {})
        if isinstance(meta, dict):
            meta["local_story_fallback"] = True
            meta["fallback_reason"] = narrator_status.reason

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
            engine.emit("on_error", engine.fallback_notice_for(reason))
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
    ) -> dict[str, Any] | None:
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
            if is_retryable_model_request_failure(judge_result):
                log.info("judge request failed with retryable provider error; retrying once")
                retry_result = engine.run_agent(
                    "judge",
                    text,
                    session,
                    narrative=narrative,
                    state_delta=state_delta,
                )
                if not retry_result.get("llm_error"):
                    retry_result["retried_after_request_failed"] = True
                judge_result = retry_result
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
        decision = JudgeDecisionV1.from_payload(judge_result)
        if not decision.approved:
            log.info("Judge rejected narrator prose: %s", judge_result.get("judgment_note", ""))
            narrative = ""
        return clean_visible_text(narrative, allow_structured=False), state_delta

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
            return recovered[: len(fallbacks)]
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
        return narrative_from_rule_delta(rule_delta)


def _should_retry_narrator_result(result: dict[str, Any]) -> bool:
    """Retry one live narrator request for transient provider failures only."""
    return is_retryable_model_request_failure(result)


def _should_retry_incomplete_narrator_result(result: dict[str, Any]) -> bool:
    """Retry one strict-schema response, or a wholly unusable legacy response."""
    if not isinstance(result, dict) or result.get("llm_error"):
        return False
    status = classify_narrator_result(result)
    if status.kind != ModelResultKind.INCOMPLETE_OUTPUT:
        return False
    if result.get("provider_json_schema") or result.get("provider_json_object"):
        return True
    if _has_nonempty_structured_delta(result.get("state_delta")):
        return False
    if str(result.get("narrative") or "").strip():
        return False
    if normalize_choices(result.get("choices")):
        return False
    return True
