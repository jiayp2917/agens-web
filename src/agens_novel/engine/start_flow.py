"""GameEngine start-flow orchestration and helpers."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .game_engine import GameEngine

from ..game.constants import (
    ATTRIBUTE_MAX,
    ATTRIBUTE_KEYS,
    ATTRIBUTE_MIN,
    ATTRIBUTE_TOTAL,
    DIFFICULTY_OPTIONS,
    FAMILY_BACKGROUNDS,
    SPIRIT_ROOTS,
    TALENT_OPTIONS,
    compute_starting_lifespan,
    normalize_attribute_value,
)
from ..session.game_session import GameSession
from .choices import complete_choices
from .model_result import ModelResultKind, ModelResultStatus, classify_world_builder_result
from .profile_opening import profile_default_world, profile_opening
from .render import format_status_bar
from .world_generator import (
    build_world_fallback,
    build_world_prompt,
    is_complete_opening_payload,
    parse_world_response,
)

log = logging.getLogger(__name__)

START_MODEL_WORLD_ENV = "AGENS_START_MODEL_WORLD"
START_MODEL_OPENING_ENV = "AGENS_START_MODEL_OPENING"
PROFILE_ATTRIBUTE_TOTAL = ATTRIBUTE_TOTAL
PROFILE_MANUAL_ATTRIBUTE_MIN = 2
PROFILE_MANUAL_ATTRIBUTE_MAX = 8
PROFILE_RANDOM_ATTRIBUTE_MIN = ATTRIBUTE_MIN
PROFILE_RANDOM_ATTRIBUTE_MAX = ATTRIBUTE_MAX
PROFILE_REWARDED_ATTRIBUTE_MAX = ATTRIBUTE_MAX
_PROFILE_ATTRIBUTE_DEFAULT = PROFILE_ATTRIBUTE_TOTAL // len(ATTRIBUTE_KEYS)
_ALLOW_LEGACY_BONUS_ATTRIBUTES = "_allow_legacy_bonus_attributes"


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

        generated = result.get("generated_data", {})
        world_status = classify_world_builder_result(result)
        engine.log_model_result(
            agent="world_builder",
            source="new_game",
            status=world_status.kind,
            reason=world_status.reason,
            result=result,
        )
        if not generated:
            engine.emit("on_info", "世界数据为空，请重试。")
            return

        apply_world_builder_generated_session(session, generated)

        opening = generated.get("opening_narrative", result.get("opening_narrative", ""))
        if not opening:
            desc = result.get("world_description", "")
            opening = desc or "世界已生成。"

        if engine.set_choices(
            generated.get("choices"),
            source="world_builder",
            fallback_notice=True,
            require_choice=True,
            reason="世界生成未返回可用选项。",
        ) is False and session.game_over:
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

        debug_choices = complete_choices(profile.get("choices"), engine.game_session) if profile.get("_allow_choice_override") else []
        opening = str(profile.get("opening_narrative") or payload.get("opening_narrative") or profile_opening(engine.game_session))
        if engine.set_choices(
            debug_choices or payload.get("choices"),
            source="profile_opening",
            fallback_notice=True,
            require_choice=True,
            reason="开场推演未返回可用选项。",
        ) is False and engine.game_session.game_over:
            return
        self._emit_opening(opening)

    def generate_opening_payload(self, profile: dict[str, Any]) -> dict[str, Any]:
        """Generate one coherent profile opening payload, model or fallback."""
        engine = self.engine
        fallback = build_world_fallback(profile)

        def decline_or_continue(source: str, reason: str) -> dict[str, Any]:
            """On model failure: return fallback if the user accepts, else end the run."""
            if engine.confirm_local_fallback(source, reason):
                engine.emit("on_info", engine.fallback_notice_for(reason))
                return fallback
            engine.end_model_failure_run(reason)
            return {}

        use_model = (
            os.environ.get(START_MODEL_WORLD_ENV) == "1"
            or os.environ.get(START_MODEL_OPENING_ENV) == "1"
        )
        if not use_model:
            return fallback

        if not _engine_has_api_key(engine):
            return decline_or_continue("profile_opening_missing_key", "AGNES_API_KEY 未设置。")

        prompt = build_world_prompt(profile)
        try:
            result = engine.run_agent(
                "world_builder",
                prompt,
                engine.game_session,
                generation_type="profile_opening",
            )
        except Exception:
            log.exception("profile opening world_builder error")
            return decline_or_continue("profile_opening_exception", "开场推演失败（详见日志）。")

        world_status = classify_world_builder_result(result)
        parsed = parse_world_response(result) if world_status.kind != ModelResultKind.REQUEST_FAILED else {}
        if world_status.kind == ModelResultKind.OK and not is_complete_opening_payload(parsed):
            world_status = ModelResultStatus(
                ModelResultKind.INCOMPLETE_OUTPUT,
                "开场推演缺少动态世界、编年史、初始局势或四个选项。",
            )
            parsed = {}
        engine.log_model_result(
            agent="world_builder",
            source="profile_opening",
            status=world_status.kind,
            reason=world_status.reason,
            result=result,
        )
        if world_status.kind == ModelResultKind.REQUEST_FAILED:
            reason = world_status.reason.replace("世界生成失败", "开场推演失败", 1)
            return decline_or_continue("profile_opening_error", reason)

        if world_status.kind == ModelResultKind.INCOMPLETE_OUTPUT or not parsed:
            reason = getattr(world_status, "reason", "") or "开场推演数据不可用。"
            return decline_or_continue("profile_opening_empty", reason)

        return merge_opening_payload(fallback, parsed)

    def _emit_opening(self, opening: str) -> None:
        engine = self.engine
        engine.emit("on_narrative", opening, 0)
        engine.emit("on_character_created", engine.game_session)
        engine.emit("on_status_bar", format_status_bar(engine.game_session))
        engine.record_opening_context(opening)


def apply_world_builder_generated_session(
    session: GameSession,
    generated: dict[str, Any],
) -> None:
    """Apply World Builder character/world output to the active session."""
    char_data = generated.get("character", {})
    if char_data:
        session.char_name = char_data.get("name", "无名")
        session.realm = char_data.get("realm", "练气")
        session.realm_stage = char_data.get("realm_stage", 1)
        session.spirit_root = char_data.get("spirit_root", "")
        session.spirit_root_grade = char_data.get("spirit_root_grade", "")
        session.age = char_data.get("age", session.age)
        session.talent = char_data.get("talent", session.talent)
        session.family_background = char_data.get("family_background", session.family_background)
        session.difficulty = char_data.get("difficulty", session.difficulty)
        attrs = char_data.get("attributes")
        if isinstance(attrs, dict):
            merged_attrs = dict(session.attributes)
            for key, value in attrs.items():
                if key in merged_attrs and isinstance(value, int) and not isinstance(value, bool):
                    merged_attrs[key] = normalize_attribute_value(value)
            session.attributes = merged_attrs
        session.techniques = char_data.get("techniques", [])
        session.inventory = char_data.get("inventory", [])
        session.status_effects = char_data.get("status_effects", [])
        session.lifespan = int(char_data.get("lifespan") or compute_starting_lifespan(
            session.realm,
            attributes=session.attributes,
            talent=session.talent,
            difficulty=session.difficulty,
        ))
        if "equipment_slots" in char_data:
            session.equipment_slots = char_data["equipment_slots"]

    world_data = generated.get("world", {})
    if world_data:
        session.current_scene = world_data.get("current_scene", "")
        session.location = world_data.get("location", "")
        session.region = world_data.get("region", "")
        session.npcs_present = world_data.get("npcs_present", [])
        session.active_quests = world_data.get("active_quests", [])
        session.discovered_locations = world_data.get("discovered_locations", [])
        session.lore_facts = world_data.get("lore_facts", [])
        session.day_count = world_data.get("day_count", 1)

    session.game_started = True
    session.turn_count = 0


def apply_profile_session(session: GameSession, profile: dict[str, Any]) -> None:
    """Initialize a deterministic session from the character form profile."""
    attrs = normalize_profile_attributes(
        profile.get("attributes", {}),
        random_mode=bool(profile.get("randomize_attributes")),
        allow_legacy_bonus=bool(profile.get(_ALLOW_LEGACY_BONUS_ATTRIBUTES)),
    )

    session.reset()
    session.game_started = True
    session.game_over = False
    session.turn_count = 0
    session.char_name = str(profile.get("char_name") or "无名")
    session.realm = "练气"
    session.realm_stage = 1
    session.age = int(profile.get("age") or 16)
    session.talent = str(profile.get("talent") or TALENT_OPTIONS[0])
    session.spirit_root = str(profile.get("spirit_root") or SPIRIT_ROOTS[0]["name"])
    session.spirit_root_grade = str(profile.get("spirit_root_grade") or "")
    session.family_background = str(profile.get("family_background") or FAMILY_BACKGROUNDS[0])
    session.difficulty = str(profile.get("difficulty") or DIFFICULTY_OPTIONS[1])
    session.attributes = attrs
    session.lifespan = compute_starting_lifespan(
        session.realm,
        attributes=attrs,
        talent=session.talent,
        difficulty=session.difficulty,
        extra_lifespan=int(profile.get("extra_lifespan") or 0),
    )
    session.techniques = list(profile.get("techniques") or [{"name": "基础吐纳术", "level": 1, "type": "内功"}])
    session.inventory = list(profile.get("inventory") or [{"name": "粗布道袍", "quantity": 1, "type": "防具"}])
    default_scene, default_location, default_region, default_lore = profile_default_world(profile)
    session.current_scene = str(profile.get("current_scene") or default_scene)
    session.location = str(profile.get("location") or default_location)
    session.region = str(profile.get("region") or default_region)
    session.discovered_locations = [session.location]
    session.lore_facts = [default_lore]


def normalize_profile_attributes(
    incoming_attrs: Any,
    *,
    random_mode: bool = False,
    allow_legacy_bonus: bool = False,
) -> dict[str, int]:
    """Validate and normalize character-creation attributes.

    GAME_MODE_SPEC section 4.1 defines the public profile contract: manual
    creation uses six attributes, each 2-8, with a fixed total of 30. Random
    creation is normalized before this function is called and may use 0-10,
    still totaling 30. Account legacy bonuses are applied after the public
    input is validated, so service code may opt into a post-bonus total above
    30 while each attribute remains on the 0-10 gameplay scale.
    """
    if not incoming_attrs:
        return {key: _PROFILE_ATTRIBUTE_DEFAULT for key in ATTRIBUTE_KEYS}
    if not isinstance(incoming_attrs, dict):
        raise ValueError("attributes must be an object")

    missing = [key for key in ATTRIBUTE_KEYS if key not in incoming_attrs]
    unknown = [str(key) for key in incoming_attrs if key not in ATTRIBUTE_KEYS]
    if missing or unknown:
        raise ValueError("attributes must contain exactly the six v5 keys")

    attrs: dict[str, int] = {}
    for key in ATTRIBUTE_KEYS:
        value = incoming_attrs[key]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("attribute values must be integers")
        attrs[key] = value

    total = sum(attrs.values())
    if allow_legacy_bonus:
        if total < PROFILE_ATTRIBUTE_TOTAL:
            raise ValueError("attributes must not drop below the 30 point pool")
        for value in attrs.values():
            if value < PROFILE_RANDOM_ATTRIBUTE_MIN or value > PROFILE_REWARDED_ATTRIBUTE_MAX:
                raise ValueError("legacy-bonus attributes must stay between 0 and 10")
        return attrs

    if total != PROFILE_ATTRIBUTE_TOTAL:
        raise ValueError("manual attributes must sum to 30")

    if random_mode:
        random_range_ok = all(
            PROFILE_RANDOM_ATTRIBUTE_MIN <= value <= PROFILE_RANDOM_ATTRIBUTE_MAX
            for value in attrs.values()
        )
        if not random_range_ok:
            raise ValueError("random attributes must stay between 0 and 10")
        return attrs

    manual_range_ok = all(
        PROFILE_MANUAL_ATTRIBUTE_MIN <= value <= PROFILE_MANUAL_ATTRIBUTE_MAX
        for value in attrs.values()
    )
    if not manual_range_ok:
        raise ValueError("manual attributes must stay between 2 and 8")
    return attrs


def apply_profile_world_profile(session: GameSession, world_profile: dict[str, Any]) -> None:
    """Attach generated world-profile fields to a profile-started session."""
    session.world_profile = world_profile
    if world_profile.get("world_name"):
        session.region = world_profile["world_name"]
    if world_profile.get("initial_situation"):
        session.lore_facts.insert(0, world_profile["initial_situation"])


def apply_profile_opening_payload(session: GameSession, payload: dict[str, Any]) -> None:
    """Apply one coherent dynamic-opening payload to an initialized session."""
    if not isinstance(payload, dict):
        return

    world = payload.get("world") if isinstance(payload.get("world"), dict) else {}
    world_profile = {
        key: value
        for key, value in payload.items()
        if key not in {"world", "choices", "opening_narrative"}
    }
    if world_profile:
        session.world_profile = world_profile

    session.current_scene = str(
        world.get("current_scene")
        or payload.get("initial_situation_16")
        or payload.get("initial_situation")
        or session.current_scene
    )
    session.location = str(world.get("location") or session.location)
    session.region = str(world.get("region") or payload.get("world_name") or session.region)
    session.npcs_present = _list_or_existing(world.get("npcs_present"), session.npcs_present)
    session.active_quests = _list_or_existing(world.get("active_quests"), session.active_quests)
    session.discovered_locations = _list_or_existing(
        world.get("discovered_locations"),
        session.discovered_locations or ([session.location] if session.location else []),
    )
    session.day_count = int(world.get("day_count") or session.day_count or 1)

    lore_facts = _list_or_existing(world.get("lore_facts"), session.lore_facts)
    for item in [
        payload.get("initial_situation"),
        *(payload.get("chronicle_0_16") if isinstance(payload.get("chronicle_0_16"), list) else []),
    ]:
        text = str(item or "").strip()
        if text and text not in lore_facts:
            lore_facts.append(text)
    session.lore_facts = lore_facts


def merge_opening_payload(fallback: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    """Merge model opening output over local fallback without losing required fields."""
    merged = dict(fallback)
    for key, value in parsed.items():
        if value:
            merged[key] = value

    fallback_world = fallback.get("world") if isinstance(fallback.get("world"), dict) else {}
    parsed_world = parsed.get("world") if isinstance(parsed.get("world"), dict) else {}
    world = dict(fallback_world)
    for key, value in parsed_world.items():
        if value:
            world[key] = value
    merged["world"] = world

    if not merged.get("opening_narrative"):
        chronicle = merged.get("chronicle_0_16") if isinstance(merged.get("chronicle_0_16"), list) else []
        opening = "\n".join(str(item) for item in chronicle if str(item).strip())
        initial = str(merged.get("initial_situation_16") or merged.get("initial_situation") or "")
        merged["opening_narrative"] = (opening + "\n\n" + initial).strip()
    return merged


def _list_or_existing(value: Any, existing: list[Any]) -> list[Any]:
    return list(value) if isinstance(value, list) else list(existing or [])



def _engine_has_api_key(engine: Any) -> bool:
    config = getattr(engine, "model_config", {})
    if isinstance(config, dict) and "api_key_set" in config:
        return bool(config.get("api_key_set"))
    return bool(os.environ.get("AGNES_API_KEY"))
