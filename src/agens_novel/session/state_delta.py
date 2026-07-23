"""Normalization and application of rule-authorized session state deltas."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..game.constants import (
    ATTRIBUTE_DEFAULT,
    DEFAULT_ATTRIBUTES,
    REALM_ORDER,
    clamp_attribute_value,
    normalize_attribute_value,
)
from ..utils.strings import dedupe_strings

if TYPE_CHECKING:
    from .game_session import GameSession


log = logging.getLogger(__name__)


def apply_session_delta(session: GameSession, delta: dict[str, Any]) -> None:
    """Apply a validated model/rule delta while ignoring malformed fields."""
    if not isinstance(delta, dict):
        log.warning("apply_delta: expected dict, got %s", type(delta).__name__)
        return
    _apply_character_delta(session, _delta_section(delta, "character"))
    _apply_world_delta(session, _delta_section(delta, "world"))
    _apply_meta_delta(session, _delta_section(delta, "meta"))


def normalize_relationships(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    relationships: list[dict[str, Any]] = []
    by_name: dict[str, int] = {}
    for raw in value:
        item = _normalize_relationship(raw)
        if item is None:
            continue
        name = item["name"]
        if name in by_name:
            relationships[by_name[name]] = {**relationships[by_name[name]], **item}
        else:
            by_name[name] = len(relationships)
            relationships.append(item)
    return relationships


def _apply_character_delta(session: GameSession, delta: dict[str, Any]) -> None:
    _apply_character_numbers(session, delta)
    _apply_character_identity(session, delta)
    _apply_character_attributes(session, delta)
    _apply_techniques(session, delta)
    _apply_inventory(session, delta)
    _apply_titles_and_relationships(session, delta)
    _apply_breakthrough_flags(session, delta)
    _apply_status_effects(session, delta)
    _apply_equipment(session, delta)


def _apply_character_numbers(session: GameSession, delta: dict[str, Any]) -> None:
    for key in ("lifespan", "realm_stage", "age"):
        if key not in delta:
            continue
        parsed = _parse_character_number(delta[key], int(getattr(session, key)), key)
        if parsed is not None:
            setattr(session, key, parsed)
    session.lifespan = max(1, session.lifespan)
    session.age = max(1, session.age)


def _parse_character_number(value: Any, current: int, key: str) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str) or value[:1] not in {"+", "-"}:
        return None
    try:
        return current + int(value)
    except ValueError:
        log.warning("apply_delta: cannot parse %s=%r as int, ignoring", key, value)
        return None


def _apply_character_identity(session: GameSession, delta: dict[str, Any]) -> None:
    if "realm" in delta:
        realm = delta["realm"]
        if isinstance(realm, str) and realm in REALM_ORDER:
            if realm != session.realm:
                session.realm_turn_count = 0
            session.realm = realm
        else:
            log.warning(
                "apply_delta: ignored invalid realm %r (expected one of %s)", realm, REALM_ORDER
            )
    direct_fields = {
        "name": "char_name",
        "spirit_root": "spirit_root",
        "spirit_root_grade": "spirit_root_grade",
    }
    for key, attribute in direct_fields.items():
        if key in delta:
            setattr(session, attribute, delta[key])
    for key in ("talent", "family_background", "difficulty"):
        if isinstance(delta.get(key), str):
            setattr(session, key, delta[key])


def _apply_character_attributes(session: GameSession, delta: dict[str, Any]) -> None:
    incoming = delta.get("attributes")
    if not isinstance(incoming, dict):
        return
    merged = {
        key: normalize_attribute_value(session.attributes.get(key, default))
        for key, default in DEFAULT_ATTRIBUTES.items()
    }
    for key, value in incoming.items():
        if key not in DEFAULT_ATTRIBUTES:
            log.warning("apply_delta: ignored unknown attribute %r", key)
            continue
        change = _parse_attribute_change(value)
        if change is not None:
            current = normalize_attribute_value(merged.get(key, ATTRIBUTE_DEFAULT))
            merged[key] = clamp_attribute_value(current + change)
    session.attributes = merged


def _parse_attribute_change(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value[:1] in {"+", "-"}:
        try:
            return int(value)
        except ValueError:
            log.warning("apply_delta: cannot parse attribute delta %r, ignoring", value)
    return None


def _apply_techniques(session: GameSession, delta: dict[str, Any]) -> None:
    if "techniques_add" in delta:
        additions = delta["techniques_add"]
        if additions is None:
            log.warning("apply_delta: techniques_add is None, ignoring")
        elif isinstance(additions, list):
            session.techniques.extend(additions)
        else:
            log.warning(
                "apply_delta: techniques_add must be list, got %s", type(additions).__name__
            )
    elif isinstance(delta.get("techniques"), list):
        session.techniques = delta["techniques"]


def _apply_inventory(session: GameSession, delta: dict[str, Any]) -> None:
    if "inventory_add" in delta:
        additions = delta["inventory_add"]
        if additions is None:
            log.warning("apply_delta: inventory_add is None, ignoring")
        elif isinstance(additions, list):
            session.inventory.extend(additions)
        elif isinstance(additions, str):
            session.inventory.append(additions)
        else:
            log.warning("apply_delta: inventory_add must be list, got %s", type(additions).__name__)
    elif isinstance(delta.get("inventory"), list):
        session.inventory = delta["inventory"]


def _apply_titles_and_relationships(session: GameSession, delta: dict[str, Any]) -> None:
    if "titles" in delta:
        titles = delta["titles"]
        if isinstance(titles, list):
            session.titles = dedupe_strings(titles)
        else:
            log.warning("apply_delta: titles must be list, got %s", type(titles).__name__)
    if "title_add" in delta:
        additions = delta["title_add"]
        if isinstance(additions, str):
            additions = [additions]
        if isinstance(additions, list):
            session.titles = dedupe_strings([*session.titles, *additions])
        else:
            log.warning("apply_delta: title_add must be list or str")

    if "relationships" in delta:
        relationships = delta["relationships"]
        if isinstance(relationships, list):
            session.relationships = normalize_relationships(relationships)
        else:
            log.warning(
                "apply_delta: relationships must be list, got %s",
                type(relationships).__name__,
            )
    if "relationship_add" in delta:
        _apply_relationship_additions(session, delta["relationship_add"])


def _apply_relationship_additions(session: GameSession, value: Any) -> None:
    additions = value if isinstance(value, list) else [value]
    if not isinstance(value, (dict, list)):
        log.warning("apply_delta: relationship_add must be dict or list")
        return
    by_name = {
        str(item.get("name") or "").strip(): index
        for index, item in enumerate(session.relationships)
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    for raw in additions:
        item = _normalize_relationship(raw)
        if item is None:
            continue
        name = item["name"]
        if name in by_name:
            session.relationships[by_name[name]] = {
                **session.relationships[by_name[name]],
                **item,
            }
        else:
            by_name[name] = len(session.relationships)
            session.relationships.append(item)


def _normalize_relationship(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    name = str(value.get("name") or "").strip()
    relation = str(value.get("relation") or "").strip()
    if not name or not relation:
        return None
    normalized: dict[str, Any] = {"name": name, "relation": relation}
    affinity = value.get("affinity")
    if isinstance(affinity, int) and not isinstance(affinity, bool):
        normalized["affinity"] = max(-100, min(100, affinity))
    return normalized


def _apply_breakthrough_flags(session: GameSession, delta: dict[str, Any]) -> None:
    if "breakthrough_flags" in delta:
        flags = delta["breakthrough_flags"]
        if isinstance(flags, list):
            session.breakthrough_flags = dedupe_strings(flags)
        else:
            log.warning(
                "apply_delta: breakthrough_flags must be list, got %s", type(flags).__name__
            )
    if "breakthrough_flags_add" not in delta:
        return
    additions = delta["breakthrough_flags_add"]
    if additions is None:
        log.warning("apply_delta: breakthrough_flags_add is None, ignoring")
        return
    flags_to_add = dedupe_strings(additions) if isinstance(additions, list) else [additions]
    if not isinstance(additions, (list, str)):
        log.warning(
            "apply_delta: breakthrough_flags_add must be list or str, got %s",
            type(additions).__name__,
        )
        return
    for flag in flags_to_add:
        if flag and flag not in session.breakthrough_flags:
            session.breakthrough_flags.append(flag)


def _apply_status_effects(session: GameSession, delta: dict[str, Any]) -> None:
    if "status_effects" in delta:
        effects = delta["status_effects"]
        if isinstance(effects, list):
            session.status_effects = effects
        else:
            log.warning("apply_delta: status_effects must be list, got %s", type(effects).__name__)
    _apply_status_effect_removals(session, delta.get("status_effects_remove"))
    if "status_effects_add" not in delta:
        return
    additions = delta["status_effects_add"]
    if additions is None:
        log.warning("apply_delta: status_effects_add is None, ignoring")
    elif isinstance(additions, list):
        for effect in additions:
            if effect not in session.status_effects:
                session.status_effects.append(effect)
    else:
        log.warning("apply_delta: status_effects_add must be list")


def _apply_status_effect_removals(session: GameSession, removals: Any) -> None:
    if removals is None:
        return
    if isinstance(removals, (str, dict)):
        removals = [removals]
    if not isinstance(removals, list):
        log.warning(
            "apply_delta: status_effects_remove must be list, str, or dict, got %s",
            type(removals).__name__,
        )
        return
    removal_names = {_status_effect_name(effect) for effect in removals}
    removal_names.discard("")
    session.status_effects = [
        effect
        for effect in session.status_effects
        if _status_effect_name(effect) not in removal_names
    ]


def _status_effect_name(effect: Any) -> str:
    if isinstance(effect, str):
        return effect.strip()
    if isinstance(effect, dict):
        return str(effect.get("name") or effect.get("effect") or effect.get("status") or "").strip()
    return ""


def _apply_equipment(session: GameSession, delta: dict[str, Any]) -> None:
    equipment = delta.get("equipment_slots")
    if not isinstance(equipment, dict):
        return
    valid_slots = {"weapon", "armor", "accessory"}
    for key, value in equipment.items():
        if key in valid_slots:
            session.equipment_slots[key] = value
        else:
            log.warning("apply_delta: unknown equipment slot %r, ignoring", key)


def _apply_world_delta(session: GameSession, delta: dict[str, Any]) -> None:
    for key in ("location", "region", "current_scene", "day_count"):
        if key in delta:
            setattr(session, key, delta[key])
    _replace_list(session, delta, "npcs_present", "npcs_present")
    _extend_list(session, delta, "npcs_present_add", "npcs_present")
    _replace_list(session, delta, "active_quests", "active_quests")
    _extend_list(session, delta, "active_quests_add", "active_quests")
    _extend_list(session, delta, "lore_add", "lore_facts")
    _extend_list(session, delta, "discovered_add", "discovered_locations")
    story_update = delta.get("story_update")
    if isinstance(story_update, dict):
        session.story_state = dict(story_update)


def _replace_list(session: GameSession, delta: dict[str, Any], key: str, attribute: str) -> None:
    value = delta.get(key)
    if isinstance(value, list):
        setattr(session, attribute, value)


def _extend_list(session: GameSession, delta: dict[str, Any], key: str, attribute: str) -> None:
    if key not in delta:
        return
    value = delta[key]
    if value is None:
        log.warning("apply_delta: %s is None, ignoring", key)
    elif isinstance(value, list):
        getattr(session, attribute).extend(value)
    else:
        log.warning("apply_delta: %s must be list", key)


def _apply_meta_delta(session: GameSession, meta: dict[str, Any]) -> None:
    if "game_over" in meta:
        value = meta["game_over"]
        if isinstance(value, bool):
            session.game_over = value
        else:
            log.warning("apply_delta: game_over must be bool, got %r", value)
    if "game_over_reason" in meta:
        session.error = meta["game_over_reason"]
    effect = meta.get("status_effect_add")
    if effect and effect not in session.status_effects:
        session.status_effects.append(effect)
    if meta.get("finale"):
        session.finale = True


def _delta_section(delta: dict[str, Any], key: str) -> dict[str, Any]:
    value = delta.get(key, {})
    if isinstance(value, dict):
        return value
    log.warning("apply_delta: %s must be dict, got %s", key, type(value).__name__)
    return {}
