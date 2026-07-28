"""Game session state for the xianxia cultivation simulator.

Replaces ``PipelineSession`` with a session that tracks character stats,
world state, and turn history.  Supports serialization for save/load.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from ..game.constants import (
    DEFAULT_ATTRIBUTES,
    DEFAULT_EQUIPMENT_SLOTS,
    REALM_LIFESPANS,
    normalize_attribute_value,
)
from ..utils.strings import dedupe_strings
from .state_delta import apply_session_delta, normalize_relationships

_RECENT_NARRATIVE_HASH_LIMIT = 120


def _narrative_hash(narrative: str) -> str:
    normalized = "".join(str(narrative or "").split())
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

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
    realm_turn_count: int = 0
    run_seed: str = ""
    rule_rng_counter: int = 0
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
    legacy_talents: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
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
    story_key: str = ""
    story_version: int = 0
    story_state: dict[str, Any] = field(default_factory=dict)
    # world_profile keys (when generated):
    #   world_name, regions, sects, cultivation_system, current_conflicts,
    #   world_rules (hidden from frontend)

    # ── Turn history ──
    turn_history: list[dict] = field(default_factory=list)
    recent_narrative_hashes: list[str] = field(default_factory=list)
    chat_history: list[dict] = field(default_factory=list)
    last_choices: list[str] = field(default_factory=list)

    # Local preset story fallback state.
    local_story_active: bool = False
    local_story_id: str = ""
    local_story_node_id: str = ""
    pending_model_failure: dict[str, Any] = field(default_factory=dict)

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
            "realm_turn_count": self.realm_turn_count,
            "game_started": self.game_started,
            "game_over": self.game_over,
            "finale": self.finale,
            "error": self.error,
            "rule_state": {
                "run_seed": self.run_seed,
                "rng_counter": self.rule_rng_counter,
            },
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
                "legacy_talents": self.legacy_talents,
                "titles": self.titles,
                "relationships": self.relationships,
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
                "story_key": self.story_key,
                "story_version": self.story_version,
                "story_state": self.story_state,
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
            "pending_model_failure": dict(self.pending_model_failure),
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
        apply_session_delta(self, delta)

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
        """Append one turn and project semantic context into chat history.

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
        self._remember_narrative(narrative)
        self.chat_history.append({"role": "user", "content": input_text})
        from ..engine.history import accepted_turn_context

        self.chat_history.append(
            {
                "role": "assistant",
                "content": str(narrative or "").strip(),
                "accepted_turn_context": accepted_turn_context(
                    self,
                    state_delta,
                    self.last_choices,
                ),
            }
        )
        if len(self.chat_history) > 20:
            from ..engine.history import compact_chat_history

            self.chat_history = compact_chat_history(self.chat_history, max_entries=20)

    def has_recent_narrative(self, narrative: str) -> bool:
        digest = _narrative_hash(narrative)
        return bool(digest) and digest in self.recent_narrative_hashes

    def _remember_narrative(self, narrative: str) -> None:
        digest = _narrative_hash(narrative)
        if not digest:
            return
        self.recent_narrative_hashes.append(digest)
        self.recent_narrative_hashes = self.recent_narrative_hashes[-_RECENT_NARRATIVE_HASH_LIMIT:]

    # ─────────────────────────────────────────────────────────────────────────
    # Serialization
    # ─────────────────────────────────────────────────────────────────────────

    def to_save_dict(self) -> dict[str, Any]:
        """Serialize the full session for JSON save export."""
        return {
            "turn_count": self.turn_count,
            "realm_turn_count": self.realm_turn_count,
            "rule_rng": {
                "run_seed": self.run_seed,
                "counter": self.rule_rng_counter,
            },
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
                "legacy_talents": self.legacy_talents,
                "titles": self.titles,
                "relationships": self.relationships,
                "status_effects": self.status_effects,
                "lifespan": self.lifespan,
                "remaining_lifespan": self.remaining_lifespan,
                "equipment_slots": self.equipment_slots,
            },
            "world": {
                "location": self.location,
                "region": self.region,
                "current_scene": self.current_scene,
                "day_count": self.day_count,
                "npcs_present": self.npcs_present,
                "active_quests": self.active_quests,
                "discovered_locations": self.discovered_locations,
                "lore_facts": self.lore_facts,
                "world_profile": self.world_profile,
                "story_key": self.story_key,
                "story_version": self.story_version,
                "story_state": self.story_state,
            },
            "turn_history": self.turn_history[-20:],
            "recent_narrative_hashes": self.recent_narrative_hashes[-_RECENT_NARRATIVE_HASH_LIMIT:],
            "chat_history": self.chat_history[-20:],
            "last_choices": self.last_choices,
            "local_story": {
                "active": self.local_story_active,
                "story_id": self.local_story_id,
                "node_id": self.local_story_node_id,
            },
            "pending_model_failure": dict(self.pending_model_failure),
            "finale": self.finale,
            "error": self.error,
        }

    @classmethod
    def from_save_dict(cls, data: dict[str, Any]) -> GameSession:
        """Deserialize from a saved JSON dict."""
        session = cls()
        session.turn_count = data.get("turn_count", 0)
        realm_turn_count = data.get("realm_turn_count", 0)
        session.realm_turn_count = (
            max(0, realm_turn_count)
            if isinstance(realm_turn_count, int) and not isinstance(realm_turn_count, bool)
            else 0
        )
        rule_rng = data.get("rule_rng", {})
        if isinstance(rule_rng, dict):
            session.run_seed = str(rule_rng.get("run_seed") or "").strip()
            raw_counter = rule_rng.get("counter", 0)
            session.rule_rng_counter = (
                max(0, raw_counter)
                if isinstance(raw_counter, int) and not isinstance(raw_counter, bool)
                else 0
            )
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
                if (
                    key in DEFAULT_ATTRIBUTES
                    and isinstance(value, int)
                    and not isinstance(value, bool)
                ):
                    merged_attrs[key] = normalize_attribute_value(value)
            session.attributes = merged_attrs
        flags = char.get("breakthrough_flags", [])
        session.breakthrough_flags = dedupe_strings(flags) if isinstance(flags, list) else []
        session.techniques = char.get("techniques", [])
        session.inventory = char.get("inventory", [])
        legacy_talents = char.get("legacy_talents", [])
        session.legacy_talents = (
            dedupe_strings(legacy_talents) if isinstance(legacy_talents, list) else []
        )
        titles = char.get("titles", [])
        session.titles = dedupe_strings(titles) if isinstance(titles, list) else []
        relationships = char.get("relationships", [])
        session.relationships = normalize_relationships(relationships)
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
        session.story_key = str(world.get("story_key") or "")
        story_version = world.get("story_version", 0)
        session.story_version = (
            story_version
            if isinstance(story_version, int) and not isinstance(story_version, bool)
            else 0
        )
        story_state = world.get("story_state", {})
        session.story_state = dict(story_state) if isinstance(story_state, dict) else {}
        turn_history = data.get("turn_history", [])
        session.turn_history = turn_history if isinstance(turn_history, list) else []
        stored_hashes = data.get("recent_narrative_hashes", [])
        session.recent_narrative_hashes = [
            item
            for item in stored_hashes
            if isinstance(item, str) and len(item) == 64 and all(char in "0123456789abcdef" for char in item)
        ][-_RECENT_NARRATIVE_HASH_LIMIT:]
        if not session.recent_narrative_hashes:
            session.recent_narrative_hashes = [
                digest
                for entry in session.turn_history
                if isinstance(entry, dict)
                if (digest := _narrative_hash(str(entry.get("narrative") or "")))
            ][-_RECENT_NARRATIVE_HASH_LIMIT:]
        chat_history = data.get("chat_history", [])
        session.chat_history = chat_history if isinstance(chat_history, list) else []
        session.last_choices = data.get("last_choices", [])
        local_story = data.get("local_story", {})
        if isinstance(local_story, dict):
            session.local_story_active = bool(local_story.get("active", False))
            session.local_story_id = str(local_story.get("story_id") or "")
            session.local_story_node_id = str(local_story.get("node_id") or "")
        pending_failure = data.get("pending_model_failure")
        from ..engine.pending_model_failure import PendingModelFailureV1

        parsed_pending = PendingModelFailureV1.from_payload(pending_failure)
        session.pending_model_failure = parsed_pending.to_dict() if parsed_pending else {}
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
