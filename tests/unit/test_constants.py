"""Tests for game constants — validates 9 realms, 8 spirit roots, etc."""

from __future__ import annotations

import pytest

from agens_novel.game.constants import (
    REALM_ORDER,
    REALM_CONFIGS,
    SPIRIT_ROOTS,
    SPIRIT_ROOT_MAP,
    SPIRIT_ROOT_GRADES,
    RARITY_ORDER,
    RARITY_MULTIPLIER,
    EQUIPMENT_SLOTS,
    DEFAULT_EQUIPMENT_SLOTS,
    COMBAT_ACTIONS,
    COMBAT_PHASES,
    NPC_AFFINITY_NEUTRAL,
    NPC_AFFINITY_FRIENDLY,
    NPC_AFFINITY_HOSTILE,
    QUEST_TYPES,
    ITEM_TYPES,
    TECHNIQUE_TYPES,
)


class TestRealmConstants:
    """Validate 9 realm definitions."""

    def test_realm_order_has_9_entries(self):
        assert len(REALM_ORDER) == 9

    def test_realm_order_names(self):
        expected = ["练气", "筑基", "金丹", "元婴", "化神", "合体", "大乘", "渡劫", "飞升"]
        assert REALM_ORDER == expected

    def test_realm_configs_has_all_9(self):
        for name in REALM_ORDER:
            assert name in REALM_CONFIGS, f"Missing realm config for: {name}"

    def test_realm_configs_required_fields(self):
        required_keys = {"name", "stages", "experience_required", "breakthrough_base_rate", "hp_base", "mp_base", "spirit_root_bonus"}
        for name, cfg in REALM_CONFIGS.items():
            missing = required_keys - set(cfg.keys())
            assert not missing, f"Realm {name} missing keys: {missing}"

    def test_realm_configs_name_matches_key(self):
        for key, cfg in REALM_CONFIGS.items():
            assert cfg["name"] == key

    def test_realm_configs_stages_positive(self):
        for name, cfg in REALM_CONFIGS.items():
            assert cfg["stages"] >= 1, f"Realm {name} has stages < 1"

    def test_realm_configs_experience_positive(self):
        for name, cfg in REALM_CONFIGS.items():
            assert cfg["experience_required"] > 0, f"Realm {name} has non-positive experience_required"

    def test_realm_configs_base_rate_in_range(self):
        for name, cfg in REALM_CONFIGS.items():
            rate = cfg["breakthrough_base_rate"]
            assert 0.0 <= rate <= 1.0, f"Realm {name} base rate {rate} out of [0,1]"

    def test_realm_configs_hp_mp_positive(self):
        for name, cfg in REALM_CONFIGS.items():
            assert cfg["hp_base"] > 0, f"Realm {name} hp_base <= 0"
            assert cfg["mp_base"] > 0, f"Realm {name} mp_base <= 0"

    def test_realm_experience_monotonically_increasing(self):
        exps = [REALM_CONFIGS[name]["experience_required"] for name in REALM_ORDER]
        for i in range(len(exps) - 1):
            assert exps[i] < exps[i + 1], f"Experience not increasing: {REALM_ORDER[i]}({exps[i]}) vs {REALM_ORDER[i+1]}({exps[i+1]})"

    def test_flying_realm_zero_breakthrough(self):
        """飞升 (final realm) should have 0% breakthrough rate."""
        assert REALM_CONFIGS["飞升"]["breakthrough_base_rate"] == 0.0

    def test_first_5_realms_have_spirit_root_bonus(self):
        for name in REALM_ORDER[:5]:
            bonus = REALM_CONFIGS[name]["spirit_root_bonus"]
            assert "天" in bonus, f"Realm {name} missing 天 spirit_root_bonus"
            assert "地" in bonus, f"Realm {name} missing 地 spirit_root_bonus"


