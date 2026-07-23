"""Apply deterministic and model-generated opening data to a game session."""

from __future__ import annotations

from typing import Any

from ..game.constants import compute_starting_lifespan, normalize_attribute_value
from ..rule_rng import new_run_seed
from ..session.game_session import GameSession
from .story_catalog import ensure_story_binding

_PROFILE_OPENING_AUTHORITY_FIELDS = (
    "world_key",
    "fate_hooks",
    "fate_profile",
    "matched_fates",
    "event_weights",
    "opening_hook",
    "long_conflict",
    "story_key",
    "story_version",
    "story_title",
    "story_opening",
    "story_state",
    "world_rules",
)


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
        session.lifespan = int(
            char_data.get("lifespan")
            or compute_starting_lifespan(
                session.realm,
                attributes=session.attributes,
                talent=session.talent,
                difficulty=session.difficulty,
            )
        )
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

    generated_profile = {
        key: value
        for key, value in generated.items()
        if key not in {"character", "world", "choices", "opening_narrative"}
    }
    if generated_profile:
        session.world_profile = generated_profile
    session.rule_rng_counter = 0
    session.run_seed = new_run_seed()
    ensure_story_binding(session)
    session.game_started = True
    session.turn_count = 0


def apply_profile_world_profile(session: GameSession, world_profile: dict[str, Any]) -> None:
    """Attach generated world-profile fields to a profile-started session."""
    session.world_profile = world_profile
    if world_profile.get("world_name"):
        session.region = world_profile["world_name"]
    if world_profile.get("initial_situation"):
        session.lore_facts.insert(0, world_profile["initial_situation"])
    _apply_story_binding(session, world_profile)


def apply_profile_opening_payload(session: GameSession, payload: dict[str, Any]) -> None:
    """Apply one coherent dynamic-opening payload to an initialized session."""
    if not isinstance(payload, dict):
        return
    world_value = payload.get("world")
    world: dict[str, Any] = world_value if isinstance(world_value, dict) else {}
    world_profile = {
        key: value
        for key, value in payload.items()
        if key not in {"character", "world", "choices", "opening_narrative"}
    }
    if world_profile:
        session.world_profile = world_profile
        _apply_story_binding(session, world_profile)

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
    chronicle_value = payload.get("chronicle_0_16")
    chronicle_items = chronicle_value if isinstance(chronicle_value, list) else []
    for item in [payload.get("initial_situation"), *chronicle_items]:
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
    for key in _PROFILE_OPENING_AUTHORITY_FIELDS:
        if key in fallback:
            merged[key] = fallback[key]

    fallback_world_value = fallback.get("world")
    parsed_world_value = parsed.get("world")
    fallback_world: dict[str, Any] = (
        fallback_world_value if isinstance(fallback_world_value, dict) else {}
    )
    parsed_world: dict[str, Any] = (
        parsed_world_value if isinstance(parsed_world_value, dict) else {}
    )
    world = dict(fallback_world)
    for key, value in parsed_world.items():
        if value:
            world[key] = value
    merged["world"] = world

    if not merged.get("opening_narrative"):
        chronicle_value = merged.get("chronicle_0_16")
        chronicle = chronicle_value if isinstance(chronicle_value, list) else []
        opening = "\n".join(str(item) for item in chronicle if str(item).strip())
        initial = str(merged.get("initial_situation_16") or merged.get("initial_situation") or "")
        merged["opening_narrative"] = (opening + "\n\n" + initial).strip()
    return merged


def _apply_story_binding(session: GameSession, world_profile: dict[str, Any]) -> None:
    story_key = str(world_profile.get("story_key") or "")
    story_version = world_profile.get("story_version", 0)
    story_state = world_profile.get("story_state")
    if story_key and isinstance(story_version, int) and not isinstance(story_version, bool):
        session.story_key = story_key
        session.story_version = story_version
    if isinstance(story_state, dict):
        session.story_state = dict(story_state)
    ensure_story_binding(session)


def _list_or_existing(value: Any, existing: list[Any]) -> list[Any]:
    return list(value) if isinstance(value, list) else list(existing or [])
