"""Tests for v5 game constants."""

from __future__ import annotations

from agens_novel.game.constants import (
    ATTRIBUTE_KEYS,
    ATTRIBUTE_LABELS,
    CATALOG_RARITY_TIERS,
    DEFAULT_ATTRIBUTES,
    DEFAULT_EQUIPMENT_SLOTS,
    DIFFICULTY_OPTIONS,
    EQUIPMENT_SLOTS,
    FAMILY_BACKGROUNDS,
    ITEM_TYPES,
    NPC_AFFINITY_FRIENDLY,
    NPC_AFFINITY_HOSTILE,
    NPC_AFFINITY_NEUTRAL,
    QUEST_TYPES,
    REALM_CONFIGS,
    REALM_LIFESPAN_RANGES,
    REALM_LIFESPANS,
    REALM_ORDER,
    SPIRIT_ROOTS,
    SPIRIT_ROOT_GRADES,
    SPIRIT_ROOT_MAP,
    TALENT_OPTIONS,
    TECHNIQUE_TYPES,
    rarity_unlocked_for,
)


class TestRealmConstants:
    def test_realm_order_has_9_entries(self):
        assert REALM_ORDER == ["练气", "筑基", "金丹", "元婴", "化神", "合体", "大乘", "渡劫", "飞升"]

    def test_realm_configs_have_v5_fields(self):
        required_keys = {
            "name",
            "lifespan",
            "stages",
            "breakthrough_requirements",
            "breakthrough_base_rate",
            "spirit_root_bonus",
        }
        for name in REALM_ORDER:
            cfg = REALM_CONFIGS[name]
            assert required_keys.issubset(cfg)
            assert cfg["name"] == name
            assert cfg["lifespan"] == REALM_LIFESPANS[name]
            assert cfg["stages"] >= 1
            assert 0.0 <= cfg["breakthrough_base_rate"] <= 1.0

    def test_realm_lifespans_are_monotonic_caps(self):
        lifespans = [REALM_LIFESPANS[name] for name in REALM_ORDER]
        for current, nxt in zip(lifespans, lifespans[1:]):
            assert current < nxt

    def test_realm_lifespan_ranges_cover_legacy_caps(self):
        for name in REALM_ORDER:
            lower, upper = REALM_LIFESPAN_RANGES[name]
            assert lower <= REALM_LIFESPANS[name] <= upper
            assert lower <= upper

    def test_flying_realm_is_terminal(self):
        assert REALM_CONFIGS["飞升"]["breakthrough_base_rate"] == 0.0
        assert REALM_CONFIGS["飞升"]["stages"] == 1


class TestSpiritRootConstants:
    def test_spirit_roots_count_and_lookup(self):
        assert len(SPIRIT_ROOTS) == 8
        assert len(SPIRIT_ROOT_MAP) == 8
        for root in SPIRIT_ROOTS:
            assert root["name"] in SPIRIT_ROOT_MAP
            assert root["grade"] in SPIRIT_ROOT_GRADES
            assert root["cultivation_bonus"] > 0
            assert root["breakthrough_bonus"] >= 0

    def test_spirit_root_grades_are_internal_not_rarity_tiers(self):
        assert SPIRIT_ROOT_GRADES == ["天", "地", "玄", "黄"]


class TestCatalogRarityConstants:
    def test_six_color_tiers(self):
        keys = [tier["key"] for tier in CATALOG_RARITY_TIERS]
        assert keys == ["白", "绿", "蓝", "紫", "橙", "红"]

    def test_tier_weights_match_spec(self):
        weights = [tier["weight"] for tier in CATALOG_RARITY_TIERS]
        assert weights == [90, 60, 30, 14, 5, 1]

    def test_unlock_gates(self):
        assert rarity_unlocked_for(0, 0) == ["白", "绿", "蓝"]
        assert rarity_unlocked_for(1, 0) == ["白", "绿", "蓝", "紫"]
        assert rarity_unlocked_for(1, 1) == ["白", "绿", "蓝", "紫", "橙"]
        assert rarity_unlocked_for(1, 2) == ["白", "绿", "蓝", "紫", "橙", "红"]

    def test_random_unlock_gates(self):
        assert "红" not in rarity_unlocked_for(0, 2, for_random=True)
        assert "红" in rarity_unlocked_for(1, 2, for_random=True)


class TestSupportingConstants:
    def test_equipment_slots(self):
        assert EQUIPMENT_SLOTS == ["weapon", "armor", "accessory"]
        assert set(DEFAULT_EQUIPMENT_SLOTS) == set(EQUIPMENT_SLOTS)
        assert all(DEFAULT_EQUIPMENT_SLOTS[slot] is None for slot in EQUIPMENT_SLOTS)

    def test_npc_quest_item_and_technique_defaults(self):
        assert NPC_AFFINITY_NEUTRAL == 0
        assert NPC_AFFINITY_FRIENDLY == 30
        assert NPC_AFFINITY_HOSTILE == -30
        assert QUEST_TYPES == ["主线", "支线", "日常", "隐藏"]
        assert ITEM_TYPES == ["武器", "防具", "丹药", "材料", "其他"]
        assert TECHNIQUE_TYPES == ["内功", "外功", "术法", "身法"]

    def test_character_creation_options(self):
        assert "天命道胎" in TALENT_OPTIONS
        assert "隐世仙族" in FAMILY_BACKGROUNDS
        assert DIFFICULTY_OPTIONS == ["简单", "普通", "困难"]

    def test_six_attributes(self):
        assert ATTRIBUTE_KEYS == ["root_bone", "comprehension", "luck", "willpower", "physique", "soul"]
        assert set(DEFAULT_ATTRIBUTES) == set(ATTRIBUTE_KEYS)
        assert all(value == 5 for value in DEFAULT_ATTRIBUTES.values())
        assert ATTRIBUTE_LABELS["root_bone"] == "根骨"
        assert ATTRIBUTE_LABELS["soul"] == "神魂"

    def test_no_hidden_start_constants(self):
        import agens_novel.game.constants as constants

        assert not hasattr(constants, "SPECIAL_START_CODE")
        assert not hasattr(constants, "SPECIAL_START_NAME")
        assert not hasattr(constants, "SPECIAL_START_ATTRIBUTES")
