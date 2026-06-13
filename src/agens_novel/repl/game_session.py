"""Game session state for the xianxia cultivation simulator.

Replaces ``PipelineSession`` with a session that tracks character stats,
world state, and turn history.  Supports serialization for save/load.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import logging

from ..game.constants import REALM_ORDER, DEFAULT_EQUIPMENT_SLOTS

log = logging.getLogger(__name__)


@dataclass
class GameSession:
    """Stateful session for the xianxia cultivation simulator."""

    # ── Persistence ──
    save_file: str = ""
    turn_count: int = 0
    game_started: bool = False
    game_over: bool = False

    # ── Character ──
    char_name: str = ""
    realm: str = "练气"
    realm_stage: int = 1
    hp: int = 100
    hp_max: int = 100
    mp: int = 50
    mp_max: int = 50
    spirit_root: str = ""
    spirit_root_grade: str = ""
    experience: int = 0
    experience_to_next: int = 100
    gold: int = 0
    techniques: list[dict] = field(default_factory=list)
    inventory: list[dict] = field(default_factory=list)
    status_effects: list[str] = field(default_factory=list)
    lifespan: int = 100
    equipment_slots: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_EQUIPMENT_SLOTS))

    # ── Combat ──
    combat: dict[str, Any] | None = None

    # ── World ──
    location: str = ""
    region: str = ""
    current_scene: str = ""
    day_count: int = 1
    npcs_present: list[dict] = field(default_factory=list)
    active_quests: list[dict] = field(default_factory=list)
    discovered_locations: list[str] = field(default_factory=list)
    lore_facts: list[str] = field(default_factory=list)

    # ── Turn history ──
    turn_history: list[dict] = field(default_factory=list)
    chat_history: list[dict] = field(default_factory=list)

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
                "hp": self.hp,
                "hp_max": self.hp_max,
                "mp": self.mp,
                "mp_max": self.mp_max,
                "spirit_root": self.spirit_root,
                "spirit_root_grade": self.spirit_root_grade,
                "experience": self.experience,
                "experience_to_next": self.experience_to_next,
                "gold": self.gold,
                "techniques": self.techniques,
                "inventory": self.inventory,
                "status_effects": self.status_effects,
                "lifespan": self.lifespan,
                "equipment_slots": self.equipment_slots,
                "combat": self.combat,
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
            },
            "model": self.model,
            "base_url": self.base_url,
            "api_key_set": self.api_key_set,
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

        char_delta = delta.get("character", {})
        for key in (
            "hp", "mp", "experience", "gold", "lifespan", "realm_stage",
            "experience_to_next", "hp_max", "mp_max",
        ):
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

        # Floor guards: prevent negative values on key stats.
        self.experience = max(0, self.experience)
        self.gold = max(0, self.gold)
        self.lifespan = max(1, self.lifespan)

        # Minimum guards for max stats.
        self.hp_max = max(1, self.hp_max)
        self.mp_max = max(1, self.mp_max)

        # Clamp HP/MP to [0, max].
        self.hp = max(0, min(self.hp, self.hp_max))
        self.mp = max(0, min(self.mp, self.mp_max))

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

        # Combat state.
        if "combat" in char_delta:
            combat_delta = char_delta["combat"]
            if combat_delta is None or combat_delta == {}:
                self.combat = None
            elif isinstance(combat_delta, dict):
                if self.combat is None:
                    self.combat = combat_delta
                else:
                    self.combat.update(combat_delta)

        world_delta = delta.get("world", {})
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

        meta = delta.get("meta", {})
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
    # Serialization
    # ─────────────────────────────────────────────────────────────────────────

    def to_save_dict(self) -> dict[str, Any]:
        """Serialize the full session for JSON persistence."""
        return {
            "turn_count": self.turn_count,
            "game_started": self.game_started,
            "game_over": self.game_over,
            "character": {
                "name": self.char_name, "realm": self.realm,
                "realm_stage": self.realm_stage, "hp": self.hp,
                "hp_max": self.hp_max, "mp": self.mp, "mp_max": self.mp_max,
                "spirit_root": self.spirit_root,
                "spirit_root_grade": self.spirit_root_grade,
                "experience": self.experience,
                "experience_to_next": self.experience_to_next,
                "gold": self.gold, "techniques": self.techniques,
                "inventory": self.inventory,
                "status_effects": self.status_effects,
                "lifespan": self.lifespan,
                "equipment_slots": self.equipment_slots,
                "combat": self.combat,
            },
            "world": {
                "location": self.location, "region": self.region,
                "current_scene": self.current_scene,
                "day_count": self.day_count,
                "npcs_present": self.npcs_present,
                "active_quests": self.active_quests,
                "discovered_locations": self.discovered_locations,
                "lore_facts": self.lore_facts,
            },
            "turn_history": self.turn_history[-20:],
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
        session.hp = char.get("hp", 100)
        session.hp_max = char.get("hp_max", 100)
        session.mp = char.get("mp", 50)
        session.mp_max = char.get("mp_max", 50)
        session.spirit_root = char.get("spirit_root", "")
        session.spirit_root_grade = char.get("spirit_root_grade", "")
        session.experience = char.get("experience", 0)
        session.experience_to_next = char.get("experience_to_next", 100)
        session.gold = char.get("gold", 0)
        session.techniques = char.get("techniques", [])
        session.inventory = char.get("inventory", [])
        session.status_effects = char.get("status_effects", [])
        session.lifespan = char.get("lifespan", 100)
        session.equipment_slots = char.get("equipment_slots", dict(DEFAULT_EQUIPMENT_SLOTS))
        session.combat = char.get("combat", None)

        world = data.get("world", {})
        session.location = world.get("location", "")
        session.region = world.get("region", "")
        session.current_scene = world.get("current_scene", "")
        session.day_count = world.get("day_count", 1)
        session.npcs_present = world.get("npcs_present", [])
        session.active_quests = world.get("active_quests", [])
        session.discovered_locations = world.get("discovered_locations", [])
        session.lore_facts = world.get("lore_facts", [])
        session.turn_history = data.get("turn_history", [])
        session.finale = data.get("finale", False)
        return session

    def reset(self) -> None:
        """Clear all state for a new game."""
        self.__init__()
