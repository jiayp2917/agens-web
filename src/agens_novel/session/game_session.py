"""Game session state for the xianxia cultivation simulator.

Replaces ``PipelineSession`` with a session that tracks character stats,
world state, and turn history.  Supports serialization for save/load.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..game.constants import (
    ATTRIBUTE_DEFAULT,
    DEFAULT_ATTRIBUTES,
    DEFAULT_EQUIPMENT_SLOTS,
    REALM_LIFESPANS,
    REALM_ORDER,
    clamp_attribute_value,
    normalize_attribute_value,
)

log = logging.getLogger(__name__)

_LEGACY_CHARACTER_FIELDS = {
    "hp",
    "hp_max",
    "mp",
    "mp_max",
    "combat",
    "luck",
    "game_mode",
    "experience",
    "experience_to_next",
    "insight",
    "gold",
}


@dataclass
class GameSession:
    def __setattr__(self, name: str, value: Any) -> None:
        if name in _LEGACY_CHARACTER_FIELDS:
            raise AttributeError(f"{name} is not part of the game-mode v5 session")
        super().__setattr__(name, value)

    """Stateful session for the xianxia cultivation simulator."""

    # ── Save metadata ──
    save_file: str = ""
    turn_count: int = 0
    game_started: bool = False
    game_over: bool = False

    # ── Character ── (game mode: no HP/MP; death events are rule-driven)
    char_name: str = ""
    realm: str = "练气"
    realm_stage: int = 1
    spirit_root: str = ""
    spirit_root_grade: str = ""
    age: int = 16
    talent: str = ""
    family_background: str = ""
    difficulty: str = "普通"
    attributes: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_ATTRIBUTES))
    breakthrough_flags: list[str] = field(default_factory=list)
    techniques: list[dict] = field(default_factory=list)
    inventory: list[Any] = field(default_factory=list)
    status_effects: list[str] = field(default_factory=list)
    lifespan: int = 100
    equipment_slots: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_EQUIPMENT_SLOTS))

    # ── World ──
    location: str = ""
    region: str = ""
    current_scene: str = ""
    day_count: int = 1
    npcs_present: list[dict] = field(default_factory=list)
    active_quests: list[dict] = field(default_factory=list)
    discovered_locations: list[str] = field(default_factory=list)
    lore_facts: list[str] = field(default_factory=list)
    world_profile: dict[str, Any] = field(default_factory=dict)
    # world_profile keys (when generated):
    #   world_name, regions, sects, cultivation_system, current_conflicts,
    #   world_rules (hidden from frontend)

    # ── Turn history ──
    turn_history: list[dict] = field(default_factory=list)
    chat_history: list[dict] = field(default_factory=list)
    last_choices: list[str] = field(default_factory=list)

    # Local preset story fallback state.
    local_story_active: bool = False
    local_story_id: str = ""
    local_story_node_id: str = ""

    # ── Run metadata ──
    model: str = ""
    base_url: str = ""
    api_key_set: bool = False

    # ── Error ──
    error: str = ""

    # ── Finale (v0.4): marks "飞升" ascension ending ──
    finale: bool = False

    # ─────────────────────────────────────────────────────────────────────────
    # Conversion
    # ─────────────────────────────────────────────────────────────────────────

    def as_game_state(self) -> dict[str, Any]:
        """Convert to a dict compatible with GameState for agent invocation."""
        return {
            "turn_count": self.turn_count,
            "game_started": self.game_started,
            "game_over": self.game_over,
            "character": {
                "name": self.char_name,
                "realm": self.realm,
                "realm_stage": self.realm_stage,
                "spirit_root": self.spirit_root,
                "spirit_root_grade": self.spirit_root_grade,
                "age": self.age,
                "talent": self.talent,
                "family_background": self.family_background,
                "difficulty": self.difficulty,
                "attributes": self.attributes,
                "breakthrough_flags": self.breakthrough_flags,
                "techniques": self.techniques,
                "inventory": self.inventory,
                "status_effects": self.status_effects,
                "lifespan": self.lifespan,
                "remaining_lifespan": self.remaining_lifespan,
                "equipment_slots": self.equipment_slots,
            },
            "world": {
                "current_scene": self.current_scene,
                "location": self.location,
                "region": self.region,
                "npcs_present": self.npcs_present,
                "active_quests": self.active_quests,
                "discovered_locations": self.discovered_locations,
                "lore_facts": self.lore_facts,
                "turn_events": [],
                "day_count": self.day_count,
                "world_profile": self.world_profile,
            },
            "model": self.model,
            "base_url": self.base_url,
            "api_key_set": self.api_key_set,
            "choices": self.last_choices,
            "local_story": {
                "active": self.local_story_active,
                "story_id": self.local_story_id,
                "node_id": self.local_story_node_id,
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Delta application
    # ─────────────────────────────────────────────────────────────────────────

    def apply_delta(self, delta: dict[str, Any]) -> None:
        """Apply a state delta from the narrator/judge to the session.

        Defensive design (v0.4): validates inputs to prevent crashes from
        malformed LLM output.  Bad values are logged and silently dropped
        rather than raising — the game must keep running.
        """
        if not isinstance(delta, dict):
            log.warning("apply_delta: expected dict, got %s", type(delta).__name__)
            return
        _apply_character_delta(self, _delta_section(delta, "character"))
        _apply_world_delta(self, _delta_section(delta, "world"))
        _apply_meta_delta(self, _delta_section(delta, "meta"))

    # ─────────────────────────────────────────────────────────────────────────
    # Turn recording
    # ─────────────────────────────────────────────────────────────────────────

    def record_turn(
        self,
        input_text: str,
        narrative: str,
        state_delta: dict[str, Any],
        *,
        local_story: dict[str, Any] | None = None,
    ) -> None:
        """Append one turn to turn_history and feed chat_history (with compact).

        All turn-recording sites (ordinary, local-story, local-story fallback,
        breakthrough) route through this so local-story turns also enter the
        narrator prompt context. ``compact_chat_history`` is imported lazily to
        avoid a session<->engine circular import at module load.
        """
        entry: dict[str, Any] = {
            "turn": self.turn_count,
            "input": input_text,
            "narrative": narrative,
            "delta": state_delta,
            "choices": self.last_choices,
        }
        if local_story is not None:
            entry["local_story"] = local_story
        self.turn_history.append(entry)
        self.chat_history.append({"role": "user", "content": input_text})
        self.chat_history.append({"role": "assistant", "content": narrative})
        if len(self.chat_history) > 20:
            from ..engine.history import compact_chat_history

            self.chat_history = compact_chat_history(self.chat_history, max_entries=20)

    # ─────────────────────────────────────────────────────────────────────────
    # Serialization
    # ─────────────────────────────────────────────────────────────────────────

    def to_save_dict(self) -> dict[str, Any]:
        """Serialize the full session for JSON save export."""
        return {
            "turn_count": self.turn_count,
            "game_started": self.game_started,
            "game_over": self.game_over,
            "character": {
                "name": self.char_name, "realm": self.realm,
                "realm_stage": self.realm_stage,
                "spirit_root": self.spirit_root,
                "spirit_root_grade": self.spirit_root_grade,
                "age": self.age,
                "talent": self.talent,
                "family_background": self.family_background,
                "difficulty": self.difficulty,
                "attributes": self.attributes,
                "breakthrough_flags": self.breakthrough_flags,
                "techniques": self.techniques,
                "inventory": self.inventory,
                "status_effects": self.status_effects,
                "lifespan": self.lifespan,
                "remaining_lifespan": self.remaining_lifespan,
                "equipment_slots": self.equipment_slots,
            },
            "world": {
                "location": self.location, "region": self.region,
                "current_scene": self.current_scene,
                "day_count": self.day_count,
                "npcs_present": self.npcs_present,
                "active_quests": self.active_quests,
                "discovered_locations": self.discovered_locations,
                "lore_facts": self.lore_facts,
                "world_profile": self.world_profile,
            },
            "turn_history": self.turn_history[-20:],
            "chat_history": self.chat_history[-20:],
            "last_choices": self.last_choices,
            "local_story": {
                "active": self.local_story_active,
                "story_id": self.local_story_id,
                "node_id": self.local_story_node_id,
            },
            "finale": self.finale,
            "error": self.error,
        }

    @classmethod
    def from_save_dict(cls, data: dict[str, Any]) -> GameSession:
        """Deserialize from a saved JSON dict."""
        session = cls()
        session.turn_count = data.get("turn_count", 0)
        session.game_started = data.get("game_started", False)
        session.game_over = data.get("game_over", False)

        char = data.get("character", {})
        session.char_name = char.get("name", "")
        session.realm = char.get("realm", "练气")
        session.realm_stage = char.get("realm_stage", 1)
        session.spirit_root = char.get("spirit_root", "")
        session.spirit_root_grade = char.get("spirit_root_grade", "")
        session.age = char.get("age", 16)
        session.talent = char.get("talent", "")
        session.family_background = char.get("family_background", "")
        session.difficulty = char.get("difficulty", "普通")
        attrs = char.get("attributes", {})
        if isinstance(attrs, dict):
            merged_attrs = dict(DEFAULT_ATTRIBUTES)
            for key, value in attrs.items():
                if key in DEFAULT_ATTRIBUTES and isinstance(value, int) and not isinstance(value, bool):
                    merged_attrs[key] = normalize_attribute_value(value)
            session.attributes = merged_attrs
        flags = char.get("breakthrough_flags", [])
        session.breakthrough_flags = _dedupe_strings(flags) if isinstance(flags, list) else []
        session.techniques = char.get("techniques", [])
        session.inventory = char.get("inventory", [])
        session.status_effects = char.get("status_effects", [])
        session.lifespan = char.get("lifespan", 100)
        session.equipment_slots = char.get("equipment_slots", dict(DEFAULT_EQUIPMENT_SLOTS))

        world = data.get("world", {})
        session.location = world.get("location", "")
        session.region = world.get("region", "")
        session.current_scene = world.get("current_scene", "")
        session.day_count = world.get("day_count", 1)
        session.npcs_present = world.get("npcs_present", [])
        session.active_quests = world.get("active_quests", [])
        session.discovered_locations = world.get("discovered_locations", [])
        session.lore_facts = world.get("lore_facts", [])
        session.world_profile = world.get("world_profile", {})
        if not isinstance(session.world_profile, dict):
            session.world_profile = {}
        session.turn_history = data.get("turn_history", [])
        chat_history = data.get("chat_history", [])
        session.chat_history = chat_history if isinstance(chat_history, list) else []
        session.last_choices = data.get("last_choices", [])
        local_story = data.get("local_story", {})
        if isinstance(local_story, dict):
            session.local_story_active = bool(local_story.get("active", False))
            session.local_story_id = str(local_story.get("story_id") or "")
            session.local_story_node_id = str(local_story.get("node_id") or "")
        session.finale = data.get("finale", False)
        session.error = str(data.get("error") or "")
        return session

    def reset(self) -> None:
        """Clear all state for a new game."""
        self.__dict__.update(GameSession().__dict__)

    @property
    def remaining_lifespan(self) -> int:
        """Remaining years before natural death under the current realm cap."""
        cap = int(self.lifespan or REALM_LIFESPANS.get(self.realm, 100))
        return max(0, cap - int(self.age or 0))


def _apply_character_delta(session: GameSession, delta: dict[str, Any]) -> None:
    _apply_character_numbers(session, delta)
    _apply_character_identity(session, delta)
    _apply_character_attributes(session, delta)
    _apply_techniques(session, delta)
    _apply_inventory(session, delta)
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
            session.realm = realm
        else:
            log.warning("apply_delta: ignored invalid realm %r (expected one of %s)", realm, REALM_ORDER)
    direct_fields = {
        "name": "char_name",
        "spirit_root": "spirit_root",
        "spirit_root_grade": "spirit_root_grade",
    }
    for key, attribute in direct_fields.items():
        if key in delta:
            setattr(session, attribute, delta[key])
    string_fields = ("talent", "family_background", "difficulty")
    for key in string_fields:
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
            log.warning("apply_delta: techniques_add must be list, got %s", type(additions).__name__)
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


def _apply_breakthrough_flags(session: GameSession, delta: dict[str, Any]) -> None:
    if "breakthrough_flags" in delta:
        flags = delta["breakthrough_flags"]
        if isinstance(flags, list):
            session.breakthrough_flags = _dedupe_strings(flags)
        else:
            log.warning("apply_delta: breakthrough_flags must be list, got %s", type(flags).__name__)
    if "breakthrough_flags_add" not in delta:
        return
    additions = delta["breakthrough_flags_add"]
    if additions is None:
        log.warning("apply_delta: breakthrough_flags_add is None, ignoring")
        return
    flags_to_add = _dedupe_strings(additions) if isinstance(additions, list) else [additions]
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


def _dedupe_strings(values: list[Any]) -> list[str]:
    """Return unique non-empty strings while preserving order (delegates to shared impl)."""
    from ..engine.choices import dedupe_strings

    return dedupe_strings(values)


def _delta_section(delta: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a dict section from a model delta, ignoring malformed sections."""
    value = delta.get(key, {})
    if isinstance(value, dict):
        return value
    log.warning("apply_delta: %s must be dict, got %s", key, type(value).__name__)
    return {}
