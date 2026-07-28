"""Breakthrough-flow orchestration for GameEngine."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .game_engine import GameEngine

from ..game.constants import format_realm_name
from .model_result import (
    ModelResultKind,
    classify_narrator_result,
    is_retryable_model_request_failure,
)
from .pending_model_failure import PendingModelFailureV1
from .render import format_status_bar
from .turn_rules import breakthrough_story_delta

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

        if not self._can_start_breakthrough():
            return

        engine.emit("on_loading", "突破中...")
        previous_realm_label = format_realm_name(session.realm, session.realm_stage)

        breakthrough_delta = engine.realm_system.attempt_breakthrough(session)
        bt_result = breakthrough_delta.get("meta", {}).get("breakthrough_result", "")
        action_text = self._breakthrough_action_text(breakthrough_delta)
        state_delta: dict[str, Any] = self._rule_breakthrough_delta(breakthrough_delta)
        self._ensure_breakthrough_meta(state_delta, bt_result)
        result = self._run_breakthrough_narrator(action_text)
        status = classify_narrator_result(result)
        if status.kind != ModelResultKind.OK:
            engine.create_pending_model_failure(
                stage="breakthrough",
                action=action_text,
                slot="breakthrough",
                frozen_result={
                    "state_delta": state_delta,
                    "breakthrough_result": bt_result,
                    "previous_realm_label": previous_realm_label,
                },
                error_code=_error_code_for_status(status),
            )
            return
        self._apply_accepted_breakthrough(
            action_text,
            state_delta,
            bt_result,
            previous_realm_label,
            result,
        )

    def retry_pending_model(self, pending: PendingModelFailureV1) -> bool:
        """Retry a frozen breakthrough narration without rerolling the result."""
        if pending.stage != "breakthrough":
            return False
        frozen = pending.frozen_result
        state_delta = frozen.get("state_delta")
        bt_result = str(frozen.get("breakthrough_result") or "")
        previous_realm_label = str(frozen.get("previous_realm_label") or "")
        if not isinstance(state_delta, dict):
            raise ValueError("待处理突破缺少冻结规则结果。")
        engine = self.engine
        engine.replace_pending_model_failure(
            pending.with_status("retrying", request_no=pending.request_no + 1)
        )
        result = self._run_breakthrough_narrator(pending.action)
        status = classify_narrator_result(result)
        if status.kind != ModelResultKind.OK:
            engine.replace_pending_model_failure(
                pending.with_status("pending", request_no=pending.request_no + 1)
            )
            engine.emit("on_info", "重试未完成，突破判定仍已冻结，请重新选择处理方式。")
            return False
        self._apply_accepted_breakthrough(
            pending.action,
            state_delta,
            bt_result,
            previous_realm_label,
            result,
        )
        return True

    def resolve_pending_with_local_story(self, pending: PendingModelFailureV1) -> bool:
        """Apply the frozen breakthrough once after an explicit local-story choice."""
        if pending.stage != "breakthrough":
            return False
        frozen = pending.frozen_result
        state_delta = frozen.get("state_delta")
        bt_result = str(frozen.get("breakthrough_result") or "")
        previous_realm_label = str(frozen.get("previous_realm_label") or "")
        if not isinstance(state_delta, dict):
            raise ValueError("待处理突破缺少冻结规则结果。")
        self._apply_accepted_breakthrough(
            pending.action,
            state_delta,
            bt_result,
            previous_realm_label,
            {"narrative": "", "choices": []},
            local_story=True,
        )
        return True

    def _apply_accepted_breakthrough(
        self,
        action_text: str,
        state_delta: dict[str, Any],
        bt_result: str,
        previous_realm_label: str,
        result: dict[str, Any],
        *,
        local_story: bool = False,
    ) -> None:
        raw_delta = result.get("state_delta")
        if isinstance(raw_delta, dict) and raw_delta:
            state_delta.setdefault("meta", {})["model_state_update_ignored"] = True
        narrative = self._apply_breakthrough_result(
            state_delta,
            bt_result,
            str(result.get("narrative") or ""),
            previous_realm_label,
        )
        session = self.engine.game_session
        if local_story and not session.game_over:
            self.engine._enter_local_story("player selected local story", emit_narrative=False)
            state_delta.setdefault("meta", {})["local_story_fallback"] = True
        else:
            self._set_breakthrough_choices(result.get("choices"))
        is_finale = session.finale
        self._record_breakthrough_turn(action_text, narrative, state_delta)
        self.engine.clear_pending_model_failure()
        self._emit_breakthrough_result(bt_result, narrative, is_finale)
        self.engine.emit("on_status_bar", format_status_bar(session))
        if not is_finale:
            self.engine.check_game_over()

    def _can_start_breakthrough(self) -> bool:
        session = self.engine.game_session
        if not session.game_started:
            self.engine.emit("on_info", "尚未开始游戏。")
            return False
        if session.game_over:
            self.engine.emit("on_info", "游戏已结束。")
            return False
        can, reason = self.engine.realm_system.can_attempt_breakthrough(session)
        if not can:
            self.engine.emit("on_info", reason)
            return False
        return True

    def _apply_breakthrough_result(
        self,
        state_delta: dict[str, Any],
        bt_result: str,
        narrative: str,
        previous_realm_label: str,
    ) -> str:
        session = self.engine.game_session
        session.turn_count += 1
        session.realm_turn_count += 1
        self._ensure_breakthrough_meta(state_delta, bt_result)
        session.apply_delta(state_delta)
        narrative = self._coerce_breakthrough_narrative(
            narrative,
            bt_result,
            previous_realm_label=previous_realm_label,
        )
        return self._dedupe_breakthrough_narrative(
            narrative,
            bt_result,
            previous_realm_label=previous_realm_label,
        )

    def _set_breakthrough_choices(self, choices: Any) -> None:
        session = self.engine.game_session
        if session.game_over:
            session.last_choices = []
            return
        used_fallback = self.engine.set_choices(
            choices,
            source="breakthrough_narrator",
            fallback_notice=False,
            require_choice=False,
            reason="突破叙事未返回可用选项。",
        )
        if used_fallback:
            raise ValueError("严格突破叙事未返回四个可用选项。")

    def _run_breakthrough_narrator(self, action_text: str) -> dict[str, Any]:
        engine = self.engine
        try:
            result = engine.run_agent(
                "narrator",
                action_text,
                engine.game_session,
                stream_callback=engine.stream_callback if engine.on_stream_chunk else None,
                repair_incomplete_output=False,
            )
            if is_retryable_model_request_failure(result):
                retry_result = engine.run_agent(
                    "narrator",
                    action_text,
                    engine.game_session,
                    stream_callback=engine.stream_callback if engine.on_stream_chunk else None,
                    repair_incomplete_output=False,
                )
                if not retry_result.get("llm_error"):
                    retry_result["retried_after_request_failed"] = True
                result = retry_result
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

    @staticmethod
    def _rule_breakthrough_delta(breakthrough_delta: dict[str, Any]) -> dict[str, Any]:
        """Copy the RealmSystem result without accepting model state updates."""
        return {
            "character": dict(breakthrough_delta.get("character") or {}),
            "world": dict(breakthrough_delta.get("world") or {}),
            "meta": dict(breakthrough_delta.get("meta") or {}),
        }

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
        self._attach_story_progress(state_delta)
        if bt_result:
            meta.setdefault("breakthrough_result", bt_result)
        if bt_result == "success":
            meta.setdefault("calendar_summary", "破境成功，境界向前推进。")
        elif bt_result == "failure":
            meta.setdefault("calendar_summary", "破境失败，本回合以反噬结果结算。")
        else:
            meta.setdefault("calendar_summary", "完成一次破境判定。")

    def _attach_story_progress(self, state_delta: dict[str, Any]) -> None:
        progress = breakthrough_story_delta(self.engine.game_session)
        world = state_delta.setdefault("world", {})
        if not isinstance(world, dict):
            world = {}
            state_delta["world"] = world
        for key, value in progress["world"].items():
            if key == "lore_add" and isinstance(value, list):
                existing = world.get(key)
                world[key] = list(
                    dict.fromkeys([*(existing if isinstance(existing, list) else []), *value])
                )
            else:
                world[key] = value
        meta = state_delta.setdefault("meta", {})
        if isinstance(meta, dict):
            meta.update(progress["meta"])

    def _record_breakthrough_turn(
        self,
        action_text: str,
        narrative: str,
        state_delta: dict[str, Any],
    ) -> None:
        session = self.engine.game_session
        session.record_turn(action_text, narrative, state_delta)
        if str(getattr(session, "run_seed", "") or "").strip():
            raw_counter = getattr(session, "rule_rng_counter", 0)
            counter = raw_counter if isinstance(raw_counter, int) and not isinstance(raw_counter, bool) else 0
            session.rule_rng_counter = max(0, counter) + 1

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


def _claims_conflicting_realm_stage(text: str, session: Any) -> bool:
    realm = str(getattr(session, "realm", "") or "")
    stage = int(getattr(session, "realm_stage", 1) or 1)
    expected = format_realm_name(realm, stage)
    claims = _realm_stage_claims(text)
    return any(claim != expected for claim in claims)


def _error_code_for_status(status: Any) -> str:
    kind = getattr(status, "kind", "")
    if kind == ModelResultKind.REQUEST_FAILED:
        return "request_failed"
    if kind == ModelResultKind.INCOMPLETE_OUTPUT:
        return "incomplete_output"
    return "llm_error"


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
