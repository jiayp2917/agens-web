"""Combat system — turn-based battle state machine.

Implements a semi-structured combat engine with states:
  idle → player_turn → enemy_turn → resolve → (idle | victory | defeat)

CombatActor and CombatState are TypedDicts matching game_schema.py definitions.
CombatEngine manages state transitions and damage calculations.
"""

from __future__ import annotations

import logging
import random
from typing import Any

from ..game.constants import (
    COMBAT_ACTIONS,
    REALM_ORDER,
)

log = logging.getLogger(__name__)


class CombatError(Exception):
    """Raised when combat operations fail unexpectedly."""


def _clamp(value: int, minimum: int = 0, maximum: int = 999999) -> int:
    """Clamp a value between min and max."""
    return max(minimum, min(maximum, value))


def _calculate_attack_damage(attacker: dict[str, Any], defender: dict[str, Any]) -> int:
    """Calculate basic attack damage with realm bonus and variance."""
    # Base damage from realm level.
    try:
        atk_idx = REALM_ORDER.index(attacker.get("realm", "练气"))
    except ValueError:
        atk_idx = 0
    try:
        def_idx = REALM_ORDER.index(defender.get("realm", "练气"))
    except ValueError:
        def_idx = 0

    # Base damage scales with realm.
    base_damage = 10 + atk_idx * 15 + attacker.get("hp_max", 100) // 20

    # Realm suppression: higher realm deals more, lower realm deals less.
    realm_diff = atk_idx - def_idx
    if realm_diff > 0:
        base_damage = int(base_damage * (1 + 0.3 * realm_diff))
    elif realm_diff < 0:
        base_damage = int(base_damage * max(0.3, 1 + 0.3 * realm_diff))

    # Variance: ±15%.
    variance = random.uniform(0.85, 1.15)
    damage = max(1, int(base_damage * variance))

    # Defender is defending: reduce by 50%.
    if defender.get("is_defending", False):
        damage = max(1, int(damage * 0.5))

    return damage


def _calculate_technique_damage(
    attacker: dict[str, Any],
    defender: dict[str, Any],
    technique: dict[str, Any],
) -> tuple[int, int]:
    """Calculate technique damage and MP cost.

    Returns: (damage, mp_cost)
    """
    mp_cost = technique.get("mp_cost", 10)

    # Check if attacker has enough MP.
    if attacker.get("mp", 0) < mp_cost:
        # Not enough MP, fall back to basic attack.
        return _calculate_attack_damage(attacker, defender), 0

    base_damage = _calculate_attack_damage(attacker, defender)

    # Technique multiplier based on element and rarity.
    element_mult = 1.5  # default technique multiplier
    tech_type = technique.get("type", "")
    if tech_type == "术法":
        element_mult = 2.0
    elif tech_type == "外功":
        element_mult = 1.8
    elif tech_type == "内功":
        element_mult = 1.3

    variance = random.uniform(0.90, 1.10)
    damage = max(1, int(base_damage * element_mult * variance))

    # Defender is defending.
    if defender.get("is_defending", False):
        damage = max(1, int(damage * 0.5))

    return damage, mp_cost


