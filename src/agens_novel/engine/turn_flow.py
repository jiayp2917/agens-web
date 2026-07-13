"""Turn-flow orchestration for GameEngine."""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .game_engine import GameEngine

from ..game.constants import format_realm_name
from .action_delta_policy import (
    apply_breakthrough_flag_rule,
    enforce_event_delta_policy,
    is_pure_cultivation,
    merge_rule_delta,
    validate_narrative_delta_consistency,
)
from .choices import clean_visible_text, fallback_choices, normalize_choices
from .model_result import (
    ModelResultKind,
    classify_judge_result,
    classify_narrator_result,
    is_retryable_model_request_failure,
)
from .render import format_status_bar
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

        if not result.matched:
            session.last_choices = engine._filter_unavailable_breakthrough_choices(result.choices)
            engine.emit("on_info", result.narrative)
            engine.emit("on_status_bar", format_status_bar(session))
            return

        session.turn_count += 1
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
        engine.emit("on_status_bar", format_status_bar(session))

        engine.check_game_over()

    def handle_action(self, text: str) -> None:
        """Process one ordinary player action through rules, narrator and judge."""
        engine = self.engine
        session = engine.game_session
        session.turn_count += 1

        engine.emit("on_loading", "天道运转中...")

        rule_delta = settle_turn(text, session)
        turn_summary = (
            rule_delta.get("meta", {}).get("turn_summary", "")
            if isinstance(rule_delta.get("meta"), dict)
            else ""
        )

        narrator_result = self._run_narrator(text, turn_summary)
        if narrator_result is None:
            session.turn_count -= 1
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
            return

        narrative = narrator_result.get("narrative", "")
        raw_state_delta = narrator_result.get("state_delta", {})
        attempted_world_reset = engine.action_delta_resets_world(raw_state_delta)
        malformed_state_delta = raw_state_delta is None or not isinstance(raw_state_delta, dict)
        state_delta = raw_state_delta if isinstance(raw_state_delta, dict) else {}
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
        if attempted_world_reset:
            narrative = self._narrative_from_rule_delta(rule_delta)
        state_delta = engine.sanitize_action_delta(state_delta)
        state_delta = enforce_event_delta_policy(state_delta, rule_delta)
        judge_result = self._run_judge_if_needed(text, narrative, state_delta, rule_delta)
        if judge_result is None and session.game_over:
            return
        if isinstance(judge_result, dict):
            narrative, state_delta = self._apply_judge_result(narrative, state_delta, judge_result)

        applied = self._validate_and_apply_delta(text, narrative, state_delta, rule_delta)
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
                    "依次对应稳妥/机遇/风险/气运的中文行动选项；继续遵守当前传输格式。]"
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
        state_delta = enforce_event_delta_policy(state_delta, rule_delta)

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
            session.last_choices = engine._filter_unavailable_breakthrough_choices(
                fallback_choices(session)
            )
            state_delta = merge_rule_delta({"character": {}, "world": {}, "meta": {}}, rule_delta)

        session.apply_delta(state_delta)
        stage_delta = self._try_emit_stage_advance()
        if stage_delta is not None:
            state_delta = self._merge_state_delta(state_delta, stage_delta)
            if _narrative_conflicts_with_stage_delta(narrative, stage_delta, session):
                log.info(
                    "narrative realm stage contradicted post-settlement stage; using rule chronicle"
                )
                narrative = self._narrative_from_rule_delta(state_delta)

        if not str(narrative or "").strip():
            narrative = self._narrative_from_rule_delta(state_delta)

        return narrative, state_delta

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
        """Build a short chronicle narrative when the model returns JSON-only output."""
        meta = rule_delta.get("meta") if isinstance(rule_delta, dict) else {}
        world = rule_delta.get("world") if isinstance(rule_delta, dict) else {}
        elapsed = 0
        stage_goal = ""
        lore = ""
        if isinstance(meta, dict):
            elapsed = int(meta.get("elapsed_years") or 0)
            lore = str(meta.get("event_lore") or "").strip()
            story_beat = str(meta.get("story_beat") or "").strip()
            if story_beat:
                lore = story_beat
            stage_goal = str(meta.get("story_goal") or meta.get("stage_goal") or "").strip()
        if (
            isinstance(world, dict)
            and isinstance(world.get("lore_add"), list)
            and world["lore_add"]
        ):
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