class TestSpiritRootConstants:
    """Validate 8 spirit root definitions."""

    def test_spirit_roots_count(self):
        assert len(SPIRIT_ROOTS) == 8

    def test_five_elemental_roots(self):
        elements = {"金", "木", "水", "火", "土"}
        found = {sr["element"] for sr in SPIRIT_ROOTS[:5]}
        assert found == elements

    def test_three_heavenly_roots(self):
        elements = {"冰", "雷", "风"}
        found = {sr["element"] for sr in SPIRIT_ROOTS[5:]}
        assert found == elements

    def test_earth_grade_for_elements(self):
        for sr in SPIRIT_ROOTS[:5]:
            assert sr["grade"] == "地", f"Elemental root {sr['name']} should be grade 地"

    def test_heaven_grade_for_special(self):
        for sr in SPIRIT_ROOTS[5:]:
            assert sr["grade"] == "天", f"Special root {sr['name']} should be grade 天"

    def test_earth_root_cultivation_bonus(self):
        for sr in SPIRIT_ROOTS[:5]:
            assert sr["cultivation_bonus"] == 1.2, f"Earth root {sr['name']} cultivation_bonus should be 1.2"

    def test_heaven_root_cultivation_bonus(self):
        for sr in SPIRIT_ROOTS[5:]:
            assert sr["cultivation_bonus"] == 1.5, f"Heaven root {sr['name']} cultivation_bonus should be 1.5"

    def test_earth_root_breakthrough_bonus(self):
        for sr in SPIRIT_ROOTS[:5]:
            assert sr["breakthrough_bonus"] == 0.05, f"Earth root {sr['name']} breakthrough_bonus should be 0.05"

    def test_heaven_root_breakthrough_bonus(self):
        for sr in SPIRIT_ROOTS[5:]:
            assert sr["breakthrough_bonus"] == 0.10, f"Heaven root {sr['name']} breakthrough_bonus should be 0.10"

    def test_spirit_root_map_complete(self):
        assert len(SPIRIT_ROOT_MAP) == 8
        for sr in SPIRIT_ROOTS:
            assert sr["name"] in SPIRIT_ROOT_MAP

    def test_spirit_root_grades(self):
        assert SPIRIT_ROOT_GRADES == ["天", "地", "玄", "黄"]


class TestRarityConstants:
    """Validate rarity levels and multipliers."""

    def test_rarity_order(self):
        assert RARITY_ORDER == ["凡品", "良品", "上品", "极品", "仙品"]

    def test_rarity_multiplier_keys(self):
        assert set(RARITY_MULTIPLIER.keys()) == set(RARITY_ORDER)

    def test_rarity_multipliers_monotonic(self):
        vals = [RARITY_MULTIPLIER[r] for r in RARITY_ORDER]
        for i in range(len(vals) - 1):
            assert vals[i] < vals[i + 1]


class TestEquipmentConstants:
    """Validate equipment slot definitions."""

    def test_equipment_slots(self):
        assert EQUIPMENT_SLOTS == ["weapon", "armor", "accessory"]

    def test_default_equipment_slots(self):
        assert set(DEFAULT_EQUIPMENT_SLOTS.keys()) == set(EQUIPMENT_SLOTS)
        for slot in EQUIPMENT_SLOTS:
            assert DEFAULT_EQUIPMENT_SLOTS[slot] is None


class TestCombatConstants:
    """Validate combat action and phase definitions."""

    def test_combat_actions(self):
        assert COMBAT_ACTIONS == ["attack", "technique", "item", "defend", "flee"]

    def test_combat_phases(self):
        assert "idle" in COMBAT_PHASES
        assert "player_turn" in COMBAT_PHASES
        assert "enemy_turn" in COMBAT_PHASES
        assert "victory" in COMBAT_PHASES
        assert "defeat" in COMBAT_PHASES

    def test_npc_affinity_defaults(self):
        assert NPC_AFFINITY_NEUTRAL == 0
        assert NPC_AFFINITY_FRIENDLY == 30
        assert NPC_AFFINITY_HOSTILE == -30

    def test_quest_types(self):
        assert QUEST_TYPES == ["主线", "支线", "日常", "隐藏"]

    def test_item_types(self):
        assert ITEM_TYPES == ["武器", "防具", "丹药", "材料", "其他"]

    def test_technique_types(self):
        assert TECHNIQUE_TYPES == ["内功", "外功", "术法", "身法"]