class CombatEngine:
    """Turn-based combat state machine.

    Manages combat flow: start → player_turn → enemy_turn → resolve.
    Uses semi-structured approach: numeric damage calculation + narrative overlay.
    """

    # ─────────────────────────────────────────────────────────────────────
    # Combat lifecycle
    # ─────────────────────────────────────────────────────────────────────

    def start_combat(
        self,
        session: Any,
        enemy_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Initialize a new combat encounter.

        Args:
            session: GameSession with current character state.
            enemy_data: Enemy info dict (from NpcInfo or narrator delta).

        Returns:
            CombatState dict with phase=player_turn.
        """
        player_actor: dict[str, Any] = {
            "name": getattr(session, "char_name", "修仙者"),
            "hp": getattr(session, "hp", 100),
            "hp_max": getattr(session, "hp_max", 100),
            "mp": getattr(session, "mp", 50),
            "mp_max": getattr(session, "mp_max", 50),
            "realm": getattr(session, "realm", "练气"),
            "techniques": list(getattr(session, "techniques", [])),
            "consumables": [
                item for item in getattr(session, "inventory", [])
                if isinstance(item, dict) and item.get("type") == "丹药"
            ],
            "is_defending": False,
        }

        enemy_actor: dict[str, Any] = {
            "name": enemy_data.get("name", "未知敌人"),
            "hp": enemy_data.get("hp", 50),
            "hp_max": enemy_data.get("hp_max", enemy_data.get("hp", 50)),
            "mp": enemy_data.get("mp", 30),
            "mp_max": enemy_data.get("mp_max", enemy_data.get("mp", 30)),
            "realm": enemy_data.get("realm", "练气"),
            "techniques": list(enemy_data.get("techniques", [])),
            "consumables": list(enemy_data.get("consumables", [])),
            "is_defending": False,
        }

        combat_state: dict[str, Any] = {
            "phase": "player_turn",
            "player": player_actor,
            "enemy": enemy_actor,
            "available_actions": list(COMBAT_ACTIONS),
            "turn_count": 1,
            "result": "",
            "narrative": f"遭遇{enemy_actor['name']}，战斗开始！",
        }

        return combat_state

    # ─────────────────────────────────────────────────────────────────────
    # Player actions
    # ─────────────────────────────────────────────────────────────────────

    def player_action(
        self,
        state: dict[str, Any],
        action: str,
        target: str = "",
    ) -> dict[str, Any]:
        """Process a player combat action.

        Args:
            state: Current CombatState.
            action: One of COMBAT_ACTIONS.
            target: Optional target (e.g. technique name, item name).

        Returns:
            Updated CombatState.
        """
        if state.get("phase") != "player_turn":
            log.warning("player_action called in wrong phase: %s", state.get("phase"))
            return state

        player = dict(state.get("player", {}))
        enemy = dict(state.get("enemy", {}))
        narrative = ""

        if action == "attack":
            damage = _calculate_attack_damage(player, enemy)
            enemy["hp"] = _clamp(enemy.get("hp", 0) - damage, 0)
            enemy["is_defending"] = False
            player["is_defending"] = False
            narrative = f"你发动攻击，造成{damage}点伤害！"

        elif action == "technique":
            # Find the technique by name.
            tech = None
            for t in player.get("techniques", []):
                if isinstance(t, dict) and (t.get("name") == target or not target):
                    tech = t
                    break

            if tech is None:
                # Fall back to basic attack.
                damage = _calculate_attack_damage(player, enemy)
                enemy["hp"] = _clamp(enemy.get("hp", 0) - damage, 0)
                narrative = f"灵力不足或功法不可用，改为普通攻击，造成{damage}点伤害。"
            else:
                damage, mp_cost = _calculate_technique_damage(player, enemy, tech)
                enemy["hp"] = _clamp(enemy.get("hp", 0) - damage, 0)
                player["mp"] = _clamp(player.get("mp", 0) - mp_cost, 0)
                narrative = f"你施展{tech.get('name', '功法')}，消耗{mp_cost}MP，造成{damage}点伤害！"

            player["is_defending"] = False
            enemy["is_defending"] = False

        elif action == "item":
            # Find a consumable.
            consumable = None
            for item in player.get("consumables", []):
                if isinstance(item, dict) and (item.get("name") == target or not target):
                    consumable = item
                    break

            if consumable is None:
                narrative = "没有可用的丹药！"
            else:
                effects = consumable.get("effects", {})
                for key, val in effects.items():
                    if key in ("hp", "mp") and isinstance(val, (int, str)):
                        heal = val
                        if isinstance(val, str):
                            heal = int(val.replace("+", ""))
                        player[key] = _clamp(
                            player.get(key, 0) + heal, 0, player.get(f"{key}_max", 999)
                        )
                # Remove used consumable.
                player["consumables"] = [
                    c for c in player.get("consumables", [])
                    if c is not consumable
                ]
                name = consumable.get("name", "丹药")
                narrative = f"你使用了{name}，恢复了生命值或灵力。"

            player["is_defending"] = False

        elif action == "defend":
            player["is_defending"] = True
            narrative = "你摆出防御姿态，减少受到的伤害。"

        elif action == "flee":
            flee_rate = 0.80
            # Check if enemy is a boss (no flee allowed).
            if enemy.get("is_boss", False):
                flee_rate = 0.0

            if random.random() < flee_rate:
                return {
                    **state,
                    "phase": "idle",
                    "result": "fled",
                    "player": player,
                    "enemy": enemy,
                    "narrative": "你成功脱离了战斗！",
                }
            else:
                narrative = "逃跑失败！"
                player["is_defending"] = False

        else:
            narrative = f"未知操作: {action}"

        # Check if enemy is defeated.
        if enemy.get("hp", 0) <= 0:
            return {
                **state,
                "phase": "victory",
                "result": "victory",
                "player": player,
                "enemy": enemy,
                "narrative": narrative,
            }

        # Transition to enemy turn.
        return {
            **state,
            "phase": "enemy_turn",
            "player": player,
            "enemy": enemy,
            "narrative": narrative,
        }

    # ─────────────────────────────────────────────────────────────────────
    # Enemy turn
    # ─────────────────────────────────────────────────────────────────────

    def enemy_turn(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute the enemy's turn automatically.

        Simple AI: use technique if MP available and player HP > 30%,
        otherwise basic attack.

        Returns:
            Updated CombatState with phase=player_turn or phase=defeat.
        """
        if state.get("phase") != "enemy_turn":
            log.warning("enemy_turn called in wrong phase: %s", state.get("phase"))
            return state

        enemy = dict(state.get("enemy", {}))
        player = dict(state.get("player", {}))
        narrative = ""

        # Reset player defending from previous turn if they didn't defend.
        # (player.is_defending was set during player_action)

        # Enemy AI: simple decision tree.
        enemy_mp = enemy.get("mp", 0)
        player_hp_pct = player.get("hp", 1) / max(1, player.get("hp_max", 1))

        # Try to use a technique if MP available and player is not low.
        tech_used = False
        if enemy_mp >= 10 and player_hp_pct > 0.2:
            for tech in enemy.get("techniques", []):
                if isinstance(tech, dict) and tech.get("mp_cost", 999) <= enemy_mp:
                    damage, mp_cost = _calculate_technique_damage(enemy, player, tech)
                    player["hp"] = _clamp(player.get("hp", 0) - damage, 0)
                    enemy["mp"] = _clamp(enemy_mp - mp_cost, 0)
                    enemy["is_defending"] = False
                    tech_name = tech.get("name", "功法")
                    narrative = f"{enemy.get('name', '敌人')}施展{tech_name}，对你造成{damage}点伤害！"
                    tech_used = True
                    break

        if not tech_used:
            # Basic attack.
            damage = _calculate_attack_damage(enemy, player)
            player["hp"] = _clamp(player.get("hp", 0) - damage, 0)
            enemy["is_defending"] = False
            narrative = f"{enemy.get('name', '敌人')}发动攻击，对你造成{damage}点伤害！"

        # Check if player is defeated.
        if player.get("hp", 0) <= 0:
            return {
                **state,
                "phase": "defeat",
                "result": "defeat",
                "player": player,
                "enemy": enemy,
                "narrative": narrative,
            }

        # Back to player turn.
        new_turn = state.get("turn_count", 1) + 1
        return {
            **state,
            "phase": "player_turn",
            "player": player,
            "enemy": enemy,
            "turn_count": new_turn,
            "available_actions": list(COMBAT_ACTIONS),
            "narrative": narrative,
        }

    # ─────────────────────────────────────────────────────────────────────
    # Resolution
    # ─────────────────────────────────────────────────────────────────────

    def resolve(self, state: dict[str, Any]) -> dict[str, Any]:
        """Resolve the combat and produce a final delta.

        Returns:
            Delta dict suitable for apply_delta().
        """
        result = state.get("result", "")
        player = state.get("player", {})
        enemy = state.get("enemy", {})

        if result == "victory":
            # Award experience and gold.
            try:
                enemy_idx = REALM_ORDER.index(enemy.get("realm", "练气"))
            except ValueError:
                enemy_idx = 0
            exp_gain = 20 + enemy_idx * 30
            gold_gain = 5 + enemy_idx * 10

            return {
                "character": {
                    "hp": str(player.get("hp", 0)),
                    "mp": str(player.get("mp", 0)),
                    "experience": f"+{exp_gain}",
                    "gold": f"+{gold_gain}",
                    "combat": None,
                },
                "meta": {
                    "combat_result": "victory",
                    "exp_gained": exp_gain,
                    "gold_gained": gold_gain,
                },
            }

        elif result == "defeat":
            return {
                "character": {
                    "hp": 0,
                    "combat": None,
                },
                "meta": {
                    "game_over": True,
                    "game_over_reason": f"被{enemy.get('name', '敌人')}击败，修真之路就此终结。",
                    "combat_result": "defeat",
                },
            }

        elif result == "fled":
            return {
                "character": {
                    "hp": str(player.get("hp", 0)),
                    "mp": str(player.get("mp", 0)),
                    "combat": None,
                },
                "meta": {
                    "combat_result": "fled",
                },
            }

        # Unknown state — reset combat.
        return {
            "character": {
                "combat": None,
            },
        }

    # ─────────────────────────────────────────────────────────────────────
    # Game over check
    # ─────────────────────────────────────────────────────────────────────

    def check_game_over(self, state: dict[str, Any]) -> bool:
        """Return True if combat results in player death."""
        return state.get("result") == "defeat" or state.get("phase") == "defeat"