def _should_retry_incomplete_narrator_result(result: dict[str, Any]) -> bool:
    """Retry one strict-schema response, or a wholly unusable legacy response."""
    if not isinstance(result, dict) or result.get("llm_error"):
        return False
    status = classify_narrator_result(result)
    if status.kind != ModelResultKind.INCOMPLETE_OUTPUT:
        return False
    if result.get("provider_json_schema"):
        return True
    if _has_nonempty_structured_delta(result.get("state_delta")):
        return False
    if str(result.get("narrative") or "").strip():
        return False
    if normalize_choices(result.get("choices")):
        return False
    return True


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
    return isinstance(meta_delta, dict) and bool(
        meta_delta.get("game_over") or meta_delta.get("finale")
    )


def _is_recent_duplicate_narrative(session: Any, narrative: str, *, limit: int = 60) -> bool:
    key = _narrative_key(narrative)
    if len(key) < 16:
        return False
    history = getattr(session, "turn_history", []) or []
    if not isinstance(history, list):
        return False
    for entry in history[-limit:]:
        if not isinstance(entry, dict):
            continue
        previous_key = _narrative_key(str(entry.get("narrative") or ""))
        if _narrative_keys_overlap(key, previous_key):
            return True
    return False


def _narrative_key(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"[零〇一二三四五六七八九十百千万\d]+\s*(岁|年|载|回合)", r"X\1", value)
    value = re.sub(r"\d+", "N", value)
    return re.sub(r"[\s，。、“”‘’；：:,.!?！？（）()\[\]\"']+", "", value)


def _narrative_keys_overlap(left: str, right: str) -> bool:
    if left == right:
        return True
    if len(left) < 16 or len(right) < 16:
        return False
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if shorter in longer and len(shorter) / max(1, len(longer)) >= 0.65:
        return True
    if len(shorter) >= 48 and SequenceMatcher(None, left, right).ratio() >= 0.86:
        return True
    if len(shorter) >= 20:
        left_grams = {left[index : index + 2] for index in range(len(left) - 1)}
        right_grams = {right[index : index + 2] for index in range(len(right) - 1)}
        overlap = len(left_grams & right_grams) / max(1, min(len(left_grams), len(right_grams)))
        if overlap >= 0.86:
            return True
    return False


_QI_STAGE_CLAIM_RE = re.compile(r"练气\s*(?:第)?\s*([1-9一二三四五六七八九])\s*层")
_REALM_PHASE_CLAIM_RE = re.compile(r"(筑基|金丹|元婴|化神|合体|大乘|渡劫)\s*(初期|中期|后期|圆满)")
_CHINESE_STAGE_VALUES = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CLAUSE_BOUNDARY_RE = re.compile(r"[。！？!?；;\n]")
_PLAYER_REALM_TRANSITION_BEFORE_RE = re.compile(
    r"(?:突破至|踏入|晋入|修至|跌落至|退回|重返|迈入|臻至|升至)\s*$"
)
_REALM_REQUIREMENT_BEFORE_RE = re.compile(
    r"(?:要求|至少|最低|不低于|门槛为|条件为|须达|需达|修为达到|境界达到)\s*$"
)
_REALM_REQUIREMENT_AFTER_RE = re.compile(
    r"^\s*(?:以上|以下)?\s*(?:方可|才可|方能|即可|才能|可接取|可报名|可登记|可领取|适用)"
)


def _narrative_conflicts_with_stage_delta(
    narrative: str,
    stage_delta: dict[str, Any],
    session: Any,
) -> bool:
    character = stage_delta.get("character") if isinstance(stage_delta, dict) else None
    if not isinstance(character, dict) or "realm_stage" not in character:
        return False
    try:
        target_stage = int(character["realm_stage"])
    except (TypeError, ValueError):
        return False

    text = str(narrative or "")
    realm = str(getattr(session, "realm", "") or "")
    if realm == "练气":
        claims: set[int] = {
            _qi_stage_claim_value(match)
            for match in _QI_STAGE_CLAIM_RE.finditer(text)
            if not _is_non_player_stage_reference(text, match.start(), match.end())
        }
        claims.discard(0)
        return bool(claims) and target_stage not in claims

    labels = ("初期", "中期", "后期", "圆满")
    target_label = labels[max(1, min(4, target_stage)) - 1]
    phase_claims: set[str] = {
        str(match.group(2))
        for match in _REALM_PHASE_CLAIM_RE.finditer(text)
        if match.group(1) == realm
        and not _is_non_player_stage_reference(text, match.start(), match.end())
    }
    return bool(phase_claims) and target_label not in phase_claims


