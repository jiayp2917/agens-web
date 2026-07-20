"""Breakthrough-flow orchestration for GameEngine."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .game_engine import GameEngine

from ..game.constants import format_realm_name
from .model_result import ModelResultKind, classify_judge_result, classify_narrator_result
from .render import format_status_bar

log = logging.getLogger(__name__)
_BREAKTHROUGH_FAILURE_WORDS = (
    "修为尽废",
    "修为未复",
    "重伤垂死",
    "未能突破",
    "突破失败",
    "功亏一篑",
    "破境未成",
    "未能破境",
    "走火入魔",
    "遭反噬",
    "灵机反噬",
    "经脉寸断",
    "生死未卜",
)
_BREAKTHROUGH_SUCCESS_WORDS = ("突破成功", "功成", "踏入", "晋入", "进阶", "破境已成")
_QI_STAGE_CLAIM_RE = re.compile(r"练气\s*(?:第)?\s*([1-9一二三四五六七八九])\s*层")
_REALM_PHASE_CLAIM_RE = re.compile(r"(筑基|金丹|元婴|化神|合体|大乘|渡劫)\s*(初期|中期|后期|圆满)")
_REALM_TRANSITION_TARGET_RE = re.compile(
    r"(?:突破至|突破到|踏入|迈入|晋入|晋升至|升至)\s*(筑基|金丹|元婴|化神|合体|大乘|渡劫|飞升)"
)
_EXPLICIT_TIME_SPAN_RE = re.compile(r"(?:\d+|[一二三四五六七八九十百千万两]+)\s*(?:年|载)")
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


def _chronicle_key(text: str) -> str:
    return re.sub(r"[\s，,。！？!?；;：:]", "", str(text or ""))


class BreakthroughFlow:
    """Owns realm breakthrough progression for ``GameEngine``."""

    def __init__(self, engine: GameEngine) -> None:
        self.engine = engine

    def attempt_breakthrough(self) -> None:
        """Attempt a realm breakthrough while preserving GameEngine callbacks."""
        engine = self.engine
        session = engine.game_session

        if not session.game_started:
            engine.emit("on_info", "尚未开始游戏。")
            return

        if session.game_over:
            engine.emit("on_info", "游戏已结束。")
            return

        can, reason = engine.realm_system.can_attempt_breakthrough(session)
        if not can:
            engine.emit("on_info", reason)
            return

        engine.emit("on_loading", "突破中...")
        previous_realm_label = format_realm_name(session.realm, session.realm_stage)

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
            log.info(
                "breakthrough narrator unavailable after rule settlement: %s",
                result.get("llm_error"),
            )
            state_delta = breakthrough_delta
        else:
            narrative = str(result.get("narrative") or "")
            raw_delta = result.get("state_delta", {})
            state_delta = raw_delta if isinstance(raw_delta, dict) else {}
            choices = result.get("choices")
            state_delta = self._merge_breakthrough_delta(state_delta, breakthrough_delta, bt_result)

        judged_delta = self._judge_breakthrough_delta(action_text, narrative, state_delta)
        if judged_delta is None:
            return
        state_delta = judged_delta
        state_delta = self._merge_breakthrough_delta(
            state_delta,
            breakthrough_delta,
            bt_result,
        )

        session.turn_count += 1
        session.realm_turn_count += 1
        self._ensure_breakthrough_meta(state_delta, bt_result)
        session.apply_delta(state_delta)
        narrative = self._coerce_breakthrough_narrative(
            narrative,
            bt_result,
            previous_realm_label=previous_realm_label,
        )
        narrative = self._dedupe_breakthrough_narrative(
            narrative,
            bt_result,
            previous_realm_label=previous_realm_label,
        )
        is_finale = session.finale
        if session.game_over:
            session.last_choices = []
        else:
            engine.set_choices(
                choices,
                source="breakthrough_narrator",
                fallback_notice=False,
                require_choice=False,
                reason="突破叙事未返回可用选项。",
            )
        self._record_breakthrough_turn(action_text, narrative, state_delta)
        self._emit_breakthrough_result(bt_result, narrative, is_finale)

        engine.emit("on_status_bar", format_status_bar(session))

        if is_finale:
            return

        if engine.check_game_over():
            return

    def _run_breakthrough_narrator(self, action_text: str) -> dict[str, Any] | None:
        engine = self.engine
        try:
            result = engine.run_agent(
                "narrator",
                action_text,
                engine.game_session,
                stream_callback=engine.stream_callback if engine.on_stream_chunk else None,
                repair_incomplete_output=False,
            )
            status = classify_narrator_result(result)
            if status.kind == ModelResultKind.INCOMPLETE_OUTPUT:
                retry_input = (
                    f"{action_text}\n\n"
                    "[输出契约提醒：必须返回非空突破编年史、合法状态对象，以及四个非空、"
                    "互不重复、依次对应稳妥/机遇/风险/气运的中文行动选项；"
                    "突破成败仍以规则判定为准，并继续遵守当前传输格式。]"
                )
                retry_result = engine.run_agent(
                    "narrator",
                    retry_input,
                    engine.game_session,
                    stream_callback=engine.stream_callback if engine.on_stream_chunk else None,
                    repair_incomplete_output=False,
                )
                if not retry_result.get("llm_error"):
                    retry_result["retried_after_incomplete_output"] = True
                result = retry_result
        except Exception:
            log.exception("breakthrough narrator error")
            result = {
                "narrative": "",
                "state_delta": {},
                "choices": [],
                "llm_error": "突破叙事失败",
            }
        status = classify_narrator_result(result)
        engine.log_model_result(
            agent="narrator",
            source="breakthrough",
            status=status.kind,
            reason=status.reason,
            result=result,
        )
        return result

    def _merge_breakthrough_delta(
        self,
        state_delta: dict[str, Any],
        breakthrough_delta: dict[str, Any],
        bt_result: str,
    ) -> dict[str, Any]:
        if bt_result not in {"success", "failure"}:
            return state_delta
        sanitized = self.engine.sanitize_action_delta(state_delta)
        world = sanitized.get("world") if isinstance(sanitized, dict) else None
        merged: dict[str, Any] = {}
        if isinstance(world, dict) and world:
            merged["world"] = world
        merged["character"] = dict(breakthrough_delta.get("character") or {})
        merged["meta"] = dict(breakthrough_delta.get("meta") or {})
        return merged

    def _breakthrough_action_text(self, breakthrough_delta: dict[str, Any]) -> str:
        session = self.engine.game_session
        meta_value = breakthrough_delta.get("meta")
        meta: dict[str, Any] = meta_value if isinstance(meta_value, dict) else {}
        result = str(meta.get("breakthrough_result") or "")
        target = str(
            meta.get("new_realm")
            or self.engine.realm_system.get_next_realm(session.realm)
            or "更高境界"
        )
        if result == "success":
            source_label = format_realm_name(session.realm, session.realm_stage)
            target_label = format_realm_name(target, 1)
            return f"规则判定：本次突破成功，从{source_label}突破至{target_label}。请只写成功叙事。"
        if result == "failure":
            effect = str(meta.get("status_effect_add") or "走火入魔")
            return f"规则判定：本次突破失败，反噬结果为{effect}。请只写失败叙事，不得提升境界。"
        return f"尝试从{session.realm}突破到更高境界"

    def _coerce_breakthrough_narrative(
        self,
        narrative: str,
        bt_result: str,
        *,
        previous_realm_label: str = "",
    ) -> str:
        text = re.sub(r"\s+", " ", str(narrative or "")).strip()
        if _EXPLICIT_TIME_SPAN_RE.search(text):
            text = ""
        if bt_result == "success":
            if (
                not text
                or any(word in text for word in _BREAKTHROUGH_FAILURE_WORDS)
                or _claims_conflicting_breakthrough_transition(
                    text,
                    previous_realm_label,
                    self.engine.game_session,
                )
            ):
                current_label = format_realm_name(
                    self.engine.game_session.realm,
                    self.engine.game_session.realm_stage,
                )
                if previous_realm_label and previous_realm_label != current_label:
                    return f"破境已成，自{previous_realm_label}踏入{current_label}。"
                return "破境已成，灵机贯通，境界向前推进。"
        elif bt_result == "failure":
            if (
                not text
                or any(word in text for word in _BREAKTHROUGH_SUCCESS_WORDS)
                or _claims_conflicting_realm_stage(text, self.engine.game_session)
            ):
                return "破境未成，灵机反噬，需先稳住根基再图后续。"
        return text

    def _dedupe_breakthrough_narrative(
        self,
        narrative: str,
        bt_result: str,
        *,
        previous_realm_label: str,
    ) -> str:
        session = self.engine.game_session
        history = session.turn_history
        narrative_key = _chronicle_key(narrative)
        seen_in_history = any(
            _chronicle_key(str(entry.get("narrative") or "")) == narrative_key
            for entry in history[-60:]
            if isinstance(entry, dict)
        )
        if not narrative_key or not (seen_in_history or session.has_recent_narrative(narrative)):
            return narrative
        if bt_result == "success":
            current_label = format_realm_name(
                self.engine.game_session.realm,
                self.engine.game_session.realm_stage,
            )
            if previous_realm_label and previous_realm_label != current_label:
                return f"破境已成，自{previous_realm_label}踏入{current_label}。"
            return f"破境已成，已立于{current_label}，此前积累终于兑现。"
        if bt_result == "failure":
            current_label = format_realm_name(
                self.engine.game_session.realm,
                self.engine.game_session.realm_stage,
            )
            variants = (
                "反噬已落，需先稳住根基再图后续。",
                "灵机散乱，尚须调息后再觅良机。",
                "旧患未消，此刻不宜再强行冲关。",
                "道基受震，应先收束心神以免伤势加深。",
            )
            return f"破境未成，{current_label}{variants[self.engine.game_session.turn_count % len(variants)]}"
        return "本次冲关未能改写既有局势，修行仍须另觅时机。"

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
            judge_result = engine.run_agent(
                "judge",
                action_text,
                engine.game_session,
                narrative=narrative,
                state_delta=state_delta,
            )
            judge_status = classify_judge_result(judge_result)
            engine.log_model_result(
                agent="judge",
                source="breakthrough",
                status=judge_status.kind,
                reason=judge_status.reason,
                result=judge_result,
            )
            if judge_result.get("llm_error"):
                reason = f"突破审判失败: {judge_result['llm_error']}"
                if not engine.confirm_local_fallback("breakthrough_judge_error", reason):
                    engine.end_model_failure_run(reason)
                    return None
                judge_result = {"approved": False, "corrected_delta": {}}
            if judge_result.get("approved") is False:
                corrected = judge_result.get("corrected_delta", {})
                if corrected and not _conflicts_with_breakthrough_result(corrected, state_delta):
                    state_delta = corrected
        except Exception:
            log.exception("breakthrough judge error")
            reason = "突破审判失败（详见日志）"
            failed_result = {"llm_error": reason}
            judge_status = classify_judge_result(failed_result)
            engine.log_model_result(
                agent="judge",
                source="breakthrough",
                status=judge_status.kind,
                reason=judge_status.reason,
                result=failed_result,
            )
            if not engine.confirm_local_fallback("breakthrough_judge_exception", reason):
                engine.end_model_failure_run(reason)
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
                engine.emit(
                    "on_narrative",
                    narrative or "天地轰鸣，金光万丈！你超脱凡尘，飞升成仙！",
                    session.turn_count,
                )
                engine.emit("on_finale", "飞升成仙，超脱凡尘，修真之路圆满。")
            else:
                engine.emit(
                    "on_narrative",
                    narrative or "突破成功！天地灵气涌动，境界提升！",
                    session.turn_count,
                )
        elif bt_result == "failure":
            engine.emit("on_narrative", narrative or "突破失败...修为受损。", session.turn_count)
        else:
            engine.emit("on_narrative", narrative, session.turn_count)


def _conflicts_with_breakthrough_result(
    corrected: dict[str, Any], original: dict[str, Any]
) -> bool:
    original_meta_value = original.get("meta")
    corrected_meta_value = corrected.get("meta")
    original_meta: dict[str, Any] = (
        original_meta_value if isinstance(original_meta_value, dict) else {}
    )
    corrected_meta: dict[str, Any] = (
        corrected_meta_value if isinstance(corrected_meta_value, dict) else {}
    )
    original_result = original_meta.get("breakthrough_result")
    if not original_result:
        return False
    if corrected_meta.get("breakthrough_result") != original_result:
        return True

    original_character_value = original.get("character")
    corrected_character_value = corrected.get("character")
    original_character: dict[str, Any] = (
        original_character_value if isinstance(original_character_value, dict) else {}
    )
    corrected_character: dict[str, Any] = (
        corrected_character_value if isinstance(corrected_character_value, dict) else {}
    )
    for key in ("realm", "realm_stage", "lifespan"):
        if key in corrected_character and corrected_character.get(key) != original_character.get(
            key
        ):
            return True
    for key in ("finale", "game_over", "game_over_reason", "new_realm"):
        if key in corrected_meta and corrected_meta.get(key) != original_meta.get(key):
            return True
    return False


def _claims_conflicting_realm_stage(text: str, session: Any) -> bool:
    realm = str(getattr(session, "realm", "") or "")
    stage = int(getattr(session, "realm_stage", 1) or 1)
    expected = format_realm_name(realm, stage)
    claims = _realm_stage_claims(text)
    return any(claim != expected for claim in claims)


def _claims_conflicting_breakthrough_transition(
    text: str,
    previous_realm_label: str,
    session: Any,
) -> bool:
    current_realm = str(getattr(session, "realm", "") or "")
    current_stage = int(getattr(session, "realm_stage", 1) or 1)
    current_label = format_realm_name(current_realm, current_stage)
    allowed_labels = {label for label in (previous_realm_label, current_label) if label}
    if any(claim not in allowed_labels for claim in _realm_stage_claims(text)):
        return True
    return any(
        target_realm != current_realm
        for target_realm in _REALM_TRANSITION_TARGET_RE.findall(str(text or ""))
    )


def _realm_stage_claims(text: str) -> list[str]:
    claims: list[str] = []
    for value in _QI_STAGE_CLAIM_RE.findall(str(text or "")):
        claim_stage = int(value) if value.isdigit() else _CHINESE_STAGE_VALUES.get(value, 0)
        if claim_stage:
            claims.append(format_realm_name("练气", claim_stage))
    claims.extend(
        f"{claim_realm}{phase}"
        for claim_realm, phase in _REALM_PHASE_CLAIM_RE.findall(str(text or ""))
    )
    return claims
