"""Tests for the Combat system — turn-based battle state machine."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from agens_novel.game.combat import CombatEngine, _clamp, _calculate_attack_damage


def _make_player(**overrides):
    defaults = {
        "name": "修仙者",
        "hp": 100,
        "hp_max": 100,
        "mp": 50,
        "mp_max": 50,
        "realm": "练气",
        "techniques": [{"name": "火球术", "type": "术法", "mp_cost": 15, "element": "火"}],
        "consumables": [{"name": "回血丹", "type": "丹药", "effects": {"hp": "+30"}}],
        "is_defending": False,
    }
    defaults.update(overrides)
    return defaults


def _make_enemy(**overrides):
    defaults = {
        "name": "妖兽",
        "hp": 80,
        "hp_max": 80,
        "mp": 30,
        "mp_max": 30,
        "realm": "练气",
        "techniques": [],
        "consumables": [],
        "is_defending": False,
    }
    defaults.update(overrides)
    return defaults


def _make_session(**overrides):
    defaults = {
        "char_name": "测试者",
        "hp": 100,
        "hp_max": 100,
        "mp": 50,
        "mp_max": 50,
        "realm": "练气",
        "techniques": [{"name": "火球术", "type": "术法", "mp_cost": 15, "element": "火"}],
        "inventory": [{"name": "回血丹", "type": "丹药", "effects": {"hp": "+30"}}],
    }
    defaults.update(overrides)
    return MagicMock(**{k: v for k, v in defaults.items()})


class TestClamp:
    def test_clamp_normal(self):
        assert _clamp(50) == 50

    def test_clamp_below_min(self):
        assert _clamp(-5, 0) == 0

    def test_clamp_above_max(self):
        assert _clamp(9999999, 0, 999999) == 999999

    def test_clamp_at_boundaries(self):
        assert _clamp(0, 0) == 0
        assert _clamp(999999, 0, 999999) == 999999


class TestCalculateAttackDamage:
    def test_damage_is_positive(self):
        attacker = _make_player()
        defender = _make_enemy()
        for _ in range(20):  # variance makes it non-deterministic
            damage = _calculate_attack_damage(attacker, defender)
            assert damage >= 1

    def test_higher_realm_more_damage(self):
        # Same realm should do less damage than higher realm
        attacker_same = _make_player(realm="练气", hp_max=100)
        attacker_higher = _make_player(realm="筑基", hp_max=200)
        defender = _make_enemy(realm="练气")

        # Average over multiple samples to reduce variance
        import agens_novel.game.combat as combat_mod
        orig = combat_mod.random.uniform
        combat_mod.random.uniform = lambda a, b: 1.0  # no variance
        try:
            dmg_same = _calculate_attack_damage(attacker_same, defender)
            dmg_higher = _calculate_attack_damage(attacker_higher, defender)
        finally:
            combat_mod.random.uniform = orig

        assert dmg_higher > dmg_same

    def test_defending_halves_damage(self):
        import agens_novel.game.combat as combat_mod
        orig = combat_mod.random.uniform
        combat_mod.random.uniform = lambda a, b: 1.0

        try:
            defender_normal = _make_enemy(is_defending=False)
            defender_defending = _make_enemy(is_defending=True)
            attacker = _make_player()

            dmg_normal = _calculate_attack_damage(attacker, defender_normal)
            dmg_defending = _calculate_attack_damage(attacker, defender_defending)
        finally:
            combat_mod.random.uniform = orig

        assert dmg_defending < dmg_normal
        # Defending should reduce by 50%
        assert dmg_defending == max(1, int(dmg_normal * 0.5))

    def test_unknown_realm_defaults_to_liangqi(self):
        attacker = _make_player(realm="不存在的境界")
        defender = _make_enemy(realm="不存在的境界")
        import agens_novel.game.combat as combat_mod
        orig = combat_mod.random.uniform
        combat_mod.random.uniform = lambda a, b: 1.0
        try:
            dmg = _calculate_attack_damage(attacker, defender)
            assert dmg >= 1
        finally:
            combat_mod.random.uniform = orig


class TestCombatEngineStartCombat:
    def test_start_combat_returns_correct_state(self):
        engine = CombatEngine()
        session = _make_session()
        enemy_data = _make_enemy()

        state = engine.start_combat(session, enemy_data)

        assert state["phase"] == "player_turn"
        assert state["player"]["name"] == "测试者"
        assert state["enemy"]["name"] == "妖兽"
        assert state["player"]["hp"] == 100
        assert state["enemy"]["hp"] == 80
        assert state["player"]["is_defending"] is False
        assert state["enemy"]["is_defending"] is False
        assert state["turn_count"] == 1
        assert state["result"] == ""

    def test_start_combat_actions_available(self):
        engine = CombatEngine()
        session = _make_session()
        enemy_data = _make_enemy()

        state = engine.start_combat(session, enemy_data)
        assert set(state["available_actions"]) == {"attack", "technique", "item", "defend", "flee"}

    def test_start_combat_consumables_filtered(self):
        """Only items with type='丹药' should be included in consumables."""
        engine = CombatEngine()
        session = _make_session(inventory=[
            {"name": "回血丹", "type": "丹药", "effects": {"hp": "+30"}},
            {"name": "铁剑", "type": "武器"},
        ])
        enemy_data = _make_enemy()

        state = engine.start_combat(session, enemy_data)
        assert len(state["player"]["consumables"]) == 1
        assert state["player"]["consumables"][0]["name"] == "回血丹"


class TestCombatEnginePlayerAttack:
    def test_attack_reduces_enemy_hp(self):
        engine = CombatEngine()
        state = {"phase": "player_turn", "player": _make_player(), "enemy": _make_enemy(hp=80)}
        import agens_novel.game.combat as combat_mod
        orig = combat_mod.random.uniform
        combat_mod.random.uniform = lambda a, b: 1.0
        try:
            result = engine.player_action(state, "attack")
        finally:
            combat_mod.random.uniform = orig

        assert result["enemy"]["hp"] < 80
        assert result["phase"] == "enemy_turn"
        assert result["player"]["is_defending"] is False

    def test_attack_kills_enemy_victory(self):
        engine = CombatEngine()
        state = {"phase": "player_turn", "player": _make_player(realm="化神", hp_max=1600), "enemy": _make_enemy(hp=1, hp_max=1)}
        import agens_novel.game.combat as combat_mod
        orig = combat_mod.random.uniform
        combat_mod.random.uniform = lambda a, b: 1.0
        try:
            result = engine.player_action(state, "attack")
        finally:
            combat_mod.random.uniform = orig

        assert result["phase"] == "victory"
        assert result["result"] == "victory"

    def test_wrong_phase_returns_unchanged(self):
        engine = CombatEngine()
        state = {"phase": "enemy_turn", "player": _make_player(), "enemy": _make_enemy()}
        result = engine.player_action(state, "attack")
        assert result is state  # same object returned


class TestCombatEnginePlayerTechnique:
    def test_technique_uses_mp_and_does_damage(self):
        engine = CombatEngine()
        player = _make_player(mp=50)
        enemy = _make_enemy(hp=80)
        state = {"phase": "player_turn", "player": player, "enemy": enemy}

        import agens_novel.game.combat as combat_mod
        orig = combat_mod.random.uniform
        combat_mod.random.uniform = lambda a, b: 1.0
        try:
            result = engine.player_action(state, "technique", "火球术")
        finally:
            combat_mod.random.uniform = orig

        assert result["player"]["mp"] < 50  # MP consumed
        assert result["enemy"]["hp"] < 80  # Damage dealt
        assert result["player"]["is_defending"] is False

    def test_technique_no_mp_falls_back_to_attack(self):
        engine = CombatEngine()
        player = _make_player(mp=0)
        enemy = _make_enemy(hp=80)
        state = {"phase": "player_turn", "player": player, "enemy": enemy}

        import agens_novel.game.combat as combat_mod
        orig = combat_mod.random.uniform
        combat_mod.random.uniform = lambda a, b: 1.0
        try:
            result = engine.player_action(state, "technique", "火球术")
        finally:
            combat_mod.random.uniform = orig

        # Should fall back to basic attack — enemy still takes damage, no MP consumed
        assert result["enemy"]["hp"] < 80
        assert result["player"]["mp"] == 0  # no MP consumed

    def test_technique_not_found_falls_back(self):
        engine = CombatEngine()
        player = _make_player(mp=50)
        enemy = _make_enemy(hp=80)
        state = {"phase": "player_turn", "player": player, "enemy": enemy}

        import agens_novel.game.combat as combat_mod
        orig = combat_mod.random.uniform
        combat_mod.random.uniform = lambda a, b: 1.0
        try:
            result = engine.player_action(state, "technique", "不存在的功法")
        finally:
            combat_mod.random.uniform = orig

        # Falls back to basic attack
        assert result["enemy"]["hp"] < 80


class TestCombatEnginePlayerItem:
    def test_item_heals_player(self):
        engine = CombatEngine()
        player = _make_player(hp=50, hp_max=100)
        enemy = _make_enemy()
        state = {"phase": "player_turn", "player": player, "enemy": enemy}

        result = engine.player_action(state, "item", "回血丹")

        assert result["player"]["hp"] > 50  # healed
        assert len(result["player"]["consumables"]) == 0  # consumed

    def test_item_not_found_no_effect(self):
        engine = CombatEngine()
        player = _make_player(hp=50)
        enemy = _make_enemy()
        state = {"phase": "player_turn", "player": player, "enemy": enemy}

        result = engine.player_action(state, "item", "不存在的丹药")

        # No healing, no crash
        assert result["player"]["hp"] == 50

    def test_item_hp_capped_at_max(self):
        engine = CombatEngine()
        player = _make_player(hp=95, hp_max=100, consumables=[{"name": "大还丹", "type": "丹药", "effects": {"hp": "+50"}}])
        enemy = _make_enemy()
        state = {"phase": "player_turn", "player": player, "enemy": enemy}

        result = engine.player_action(state, "item", "大还丹")

        assert result["player"]["hp"] <= 100  # capped at hp_max


class TestCombatEnginePlayerDefend:
    def test_defend_sets_flag(self):
        engine = CombatEngine()
        player = _make_player()
        enemy = _make_enemy()
        state = {"phase": "player_turn", "player": player, "enemy": enemy}

        result = engine.player_action(state, "defend")

        assert result["player"]["is_defending"] is True


class TestCombatEnginePlayerFlee:
    def test_flee_success(self):
        engine = CombatEngine()
        player = _make_player()
        enemy = _make_enemy()
        state = {"phase": "player_turn", "player": player, "enemy": enemy}

        import agens_novel.game.combat as combat_mod
        orig = combat_mod.random.random
        combat_mod.random.random = lambda: 0.0  # succeed flee
        try:
            result = engine.player_action(state, "flee")
        finally:
            combat_mod.random.random = orig

        assert result["phase"] == "idle"
        assert result["result"] == "fled"

    def test_flee_failure(self):
        engine = CombatEngine()
        player = _make_player()
        enemy = _make_enemy()
        state = {"phase": "player_turn", "player": player, "enemy": enemy}

        import agens_novel.game.combat as combat_mod
        orig = combat_mod.random.random
        combat_mod.random.random = lambda: 0.99  # fail flee
        try:
            result = engine.player_action(state, "flee")
        finally:
            combat_mod.random.random = orig

        assert result["phase"] == "enemy_turn"
        assert result["player"]["is_defending"] is False

    def test_flee_boss_impossible(self):
        engine = CombatEngine()
        player = _make_player()
        enemy = _make_enemy(is_boss=True)
        state = {"phase": "player_turn", "player": player, "enemy": enemy}

        import agens_novel.game.combat as combat_mod
        orig = combat_mod.random.random
        combat_mod.random.random = lambda: 0.0  # would succeed normally
        try:
            result = engine.player_action(state, "flee")
        finally:
            combat_mod.random.random = orig

        # Boss: flee_rate = 0.0, so random.random() < 0.0 is never True
        assert result["phase"] == "enemy_turn"


class TestCombatEngineEnemyTurn:
    def test_enemy_turn_deals_damage(self):
        engine = CombatEngine()
        player = _make_player(hp=100)
        enemy = _make_enemy(mp=0)  # no MP → basic attack
        state = {"phase": "enemy_turn", "player": player, "enemy": enemy, "turn_count": 1}

        import agens_novel.game.combat as combat_mod
        orig = combat_mod.random.uniform
        combat_mod.random.uniform = lambda a, b: 1.0
        try:
            result = engine.enemy_turn(state)
        finally:
            combat_mod.random.uniform = orig

        assert result["player"]["hp"] < 100
        assert result["phase"] == "player_turn"
        assert result["turn_count"] == 2

    def test_enemy_kills_player_defeat(self):
        engine = CombatEngine()
        player = _make_player(hp=1, hp_max=1)
        enemy = _make_enemy(realm="化神", hp_max=1600, mp=0)  # very strong
        state = {"phase": "enemy_turn", "player": player, "enemy": enemy, "turn_count": 1}

        import agens_novel.game.combat as combat_mod
        orig = combat_mod.random.uniform
        combat_mod.random.uniform = lambda a, b: 1.0
        try:
            result = engine.enemy_turn(state)
        finally:
            combat_mod.random.uniform = orig

        assert result["phase"] == "defeat"
        assert result["result"] == "defeat"

    def test_wrong_phase_returns_unchanged(self):
        engine = CombatEngine()
        state = {"phase": "player_turn", "player": _make_player(), "enemy": _make_enemy()}
        result = engine.enemy_turn(state)
        assert result is state

    def test_enemy_uses_technique_if_available(self):
        engine = CombatEngine()
        player = _make_player(hp=100, hp_max=100)
        enemy = _make_enemy(
            mp=50, mp_max=50,
            techniques=[{"name": "毒雾术", "mp_cost": 15, "element": "木"}]
        )
        state = {"phase": "enemy_turn", "player": player, "enemy": enemy, "turn_count": 1}

        import agens_novel.game.combat as combat_mod
        orig = combat_mod.random.uniform
        combat_mod.random.uniform = lambda a, b: 1.0
        try:
            result = engine.enemy_turn(state)
        finally:
            combat_mod.random.uniform = orig

        # MP should be consumed if technique was used
        assert result["enemy"]["mp"] < 50 or result["player"]["hp"] < 100


class TestCombatEngineResolve:
    def test_victory_resolve(self):
        engine = CombatEngine()
        state = {
            "result": "victory",
            "player": {"hp": 80, "mp": 30},
            "enemy": {"realm": "练气"},
        }
        delta = engine.resolve(state)
        assert delta["meta"]["combat_result"] == "victory"
        assert delta["character"]["combat"] is None
        assert "experience" in delta["character"]
        assert delta["character"]["experience"].startswith("+")

    def test_defeat_resolve(self):
        engine = CombatEngine()
        state = {
            "result": "defeat",
            "player": {"hp": 0, "mp": 0},
            "enemy": {"name": "妖兽", "realm": "筑基"},
        }
        delta = engine.resolve(state)
        assert delta["meta"]["combat_result"] == "defeat"
        assert delta["meta"]["game_over"] is True
        assert delta["character"]["combat"] is None

    def test_fled_resolve(self):
        engine = CombatEngine()
        state = {
            "result": "fled",
            "player": {"hp": 70, "mp": 40},
            "enemy": {},
        }
        delta = engine.resolve(state)
        assert delta["meta"]["combat_result"] == "fled"
        assert delta["character"]["combat"] is None

    def test_unknown_resolve_clears_combat(self):
        engine = CombatEngine()
        state = {"result": "", "player": {}, "enemy": {}}
        delta = engine.resolve(state)
        assert delta["character"]["combat"] is None


class TestCombatEngineCheckGameOver:
    def test_defeat_result(self):
        engine = CombatEngine()
        assert engine.check_game_over({"result": "defeat"}) is True

    def test_defeat_phase(self):
        engine = CombatEngine()
        assert engine.check_game_over({"phase": "defeat"}) is True

    def test_not_game_over(self):
        engine = CombatEngine()
        assert engine.check_game_over({"result": "victory"}) is False
        assert engine.check_game_over({"phase": "player_turn"}) is False


class TestCombatFullFlow:
    """Integration test: full combat flow from start to resolution."""

    def test_full_combat_victory(self):
        engine = CombatEngine()
        session = _make_session(hp=100, hp_max=100, mp=50, mp_max=50, realm="化神")
        enemy_data = _make_enemy(hp=1, hp_max=1, mp=0, realm="练气")

        # Start combat
        state = engine.start_combat(session, enemy_data)
        assert state["phase"] == "player_turn"

        # Player attacks — should kill enemy
        import agens_novel.game.combat as combat_mod
        orig = combat_mod.random.uniform
        combat_mod.random.uniform = lambda a, b: 1.0
        try:
            state = engine.player_action(state, "attack")
        finally:
            combat_mod.random.uniform = orig

        assert state["phase"] == "victory"

        # Resolve
        delta = engine.resolve(state)
        assert delta["meta"]["combat_result"] == "victory"

    def test_full_combat_defeat(self):
        engine = CombatEngine()
        session = _make_session(hp=1, hp_max=1, mp=0, realm="练气")
        enemy_data = _make_enemy(hp=80, hp_max=80, mp=0, realm="化神")

        state = engine.start_combat(session, enemy_data)

        # Player attacks (won't kill)
        import agens_novel.game.combat as combat_mod
        orig = combat_mod.random.uniform
        combat_mod.random.uniform = lambda a, b: 1.0
        try:
            state = engine.player_action(state, "attack")
            # Enemy turn — should kill player
            if state.get("phase") == "enemy_turn":
                state = engine.enemy_turn(state)
        finally:
            combat_mod.random.uniform = orig

        assert state["phase"] == "defeat"
