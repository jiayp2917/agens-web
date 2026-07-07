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
    inventory: list[dict] = field(default_factory=list)
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

        char_delta = _delta_section(delta, "character")
        for key in ("lifespan", "realm_stage", "age"):
            if key in char_delta:
                val = char_delta[key]
                current = getattr(self, key)
                if isinstance(val, bool):
                    pass  # bool is a subclass of int; skip it
                elif isinstance(val, str) and val.startswith("+"):
                    try:
                        new_val = current + int(val[1:])
                    except ValueError:
                        log.warning("apply_delta: cannot parse +%r as int, ignoring", val[1:])
                        continue
                    setattr(self, key, new_val)
                elif isinstance(val, str) and val.startswith("-"):
                    try:
                        new_val = current - int(val[1:])
                    except ValueError:
                        log.warning("apply_delta: cannot parse -%r as int, ignoring", val[1:])
                        continue
                    setattr(self, key, new_val)
                elif isinstance(val, int):
                    setattr(self, key, val)
                # else: silently drop unknown types (None, float, str, list, dict)

        # Floor guards: prevent invalid age/lifespan values.
        self.lifespan = max(1, self.lifespan)
        self.age = max(1, self.age)

        if "realm" in char_delta:
            val = char_delta["realm"]
            # Whitelist: only allow known realm names.
            if isinstance(val, str) and val in REALM_ORDER:
                self.realm = val
            else:
                log.warning(
                    "apply_delta: ignored invalid realm %r (expected one of %s)",
                    val, REALM_ORDER,
                )
        if "name" in char_delta:
            self.char_name = char_delta["name"]
        if "spirit_root" in char_delta:
            self.spirit_root = char_delta["spirit_root"]
        if "spirit_root_grade" in char_delta:
            self.spirit_root_grade = char_delta["spirit_root_grade"]
        if "talent" in char_delta and isinstance(char_delta["talent"], str):
            self.talent = char_delta["talent"]
        if "family_background" in char_delta and isinstance(char_delta["family_background"], str):
            self.family_background = char_delta["family_background"]
        if "difficulty" in char_delta and isinstance(char_delta["difficulty"], str):
            self.difficulty = char_delta["difficulty"]
        if "attributes" in char_delta and isinstance(char_delta["attributes"], dict):
            merged = {
                key: normalize_attribute_value(self.attributes.get(key, default))
                for key, default in DEFAULT_ATTRIBUTES.items()
            }
            for key, value in char_delta["attributes"].items():
                if key not in DEFAULT_ATTRIBUTES:
                    log.warning("apply_delta: ignored unknown attribute %r", key)
                    continue
                if isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool):
                    current = normalize_attribute_value(merged.get(key, ATTRIBUTE_DEFAULT))
                    merged[key] = clamp_attribute_value(current + value)
                elif isinstance(key, str) and isinstance(value, str) and value[:1] in {"+", "-"}:
                    try:
                        current = normalize_attribute_value(merged.get(key, ATTRIBUTE_DEFAULT))
                        merged[key] = clamp_attribute_value(current + int(value))
                    except ValueError:
                        log.warning("apply_delta: cannot parse attribute delta %r, ignoring", value)
            self.attributes = merged
        if "techniques_add" in char_delta:
            add = char_delta["techniques_add"]
            if add is None:
                log.warning("apply_delta: techniques_add is None, ignoring")
            elif isinstance(add, list):
                self.techniques.extend(add)
            else:
                log.warning("apply_delta: techniques_add must be list, got %s", type(add).__name__)
        if "techniques" in char_delta and "techniques_add" not in char_delta:
            # Full replace only if no _add variant.
            if isinstance(char_delta["techniques"], list):
                self.techniques = char_delta["techniques"]
        if "inventory_add" in char_delta:
            add = char_delta["inventory_add"]
            if add is None:
                log.warning("apply_delta: inventory_add is None, ignoring")
            elif isinstance(add, list):
                self.inventory.extend(add)
            elif isinstance(add, str):
                # Defensive: a single string (e.g. LLM typo) becomes a single item, not 5 chars.
                self.inventory.append(add)
            else:
                log.warning("apply_delta: inventory_add must be list, got %s", type(add).__name__)
        if "inventory" in char_delta and "inventory_add" not in char_delta:
            if isinstance(char_delta["inventory"], list):
                self.inventory = char_delta["inventory"]
        if "breakthrough_flags" in char_delta:
            val = char_delta["breakthrough_flags"]
            if isinstance(val, list):
                self.breakthrough_flags = _dedupe_strings(val)
            else:
                log.warning("apply_delta: breakthrough_flags must be list, got %s", type(val).__name__)
        if "breakthrough_flags_add" in char_delta:
            add = char_delta["breakthrough_flags_add"]
            if add is None:
                log.warning("apply_delta: breakthrough_flags_add is None, ignoring")
            elif isinstance(add, list):
                for flag in _dedupe_strings(add):
                    if flag not in self.breakthrough_flags:
                        self.breakthrough_flags.append(flag)
            elif isinstance(add, str):
                if add and add not in self.breakthrough_flags:
                    self.breakthrough_flags.append(add)
            else:
                log.warning("apply_delta: breakthrough_flags_add must be list or str, got %s", type(add).__name__)
        if "status_effects" in char_delta:
            val = char_delta["status_effects"]
            if isinstance(val, list):
                self.status_effects = val
            else:
                log.warning("apply_delta: status_effects must be list, got %s", type(val).__name__)
        if "status_effects_add" in char_delta:
            add = char_delta["status_effects_add"]
            if add is None:
                log.warning("apply_delta: status_effects_add is None, ignoring")
            elif isinstance(add, list):
                for eff in add:
                    if eff not in self.status_effects:
                        self.status_effects.append(eff)
            else:
                log.warning("apply_delta: status_effects_add must be list")
        if "equipment_slots" in char_delta:
            eq_delta = char_delta["equipment_slots"]
            if isinstance(eq_delta, dict):
                # Whitelist: only accept known equipment slot keys.
                _VALID_SLOTS = {"weapon", "armor", "accessory"}
                for k, v in eq_delta.items():
                    if k in _VALID_SLOTS:
                        self.equipment_slots[k] = v
                    else:
                        log.warning("apply_delta: unknown equipment slot %r, ignoring", k)

        world_delta = _delta_section(delta, "world")
        for key in ("location", "region", "current_scene", "day_count"):
            if key in world_delta:
                setattr(self, key, world_delta[key])
        if "npcs_present" in world_delta:
            val = world_delta["npcs_present"]
            if isinstance(val, list):
                self.npcs_present = val
        if "npcs_present_add" in world_delta:
            add = world_delta["npcs_present_add"]
            if add is None:
                log.warning("apply_delta: npcs_present_add is None, ignoring")
            elif isinstance(add, list):
                self.npcs_present.extend(add)
            else:
                log.warning("apply_delta: npcs_present_add must be list")
        if "active_quests" in world_delta:
            val = world_delta["active_quests"]
            if isinstance(val, list):
                self.active_quests = val
        if "active_quests_add" in world_delta:
            add = world_delta["active_quests_add"]
            if add is None:
                log.warning("apply_delta: active_quests_add is None, ignoring")
            elif isinstance(add, list):
                self.active_quests.extend(add)
            else:
                log.warning("apply_delta: active_quests_add must be list")
        if "lore_add" in world_delta:
            add = world_delta["lore_add"]
            if add is None:
                log.warning("apply_delta: lore_add is None, ignoring")
            elif isinstance(add, list):
                self.lore_facts.extend(add)
            else:
                log.warning("apply_delta: lore_add must be list")
        if "discovered_add" in world_delta:
            add = world_delta["discovered_add"]
            if add is None:
                log.warning("apply_delta: discovered_add is None, ignoring")
            elif isinstance(add, list):
                self.discovered_locations.extend(add)
            else:
                log.warning("apply_delta: discovered_add must be list")

        meta = _delta_section(delta, "meta")
        if "game_over" in meta:
            val = meta["game_over"]
            # Only accept bool (or truthy/falsy that maps cleanly).
            if isinstance(val, bool):
                self.game_over = val
            else:
                log.warning("apply_delta: game_over must be bool, got %r", val)
        if "game_over_reason" in meta:
            self.error = meta["game_over_reason"]
        if "status_effect_add" in meta:
            eff = meta["status_effect_add"]
            if eff and eff not in self.status_effects:
                self.status_effects.append(eff)
        # Finale flag (v0.4): marks "飞升" (ascension) — used by UI for special ending screen.
        if "finale" in meta and meta["finale"]:
            self.finale = True

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
        return session

    def reset(self) -> None:
        """Clear all state for a new game."""
        self.__init__()

    @property
    def remaining_lifespan(self) -> int:
        """Remaining years before natural death under the current realm cap."""
        cap = int(self.lifespan or REALM_LIFESPANS.get(self.realm, 100))
        return max(0, cap - int(self.age or 0))


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
