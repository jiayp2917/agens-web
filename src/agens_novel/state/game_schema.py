"""Game state schemas for the xianxia cultivation simulator.

Defines the TypedDict shapes used by the narrator, judge, and world_builder
agents.  These are the "contract" between the REPL session and the LLM agents.
"""

from __future__ import annotations

from typing import TypedDict

from .reducers import Append

# ─────────────────────────────────────────────────────────────────────────────
# Nested sub-states
# ─────────────────────────────────────────────────────────────────────────────


class Technique(TypedDict, total=False):
    name: str
    level: int
    type: str       # "内功" | "外功" | "术法" | "身法" | ...
    mp_cost: int    # MP cost to use this technique in combat
    element: str    # elemental affinity: 金/木/水/火/土/冰/雷/风


class InventoryItem(TypedDict, total=False):
    name: str
    quantity: int
    type: str       # "武器" | "防具" | "丹药" | "材料" | "其他"
    rarity: str     # "凡品" | "良品" | "上品" | "极品" | "仙品"
    effects: dict   # item effects, e.g. {"hp": "+50", "mp": "+20"}
    equipped: bool  # whether currently equipped
    slot: str       # equipment slot: "weapon" | "armor" | "accessory"


class NpcInfo(TypedDict, total=False):
    name: str
    relation: str           # "师门" | "友善" | "中立" | "敌对" | ...
    realm: str
    affinity: int           # NPC affinity score toward player
    personality: str        # e.g. "温和" | "冷酷" | "豪爽"
    can_trade: bool         # whether NPC offers shop/trade
    can_teach: bool         # whether NPC can teach techniques
    exclusive_quest: str    # name of NPC-exclusive quest (empty if none)


class QuestInfo(TypedDict, total=False):
    name: str
    description: str
    status: str     # "active" | "completed" | "failed"
    type: str       # "主线" | "支线" | "日常" | "隐藏"
    conditions: dict  # quest completion conditions
    rewards: dict     # quest rewards
    giver: str        # NPC name who gave the quest


class CombatActor(TypedDict, total=False):
    name: str
    hp: int
    hp_max: int
    mp: int
    mp_max: int
    realm: str
    techniques: list[Technique]
    consumables: list[InventoryItem]
    is_defending: bool


class CombatState(TypedDict, total=False):
    phase: str                  # "idle" | "player_turn" | "enemy_turn" | "resolve" | "victory" | "defeat"
    player: CombatActor
    enemy: CombatActor
    available_actions: list[str]  # ["attack", "technique", "item", "defend", "flee"]
    turn_count: int
    result: str                 # "" | "victory" | "defeat" | "fled"
    narrative: str              # latest combat narrative snippet


class CharacterState(TypedDict, total=False):
    name: str
    realm: str
    realm_stage: int
    hp: int
    hp_max: int
    mp: int
    mp_max: int
    spirit_root: str
    spirit_root_grade: str
    age: int
    talent: str
    family_background: str
    luck: str
    difficulty: str
    game_mode: str
    attributes: dict
    techniques: list[Technique]
    inventory: list[InventoryItem]
    experience: int
    experience_to_next: int
    insight: int
    breakthrough_flags: list[str]
    gold: int
    status_effects: list[str]
    lifespan: int
    equipment_slots: dict       # {"weapon": InventoryItem|None, "armor": ..., "accessory": ...}
    combat: CombatState         # None when not in combat


class WorldState(TypedDict, total=False):
    current_scene: str
    location: str
    region: str
    npcs_present: list[NpcInfo]
    active_quests: list[QuestInfo]
    discovered_locations: list[str]
    lore_facts: list[str]
    turn_events: list[str]
    day_count: int


# ─────────────────────────────────────────────────────────────────────────────
# Top-level game state (what flows through agents)
# ─────────────────────────────────────────────────────────────────────────────


class GameState(TypedDict, total=False):
    # ── Meta ──
    turn_count: int
    game_started: bool
    game_over: bool
    game_over_reason: str

    # ── Core ──
    character: CharacterState
    world: WorldState

    # ── Run metadata ──
    thread_id: str
    run_id: str
    started_at: str
    model: str
    base_url: str
    api_key_set: bool

    # ── Agent I/O ──
    user_input: str
    system_message: str
    user_message: str
    messages: Append

    # ── Narrator output ──
    narrative: str
    state_delta: dict
    choices: list[str]

    # ── Judge output ──
    approved: bool
    corrected_delta: dict
    judgment_note: str
    review_score: int

    # ── World Builder output ──
    world_description: str
    generated_data: dict
    opening_narrative: str
    generation_type: str

    # ── Final ──
    output_text: str
    output_path: str
    audit_path: str
    usage: dict
    elapsed_ms: int
    llm_error: str
    finished_at: str
