"""GameEngine start-flow orchestration and helpers."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .game_engine import GameEngine

from ..agents.contracts import WorldOpeningEnvelopeV1
from .choices import complete_choices, has_visible_english
from .model_result import (
    ModelResultKind,
    ModelResultStatus,
    classify_world_builder_result,
    is_retryable_model_request_failure,
)
from .opening_application import (
    apply_profile_opening_payload,
    apply_profile_world_profile,
    apply_world_builder_generated_session,
    merge_opening_payload,
)
from .profile_opening import profile_opening
from .profile_setup import (
    PROFILE_ATTRIBUTE_TOTAL,
    PROFILE_MANUAL_ATTRIBUTE_MAX,
    PROFILE_MANUAL_ATTRIBUTE_MIN,
    PROFILE_RANDOM_ATTRIBUTE_MAX,
    PROFILE_RANDOM_ATTRIBUTE_MIN,
    PROFILE_REWARDED_ATTRIBUTE_MAX,
    apply_profile_session,
    normalize_profile_attributes,
)
from .render import format_status_bar
from .world_generator import (
    build_world_fallback,
    build_world_prompt,
    is_complete_opening_payload,
    parse_profile_opening_response,
    parse_world_response,
)

log = logging.getLogger(__name__)

START_MODEL_WORLD_ENV = "AGENS_START_MODEL_WORLD"
START_MODEL_OPENING_ENV = "AGENS_START_MODEL_OPENING"
_PROFILE_OPENING_DESCRIPTIVE_FIELDS = (
    "world_name",
    "regions",
    "sects",
    "current_conflicts",
    "initial_situation",
    "world",
)

__all__ = (
    "PROFILE_ATTRIBUTE_TOTAL",
    "PROFILE_MANUAL_ATTRIBUTE_MIN",
    "PROFILE_MANUAL_ATTRIBUTE_MAX",
    "PROFILE_RANDOM_ATTRIBUTE_MIN",
    "PROFILE_RANDOM_ATTRIBUTE_MAX",
    "PROFILE_REWARDED_ATTRIBUTE_MAX",
    "START_MODEL_OPENING_ENV",
    "START_MODEL_WORLD_ENV",
    "StartFlow",
    "apply_profile_opening_payload",
    "apply_profile_session",
    "apply_profile_world_profile",
    "apply_world_builder_generated_session",
    "merge_opening_payload",
    "normalize_profile_attributes",
)


class StartFlow:
    """Owns model and local-template start paths for ``GameEngine``."""

    def __init__(self, engine: GameEngine) -> None:
        self.engine = engine

    def new_game(self, concept: str) -> None:
        """Create a new character via the World Builder agent."""
        engine = self.engine
        session = engine.game_session
        concept = concept.strip()
        if not concept:
            engine.emit("on_info", "已取消。")
            return

        session.reset()
        engine.emit("on_loading", "天道初开，世界生成中...")

        try:
            result = engine.run_agent(
                "world_builder",
                concept,
                session,
                generation_type="new_game",
            )
        except Exception:
            log.exception("world_builder error")
            reason = "世界生成失败（详见日志）"
            engine.emit("on_error", reason)
            if engine.confirm_local_fallback("world_builder_exception", reason):
                engine.set_choices(None, source="world_builder_exception", fallback_notice=True)
            else:
                engine.end_model_failure_run(reason)
            return

        if result.get("llm_error"):
            reason = f"世界生成失败: {result['llm_error']}"
            engine.log_model_result(
                agent="world_builder",
                source="new_game_error",
                status=ModelResultKind.REQUEST_FAILED,
                reason=reason,
                result=result,
            )
            engine.emit("on_error", reason)
            if engine.confirm_local_fallback("world_builder_error", reason):
                engine.set_choices(None, source="world_builder_error", fallback_notice=True)
            else:
                engine.end_model_failure_run(reason)
            return

        world_status, generated = _classify_opening_result(result)
        result, world_status, generated = self._retry_incomplete_opening(
            concept,
            result,
            world_status,
            generated,
            generation_type="new_game",
        )
        engine.log_model_result(
            agent="world_builder",
            source="new_game",
            status=world_status.kind,
            reason=world_status.reason,
            result=result,
        )
        if world_status.kind == ModelResultKind.INCOMPLETE_OUTPUT or not generated:
            engine.emit("on_info", "世界数据为空，请重试。")
            return

        apply_world_builder_generated_session(session, generated)

        opening = generated.get("opening_narrative", result.get("opening_narrative", ""))
        if not opening:
            desc = result.get("world_description", "")
            opening = desc or "世界已生成。"

        if (
            engine.set_choices(
                generated.get("choices"),
                source="world_builder",
                fallback_notice=True,
                require_choice=True,
                reason="世界生成未返回可用选项。",
            )
            is False
            and session.game_over
        ):
            return
        self._emit_opening(opening)

    def start_from_profile(self, profile: dict[str, Any]) -> None:
        """Create a deterministic game from the character form."""
        engine = self.engine
        apply_profile_session(engine.game_session, profile)

        engine.emit("on_loading", "开局生成中...")
        payload = self.generate_opening_payload(profile)
        if engine.game_session.game_over:
            return
        apply_profile_opening_payload(engine.game_session, payload)

        debug_choices = (
            complete_choices(profile.get("choices"), engine.game_session)
            if profile.get("_allow_choice_override")
            else []
        )
        opening = str(
            profile.get("opening_narrative")
            or payload.get("opening_narrative")
            or profile_opening(engine.game_session)
        )
        if (
            engine.set_choices(
                debug_choices or payload.get("choices"),
                source="profile_opening",
                fallback_notice=True,
                require_choice=True,
                reason="开场推演未返回可用选项。",
            )
            is False
            and engine.game_session.game_over
        ):
            return
        self._emit_opening(opening)

    def generate_opening_payload(self, profile: dict[str, Any]) -> dict[str, Any]:
        """Generate one coherent profile opening payload, model or fallback."""
        engine = self.engine
        fallback = build_world_fallback(profile)

        use_model = (
            os.environ.get(START_MODEL_WORLD_ENV) == "1"
            or os.environ.get(START_MODEL_OPENING_ENV) == "1"
        )
        if not use_model:
            return fallback

        if not _engine_has_api_key(engine):
            return self._decline_or_continue(
                fallback, "profile_opening_missing_key", "AGNES_API_KEY 未设置。"
            )

        prompt = build_world_prompt(profile)
        try:
            result = engine.run_agent(
                "world_builder",
                prompt,
                engine.game_session,
                generation_type="profile_opening",
            )
            if is_retryable_model_request_failure(result) and _opening_retry_allowed():
                log.info(
                    "profile opening world_builder request failed with retryable provider error; retrying once"
                )
                retry_result = engine.run_agent(
                    "world_builder",
                    prompt,
                    engine.game_session,
                    generation_type="profile_opening",
                )
                if not retry_result.get("llm_error"):
                    retry_result["retried_after_request_failed"] = True
                result = retry_result
        except Exception:
            log.exception("profile opening world_builder error")
            return self._decline_or_continue(
                fallback, "profile_opening_exception", "开场推演失败（详见日志）。"
            )

        world_status, parsed = _classify_opening_result(result, profile_opening=True)
        result, world_status, parsed = self._retry_incomplete_opening(
            prompt,
            result,
            world_status,
            parsed,
            profile_opening=True,
        )
        engine.log_model_result(
            agent="world_builder",
            source="profile_opening",
            status=world_status.kind,
            reason=world_status.reason,
            result=result,
        )
        if world_status.kind == ModelResultKind.REQUEST_FAILED:
            reason = world_status.reason.replace("世界生成失败", "开场推演失败", 1)
            return self._decline_or_continue(fallback, "profile_opening_error", reason)

        if world_status.kind == ModelResultKind.INCOMPLETE_OUTPUT or not parsed:
            reason = getattr(world_status, "reason", "") or "开场推演数据不可用。"
            return self._decline_or_continue(fallback, "profile_opening_empty", reason)

        return merge_opening_payload(fallback, parsed)

    def _retry_incomplete_opening(
        self,
        prompt: str,
        result: dict[str, Any],
        world_status: ModelResultStatus,
        parsed: dict[str, Any],
        *,
        generation_type: str = "profile_opening",
        profile_opening: bool = False,
    ) -> tuple[dict[str, Any], ModelResultStatus, dict[str, Any]]:
        should_retry = (
            world_status.kind == ModelResultKind.INCOMPLETE_OUTPUT
            and not result.get("retried_after_incomplete_output")
            and _opening_retry_allowed()
        )
        if not should_retry:
            return result, world_status, parsed
        log.info("profile opening contract incomplete; retrying world_builder once")
        retry_prompt = _strict_opening_retry_prompt(prompt)
        try:
            result = self.engine.run_agent(
                "world_builder",
                retry_prompt,
                self.engine.game_session,
                generation_type=generation_type,
            )
            if not result.get("llm_error"):
                result["retried_after_incomplete_output"] = True
        except Exception:
            log.exception("profile opening world_builder incomplete retry failed")
            result = {"generated_data": {}, "llm_error": "开场推演重试失败。"}
        world_status, parsed = _classify_opening_result(result, profile_opening=profile_opening)
        return result, world_status, parsed

    def _decline_or_continue(
        self, fallback: dict[str, Any], source: str, reason: str
    ) -> dict[str, Any]:
        engine = self.engine
        if engine.confirm_local_fallback(source, reason):
            engine.emit("on_info", engine.fallback_notice_for(reason))
            return fallback
        engine.end_model_failure_run(reason)
        return {}

    def _emit_opening(self, opening: str) -> None:
        engine = self.engine
        engine.emit("on_narrative", opening, 0)
        engine.emit("on_character_created", engine.game_session)
        engine.emit("on_status_bar", format_status_bar(engine.game_session))
        engine.record_opening_context(opening)


def _engine_has_api_key(engine: Any) -> bool:
    config = getattr(engine, "model_config", {})
    if isinstance(config, dict) and "api_key_set" in config:
        return bool(config.get("api_key_set"))
    return bool(os.environ.get("AGNES_API_KEY"))


def _classify_opening_result(
    result: dict[str, Any],
    *,
    profile_opening: bool = False,
) -> tuple[ModelResultStatus, dict[str, Any]]:
    status = classify_world_builder_result(result)
    if status.kind == ModelResultKind.REQUEST_FAILED:
        return status, {}
    if profile_opening:
        if (
            str(result.get("provider_transport") or "legacy_tags") in {"json_schema", "json_object"}
            and not result.get("provider_json_envelope_ok")
        ):
            return (
                ModelResultStatus(
                    ModelResultKind.INCOMPLETE_OUTPUT,
                    "开场推演未按 provider JSON 契约返回完整字段。",
                ),
                {},
            )
        parsed = parse_profile_opening_response(result)
        envelope = WorldOpeningEnvelopeV1.from_payload(parsed)
        visible = [
            envelope.opening_narrative,
            envelope.initial_situation_16,
            *envelope.chronicle_0_16,
            *envelope.choices,
        ] if envelope is not None else []
        if (
            envelope is None
            or not 3 <= len(envelope.chronicle_0_16) <= 5
            or any(len(choice) < 4 for choice in envelope.choices)
            or any(has_visible_english(text) for text in visible)
        ):
            return (
                ModelResultStatus(
                    ModelResultKind.INCOMPLETE_OUTPUT,
                    "开场推演缺少完整编年史、初始局势或四个中文选项。",
                ),
                {},
            )
        opening_payload = {
            "opening_narrative": envelope.opening_narrative,
            "chronicle_0_16": list(envelope.chronicle_0_16),
            "initial_situation_16": envelope.initial_situation_16,
            "choices": list(envelope.choices),
        }
        for key in _PROFILE_OPENING_DESCRIPTIVE_FIELDS:
            value = parsed.get(key)
            if value:
                opening_payload[key] = value
        return ModelResultStatus(ModelResultKind.OK), opening_payload
    parsed = parse_world_response(result)
    if not is_complete_opening_payload(parsed):
        return (
            ModelResultStatus(
                ModelResultKind.INCOMPLETE_OUTPUT,
                "开场推演缺少完整角色、动态世界、编年史、初始局势或四个选项。",
            ),
            {},
        )
    return ModelResultStatus(ModelResultKind.OK), parsed


def _strict_opening_retry_prompt(prompt: str) -> str:
    return (
        f"{prompt}\n\n"
        "严格重试要求：上一份开场数据未通过验收。请重新检查 character、world_name、regions、sects、"
        "current_conflicts、fate_hooks、chronicle_0_16、initial_situation、opening_narrative、"
        "choices 以及 world 内的 current_scene、location、region、npcs_present、active_quests、"
        "discovered_locations、lore_facts；所有可见字符串必须是中文，不得含任何英文单词、英文地点名、"
        "标签、占位选项或单独的 A/B/C/D 字母。choices 必须是四条引用本局地点或势力的完整中文行动句。"
    )


def _opening_retry_allowed() -> bool:
    """Optionally suppress opening retries for a one-request evaluation canary."""
    raw_limit = os.environ.get("AGENS_EVALUATION_OPENING_MAX_ATTEMPTS", "").strip()
    if not raw_limit:
        return True
    try:
        return int(raw_limit) > 1
    except ValueError as exc:
        raise ValueError("AGENS_EVALUATION_OPENING_MAX_ATTEMPTS must be an integer") from exc
