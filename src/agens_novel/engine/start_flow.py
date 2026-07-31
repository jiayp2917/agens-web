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
from .pending_model_failure import PendingModelFailureV1
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
            self._hold_world_builder_failure(
                concept,
                ModelResultStatus(ModelResultKind.REQUEST_FAILED, "世界生成失败（详见日志）。"),
            )
            return

        world_status, generated = _classify_opening_result(result)
        result, world_status, generated = self._retry_request_failed_opening(
            concept,
            result,
            world_status,
            generated,
            generation_type="new_game",
        )
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
        if world_status.kind != ModelResultKind.OK or not generated:
            self._hold_world_builder_failure(concept, world_status)
            return
        self._complete_world_builder_opening(generated, result)

    def start_from_profile(self, profile: dict[str, Any]) -> None:
        """Create a deterministic game from the character form."""
        engine = self.engine
        apply_profile_session(engine.game_session, profile)
        fallback = build_world_fallback(profile)
        # Bind the rule-owned world and story before a model call. A failed
        # opening may delay visible prose, but it cannot reroll this binding.
        apply_profile_opening_payload(engine.game_session, fallback)

        engine.emit("on_loading", "开局生成中...")
        payload = self.generate_opening_payload(profile, fallback=fallback)
        if engine.game_session.game_over or engine.pending_model_failure() is not None:
            return
        self._complete_profile_opening(profile, payload)

    def generate_opening_payload(
        self,
        profile: dict[str, Any],
        *,
        fallback: dict[str, Any] | None = None,
        pending: PendingModelFailureV1 | None = None,
    ) -> dict[str, Any]:
        """Generate one coherent profile opening payload, model or fallback."""
        engine = self.engine
        fallback = fallback or build_world_fallback(profile)

        if not _engine_has_api_key(engine):
            self._hold_profile_opening_failure(
                profile,
                fallback,
                ModelResultStatus(ModelResultKind.REQUEST_FAILED, "开场推演服务未配置。"),
                pending=pending,
            )
            return {}

        prompt = build_world_prompt(profile)
        try:
            result = engine.run_agent(
                "world_builder",
                prompt,
                engine.game_session,
                generation_type="profile_opening",
            )
            if is_retryable_model_request_failure(result):
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
            self._hold_profile_opening_failure(
                profile,
                fallback,
                ModelResultStatus(ModelResultKind.REQUEST_FAILED, "开场推演失败（详见日志）。"),
                pending=pending,
            )
            return {}

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
            self._hold_profile_opening_failure(profile, fallback, world_status, pending=pending)
            return {}

        if world_status.kind == ModelResultKind.INCOMPLETE_OUTPUT or not parsed:
            self._hold_profile_opening_failure(profile, fallback, world_status, pending=pending)
            return {}

        return merge_opening_payload(fallback, parsed)

    def _complete_world_builder_opening(
        self,
        generated: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        session = self.engine.game_session
        apply_world_builder_generated_session(session, generated)
        opening = str(generated.get("opening_narrative") or result.get("opening_narrative") or "")
        if not opening:
            opening = str(result.get("world_description") or "世界已生成。")
        used_fallback = self.engine.set_choices(
            generated.get("choices"),
            source="world_builder",
            fallback_notice=False,
            require_choice=False,
            reason="世界生成未返回可用选项。",
        )
        if used_fallback:
            raise ValueError("严格世界开局未返回四个可用选项。")
        self._emit_opening(opening)

    def _hold_world_builder_failure(
        self,
        concept: str,
        status: ModelResultStatus,
        *,
        pending: PendingModelFailureV1 | None = None,
    ) -> None:
        if pending is not None:
            self.engine.replace_pending_model_failure(
                pending.with_status("pending", request_no=pending.request_no + 1)
            )
            return
        self.engine.create_pending_model_failure(
            stage="opening",
            action="new_game",
            slot="opening",
            frozen_result={"concept": concept},
            error_code=_error_code_for_status(status),
        )

    def retry_pending_model(self, pending: PendingModelFailureV1) -> bool:
        """Retry a frozen profile-opening request without rebinding its world."""
        if pending.stage != "opening":
            return False
        frozen = pending.frozen_result
        concept = frozen.get("concept")
        if isinstance(concept, str) and concept:
            return self._retry_world_builder_opening(pending, concept)
        profile_value = frozen.get("profile")
        fallback_value = frozen.get("fallback")
        if not isinstance(profile_value, dict) or not isinstance(fallback_value, dict):
            raise ValueError("待处理开局缺少冻结配置。")
        self.engine.replace_pending_model_failure(
            pending.with_status("retrying", request_no=pending.request_no + 1)
        )
        payload = self.generate_opening_payload(
            profile_value,
            fallback=fallback_value,
            pending=pending,
        )
        if not payload:
            self.engine.emit("on_info", "重试未完成，开局绑定保持不变，请重新选择处理方式。")
            return False
        self._complete_profile_opening(profile_value, payload)
        self.engine.clear_pending_model_failure()
        return True

    def _retry_world_builder_opening(
        self,
        pending: PendingModelFailureV1,
        concept: str,
    ) -> bool:
        engine = self.engine
        engine.replace_pending_model_failure(
            pending.with_status("retrying", request_no=pending.request_no + 1)
        )
        try:
            result = engine.run_agent(
                "world_builder",
                concept,
                engine.game_session,
                generation_type="new_game",
            )
        except Exception:
            log.exception("world_builder retry error")
            self._hold_world_builder_failure(
                concept,
                ModelResultStatus(ModelResultKind.REQUEST_FAILED, "世界生成重试失败。"),
                pending=pending,
            )
            return False
        status, generated = _classify_opening_result(result)
        result, status, generated = self._retry_request_failed_opening(
            concept,
            result,
            status,
            generated,
            generation_type="new_game",
        )
        result, status, generated = self._retry_incomplete_opening(
            concept,
            result,
            status,
            generated,
            generation_type="new_game",
        )
        engine.log_model_result(
            agent="world_builder",
            source="new_game_retry",
            status=status.kind,
            reason=status.reason,
            result=result,
        )
        if status.kind != ModelResultKind.OK or not generated:
            self._hold_world_builder_failure(concept, status, pending=pending)
            engine.emit("on_info", "重试未完成，开局尚未建立，请重新选择处理方式。")
            return False
        self._complete_world_builder_opening(generated, result)
        engine.clear_pending_model_failure()
        return True

    def _retry_request_failed_opening(
        self,
        prompt: str,
        result: dict[str, Any],
        world_status: ModelResultStatus,
        parsed: dict[str, Any],
        *,
        generation_type: str,
        profile_opening: bool = False,
    ) -> tuple[dict[str, Any], ModelResultStatus, dict[str, Any]]:
        if (
            world_status.kind != ModelResultKind.REQUEST_FAILED
            or not is_retryable_model_request_failure(result)
        ):
            return result, world_status, parsed
        try:
            retry_result = self.engine.run_agent(
                "world_builder",
                prompt,
                self.engine.game_session,
                generation_type=generation_type,
            )
        except Exception:
            log.exception("world_builder request retry failed")
            return {
                "generated_data": {},
                "llm_error": "开场推演重试失败。",
            }, ModelResultStatus(ModelResultKind.REQUEST_FAILED, "开场推演重试失败。"), {}
        if not retry_result.get("llm_error"):
            retry_result["retried_after_request_failed"] = True
        retry_status, retry_parsed = _classify_opening_result(
            retry_result,
            profile_opening=profile_opening,
        )
        return retry_result, retry_status, retry_parsed

    def resolve_pending_with_local_story(self, pending: PendingModelFailureV1) -> bool:
        """Apply the frozen opening and enter local story after player consent."""
        if pending.stage != "opening":
            return False
        frozen = pending.frozen_result
        concept = frozen.get("concept")
        if isinstance(concept, str) and concept:
            profile = {"char_name": concept}
            fallback = build_world_fallback(profile)
            apply_profile_session(self.engine.game_session, profile)
            apply_profile_opening_payload(self.engine.game_session, fallback)
            self._complete_profile_opening(profile, fallback, local_story=True)
            self.engine.clear_pending_model_failure()
            return True
        profile_value = frozen.get("profile")
        fallback_value = frozen.get("fallback")
        if not isinstance(profile_value, dict) or not isinstance(fallback_value, dict):
            raise ValueError("待处理开局缺少冻结配置。")
        self._complete_profile_opening(profile_value, fallback_value, local_story=True)
        self.engine.clear_pending_model_failure()
        return True

    def _hold_profile_opening_failure(
        self,
        profile: dict[str, Any],
        fallback: dict[str, Any],
        status: ModelResultStatus,
        *,
        pending: PendingModelFailureV1 | None = None,
    ) -> None:
        frozen_result = {"profile": dict(profile), "fallback": dict(fallback)}
        if pending is not None:
            self.engine.replace_pending_model_failure(
                pending.with_status("pending", request_no=pending.request_no + 1)
            )
            return
        self.engine.create_pending_model_failure(
            stage="opening",
            action="profile_opening",
            slot="opening",
            frozen_result=frozen_result,
            error_code=_error_code_for_status(status),
        )

    def _complete_profile_opening(
        self,
        profile: dict[str, Any],
        payload: dict[str, Any],
        *,
        local_story: bool = False,
    ) -> None:
        engine = self.engine
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
        if local_story:
            engine._enter_local_story("player selected local story", emit_narrative=False)
        else:
            used_fallback = engine.set_choices(
                debug_choices or payload.get("choices"),
                source="profile_opening",
                fallback_notice=False,
                require_choice=False,
                reason="开场推演未返回可用选项。",
            )
            if used_fallback:
                raise ValueError("严格开场未返回四个可用选项。")
        self._emit_opening(opening)

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
            str(result.get("response_mode") or result.get("provider_transport") or "json_object")
            not in {"json_schema", "json_object"}
            or result.get("provider_json_envelope_ok") is not True
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


def _error_code_for_status(status: ModelResultStatus) -> str:
    if status.kind == ModelResultKind.REQUEST_FAILED:
        return "request_failed"
    if status.kind == ModelResultKind.INCOMPLETE_OUTPUT:
        return "incomplete_output"
    return "llm_error"