def _is_non_player_stage_reference(text: str, start: int, end: int) -> bool:
    """Ignore only explicit realm requirements, never player transition claims."""
    clause_start = 0
    clause_end = len(text)
    for boundary in _CLAUSE_BOUNDARY_RE.finditer(text):
        if boundary.end() <= start:
            clause_start = boundary.end()
            continue
        clause_end = boundary.start()
        break
    before = text[clause_start:start][-20:]
    after = text[end:clause_end][:20]
    if _PLAYER_REALM_TRANSITION_BEFORE_RE.search(before):
        return False
    return bool(
        _REALM_REQUIREMENT_BEFORE_RE.search(before) or _REALM_REQUIREMENT_AFTER_RE.search(after)
    )


def _qi_stage_claim_value(match: re.Match[str]) -> int:
    raw = str(match.group(1))
    return int(raw) if raw.isdigit() else _CHINESE_STAGE_VALUES.get(raw, 0)


def _generic_distinct_chronicle(state_delta: dict[str, Any], session: Any) -> str:
    meta = state_delta.get("meta") if isinstance(state_delta, dict) else {}
    elapsed = 0
    stage_goal = ""
    category = ""
    if isinstance(meta, dict):
        elapsed = int(meta.get("elapsed_years") or 0)
        stage_goal = str(meta.get("story_goal") or meta.get("stage_goal") or "").strip()
        category = str(meta.get("choice_category") or "").strip()
    years = f"{elapsed}年间，" if elapsed > 0 else ""
    turn = int(getattr(session, "turn_count", 0) or 0)
    route = f"沿{category}之路" if category else "沿所选道路"
    closures = (
        "卷末另记山门风声已有转向。",
        "旁注称坊市议论也随之变化。",
        "同门对此各有取舍，旧局不再原样延续。",
        "外界传闻因此出现新的解释。",
        "势力间的应对已与上一阶段不同。",
        "此后数年的因果由此改换落点。",
        "旧有线索被重新排序，后续行止随之调整。",
        "本阶段留下的新旁证已写入卷册。",
    )
    if stage_goal:
        variants = (
            f"{route}暂收旧议，依当前局势推进{stage_goal}。",
            f"{route}重新梳理线索，将{stage_goal}列为下一阶段要务。",
            f"{route}核对前因后果，围绕{stage_goal}调整后续安排。",
            f"{route}把散落见闻归入本阶段卷册，继续推进{stage_goal}。",
            f"{route}从外界变化中确认新的侧证，转而处理{stage_goal}。",
            f"{route}对照旧卷与新讯，重新安排{stage_goal}的先后次序。",
            f"{route}暂缓沿用旧策，依据眼前局势续办{stage_goal}。",
            f"{route}将本轮见闻交叉核验，再从新的切口推进{stage_goal}。",
        )
        closure = closures[(turn // len(variants)) % len(closures)]
        return f"{years}{variants[turn % len(variants)]}{closure}"
    variants = (
        f"{route}留下新的编年史旁证，外界局势继续变化。",
        f"{route}重整旧日见闻，山门内外又有新的动向浮现。",
        f"{route}核对这一阶段的得失，下一段因果随之展开。",
        f"{route}将零散传闻归档，势力间的暗流仍未停歇。",
        f"{route}结束本段修行，外界风向已与往日不同。",
        f"{route}对照新旧消息，确认下一阶段已不能照搬前策。",
        f"{route}暂收眼前得失，转而观察各方随后作出的回应。",
        f"{route}把本轮旁证写入卷册，后续因果另有新的落点。",
    )
    closure = closures[(turn // len(variants)) % len(closures)]
    return f"{years}{variants[turn % len(variants)]}{closure}"


def _visible_delta_chronicle(state_delta: dict[str, Any]) -> str:
    """Summarize visible structured outcomes when replacing repeated prose."""
    if not isinstance(state_delta, dict):
        return ""
    character = state_delta.get("character")
    world = state_delta.get("world")
    details: list[str] = []
    _append_character_delta_details(details, character)
    _append_world_delta_details(details, world)
    return "" if not details else " 同期，" + "；".join(details) + "。"


def _append_character_delta_details(details: list[str], character: Any) -> None:
    if isinstance(character, dict):
        inventory = _delta_names(character.get("inventory_add"))
        techniques = _delta_names(character.get("techniques_add"))
        titles = _delta_names(character.get("title_add"))
        relationships = _relationship_delta_text(character.get("relationship_add"))
        effects = _delta_names(character.get("status_effects_add"))
        if inventory:
            details.append(f"本回合入册所得为{'、'.join(inventory)}")
        if techniques:
            details.append(f"其新入册功法为{'、'.join(techniques)}")
        if titles:
            details.append(f"其新获称号为{'、'.join(titles)}")
        if relationships:
            details.append(f"其人物关系更新为{'、'.join(relationships)}")
        if effects:
            details.append(f"其身上留下{'、'.join(effects)}")


def _append_world_delta_details(details: list[str], world: Any) -> None:
    if isinstance(world, dict):
        npcs = _delta_names(world.get("npcs_present_add"))
        quests = _delta_names(world.get("active_quests_add"))
        discovered = _delta_names(world.get("discovered_add"))
        if npcs:
            details.append(f"其与{'、'.join(npcs)}有了新的往来")
        if quests:
            details.append(f"{'、'.join(quests)}被列入后续行程")
        if discovered:
            details.append(f"新近确认的地点包括{'、'.join(discovered)}")
        scene = str(world.get("current_scene") or world.get("location") or "").strip()
        if scene:
            details.append(f"其行迹转至{scene}")


def _delta_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = str(item.get("name") or item.get("title") or "").strip()
        else:
            text = str(item or "").strip()
        if text and text not in names:
            names.append(text)
    return names[:4]


def _relationship_delta_text(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    if not isinstance(value, (dict, list)):
        return []
    out: list[str] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        relation = str(item.get("relation") or "").strip()
        if name and relation:
            text = f"{name}（{relation}）"
            if text not in out:
                out.append(text)
    return out[:4]


def _has_visible_contract_violation(result: dict[str, Any]) -> bool:
    diagnostics = result.get("contract_diagnostics")
    if not isinstance(diagnostics, dict):
        return False
    return bool(diagnostics.get("structured_residue") or diagnostics.get("english_residue"))


def _has_visible_authoritative_delta(state_delta: dict[str, Any], narrative: str = "") -> bool:
    """Return true when duplicate text should not replace a visible state event.

    ``world.lore_add`` is intentionally not a blocker here: rule-derived
    replacement chronicle text is built from the same lore facts, so using it is
    how we remove repeated prose without hiding the external-intel update.
    Numeric rule-owned changes only block replacement when the visible prose
    actually claims that same kind of change; otherwise automatic age/stage
    progression would let unrelated repeated prose leak through.
    """
    if not isinstance(state_delta, dict):
        return False
    if _visible_character_delta(state_delta.get("character"), narrative):
        return True
    if _visible_world_delta(state_delta.get("world")):
        return True
    return _visible_meta_delta(state_delta.get("meta"))


def _visible_character_delta(value: Any, narrative: str) -> bool:
    if not isinstance(value, dict):
        return False
    direct_keys = (
        "breakthrough_flags",
        "breakthrough_flags_add",
        "equipment_slots",
        "inventory",
        "inventory_add",
        "relationship_add",
        "status_effects",
        "status_effects_add",
        "techniques",
        "techniques_add",
        "title_add",
    )
    if any(_meaningful_delta_value(value.get(key)) for key in direct_keys):
        return True
    if _meaningful_delta_value(value.get("lifespan")) and _narrative_claims_lifespan(narrative):
        return True
    if _meaningful_delta_value(value.get("attributes")) and _narrative_claims_attributes(narrative):
        return True
    realm_changed = _meaningful_delta_value(value.get("realm")) or _meaningful_delta_value(
        value.get("realm_stage")
    )
    return realm_changed and _narrative_claims_realm_progress(narrative)


def _visible_world_delta(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    keys = (
        "active_quests",
        "active_quests_add",
        "current_scene",
        "discovered_add",
        "discovered_locations",
        "location",
        "npcs_present",
        "npcs_present_add",
        "region",
    )
    return any(_meaningful_delta_value(value.get(key)) for key in keys)


def _visible_meta_delta(value: Any) -> bool:
    return isinstance(value, dict) and (
        _meaningful_delta_value(value.get("breakthrough_result"))
        or bool(value.get("game_over"))
        or bool(value.get("finale"))
    )


def _narrative_claims_lifespan(text: str) -> bool:
    return bool(re.search(r"(?:寿元|寿命|阳寿|延寿|续命)", str(text or "")))


def _narrative_claims_attributes(text: str) -> bool:
    return bool(re.search(r"(?:悟性|根骨|心性|体魄|神魂|气运|资质|道心)", str(text or "")))


def _narrative_claims_realm_progress(text: str) -> bool:
    return bool(
        re.search(
            r"(?:修为|境界|突破|晋升|练气|筑基|金丹|元婴|化神|炼虚|合体|大乘|渡劫|飞升|"
            r"初期|中期|后期|圆满|[一二三四五六七八九十\d]+层)",
            str(text or ""),
        )
    )


def _meaningful_delta_value(value: Any) -> bool:
    if isinstance(value, list):
        return any(item not in ("", None, {}) for item in value)
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None
