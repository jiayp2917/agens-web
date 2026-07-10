"""Tests for the Realm system — breakthrough logic and spirit root modifiers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agens_novel.game.constants import REALM_CONFIGS, REALM_ORDER, SPIRIT_ROOTS
from agens_novel.game.realm import RealmConfig, RealmSystem


class TestRealmConfig:
    """Test RealmConfig dataclass."""

    def test_from_dict(self):
        data = REALM_CONFIGS["练气"]
        cfg = RealmConfig.from_dict(data)
        assert cfg.name == "练气"
        assert cfg.stages == 9
        assert cfg.lifespan == 100
        assert cfg.breakthrough_requirements
        assert cfg.breakthrough_base_rate == 0.80

    def test_from_dict_defaults(self):
        cfg = RealmConfig.from_dict({})
        assert cfg.name == ""
        assert cfg.stages == 1
        assert cfg.lifespan == 100
        assert cfg.breakthrough_requirements == []
        assert cfg.breakthrough_base_rate == 0.80

    def test_from_dict_preserves_spirit_root_bonus(self):
        data = REALM_CONFIGS["练气"]
        cfg = RealmConfig.from_dict(data)
        assert "天" in cfg.spirit_root_bonus
        assert cfg.spirit_root_bonus["天"] == 0.10


class TestRealmSystemInit:
    """Test RealmSystem initialization."""

    def test_all_realms_loaded(self):
        rs = RealmSystem()
        assert len(rs.REALMS) == 9
        for name in REALM_ORDER:
            assert name in rs.REALMS

    def test_realm_order_copied(self):
        rs = RealmSystem()
        assert rs.REALM_ORDER == list(REALM_ORDER)


class TestRealmSystemLookup:
    """Test get_realm_config and get_next_realm."""

    def test_get_realm_config_existing(self):
        rs = RealmSystem()
        cfg = rs.get_realm_config("练气")
        assert cfg is not None
        assert cfg.name == "练气"

    def test_get_realm_config_nonexistent(self):
        rs = RealmSystem()
        assert rs.get_realm_config("不存在的境界") is None

    def test_get_next_realm(self):
        rs = RealmSystem()
        assert rs.get_next_realm("练气") == "筑基"
        assert rs.get_next_realm("筑基") == "金丹"
        assert rs.get_next_realm("化神") == "合体"

    def test_get_next_realm_last(self):
        rs = RealmSystem()
        assert rs.get_next_realm("飞升") is None

    def test_get_next_realm_invalid(self):
        rs = RealmSystem()
        assert rs.get_next_realm("不存在的境界") is None


def _make_session(**overrides):
    """Create a mock session with default values."""
    defaults = {
        "realm": "练气",
        "realm_stage": 9,       # final stage of 练气 (9 stages)
        "breakthrough_flags": [
            "foundation_aid",
            "golden_core_aid",
            "nascent_soul_aid",
            "spirit_transformation_aid",
            "unity_law_aid",
            "mahayana_vow_aid",
            "tribulation_preparation",
            "tribulation_elixir",
            "ascension_protection",
        ],
        "game_over": False,
        "spirit_root": "",
        "spirit_root_grade": "",
        "char_name": "测试",
    }
    defaults.update(overrides)
    session = MagicMock()
    for k, v in defaults.items():
        setattr(session, k, v)
    return session


class TestCanAttemptBreakthrough:
    """Test breakthrough eligibility logic."""

    def test_eligible_liangqi_to_zhuji(self):
        rs = RealmSystem()
        session = _make_session(realm="练气", realm_stage=9)
        can, reason = rs.can_attempt_breakthrough(session)
        assert can is True
        assert reason == ""

    def test_not_eligible_game_over(self):
        rs = RealmSystem()
        session = _make_session(game_over=True)
        can, reason = rs.can_attempt_breakthrough(session)
        assert can is False
        assert "结束" in reason

    def test_not_eligible_unknown_realm(self):
        rs = RealmSystem()
        session = _make_session(realm="不存在的境界")
        can, reason = rs.can_attempt_breakthrough(session)
        assert can is False
        assert "未知" in reason

    def test_not_eligible_not_final_stage(self):
        rs = RealmSystem()
        # 练气 has 9 stages, so stage 5 is not final
        session = _make_session(realm="练气", realm_stage=5)
        can, reason = rs.can_attempt_breakthrough(session)
        assert can is False
        assert "层" in reason

    def test_not_eligible_missing_breakthrough_resource(self):
        rs = RealmSystem()
        session = _make_session(
            realm="练气", realm_stage=9, breakthrough_flags=[],
        )
        can, reason = rs.can_attempt_breakthrough(session)
        assert can is False
        assert "破境准备不足" in reason
        assert "筑基" in reason

    def test_inventory_item_can_satisfy_requirement(self):
        rs = RealmSystem()
        session = _make_session(
            realm="练气", realm_stage=9,
            breakthrough_flags=[],
            inventory=[{"name": "筑基丹", "type": "丹药"}],
        )
        can, reason = rs.can_attempt_breakthrough(session)
        assert can is True
        assert reason == ""

    def test_tribulation_to_ascension_requires_elixir_and_protection(self):
        rs = RealmSystem()
        session = _make_session(
            realm="渡劫", realm_stage=4,
            breakthrough_flags=["tribulation_elixir"],
        )
        can, reason = rs.can_attempt_breakthrough(session)
        assert can is False
        assert "护身法宝" in reason or "雷劫阵法" in reason

    def test_not_eligible_max_realm(self):
        rs = RealmSystem()
        session = _make_session(realm="飞升", realm_stage=1)
        can, reason = rs.can_attempt_breakthrough(session)
        assert can is False
        assert "最高" in reason

    def test_eligible_reserved_realm_huati(self):
        """v0.4: 合体 (and all 9 realms) are now eligible for breakthrough."""
        rs = RealmSystem()
        session = _make_session(realm="合体", realm_stage=4)
        can, reason = rs.can_attempt_breakthrough(session)
        assert can is True

    def test_eligible_zhuji_to_jindan(self):
        rs = RealmSystem()
        session = _make_session(realm="筑基", realm_stage=4)
        can, reason = rs.can_attempt_breakthrough(session)
        assert can is True


class TestCalculateBreakthroughRate:
    """Test breakthrough rate calculation."""

    def test_base_rate_liangqi(self):
        rs = RealmSystem()
        session = _make_session(realm="练气", spirit_root="", spirit_root_grade="")
        rate = rs.calculate_breakthrough_rate(session)
        assert rate == 0.80

    def test_earth_spirit_root_bonus(self):
        rs = RealmSystem()
        session = _make_session(realm="练气", spirit_root="金灵根", spirit_root_grade="地")
        rate = rs.calculate_breakthrough_rate(session)
        # 0.80 base + 0.05 breakthrough_bonus = 0.85
        assert rate == pytest.approx(0.85)

    def test_heaven_spirit_root_bonus(self):
        rs = RealmSystem()
        session = _make_session(realm="练气", spirit_root="冰灵根", spirit_root_grade="天")
        rate = rs.calculate_breakthrough_rate(session)
        # 0.80 base + 0.10 breakthrough_bonus = 0.90
        assert rate == pytest.approx(0.90)

    def test_rate_lower_for_higher_realm(self):
        rs = RealmSystem()
        s1 = _make_session(realm="练气")
        s2 = _make_session(realm="筑基")
        s3 = _make_session(realm="金丹")
        assert rs.calculate_breakthrough_rate(s1) > rs.calculate_breakthrough_rate(s2)
        assert rs.calculate_breakthrough_rate(s2) > rs.calculate_breakthrough_rate(s3)

    def test_unknown_realm_returns_zero(self):
        rs = RealmSystem()
        session = _make_session(realm="不存在的境界")
        rate = rs.calculate_breakthrough_rate(session)
        assert rate == 0.0

    def test_rate_clamped_to_one(self):
        """Ensure rate doesn't exceed 1.0 even with bonuses."""
        rs = RealmSystem()
        session = _make_session(realm="练气", spirit_root="冰灵根", spirit_root_grade="天")
        rate = rs.calculate_breakthrough_rate(session)
        assert rate <= 1.0

    def test_rate_with_spirit_root_but_no_grade(self):
        """If spirit_root is set but spirit_root_grade is empty, no bonus applied."""
        rs = RealmSystem()
        session = _make_session(realm="练气", spirit_root="冰灵根", spirit_root_grade="")
        rate = rs.calculate_breakthrough_rate(session)
        assert rate == 0.80  # no bonus since grade is empty


class TestStageAdvancePacing:
    """Chronicle pacing guards for small-realm advancement."""

    def test_qi_refining_does_not_lag_after_many_years(self):
        rs = RealmSystem()
        session = _make_session(
            realm="练气",
            realm_stage=3,
            age=29,
            turn_count=10,
            attributes={"comprehension": 5, "root_bone": 5},
        )

        delta = rs.try_advance_stage(session)

        assert delta is not None
        assert delta["character"]["realm_stage"] >= 4
        assert delta["meta"]["stage_advance_reason"] == "chronicle_pace"

    def test_attribute_scale_accepts_character_creation_points(self):
        rs = RealmSystem()
        session = _make_session(
            realm="练气",
            realm_stage=1,
            age=16,
            turn_count=0,
            attributes={"comprehension": 8, "root_bone": 8},
        )

        with patch("agens_novel.game.realm.random.random", return_value=0.39):
            delta = rs.try_advance_stage(session)

        assert delta is not None
        assert delta["character"]["realm_stage"] == 2

    def test_stage_advance_migrates_legacy_percent_attributes(self):
        rs = RealmSystem()
        session = _make_session(
            realm="练气",
            realm_stage=1,
            age=16,
            turn_count=0,
            attributes={"comprehension": 80, "root_bone": 80},
        )

        with patch("agens_novel.game.realm.random.random", return_value=0.39):
            delta = rs.try_advance_stage(session)

        assert delta is not None
        assert delta["character"]["realm_stage"] == 2


class TestAttemptBreakthrough:
    """Test breakthrough execution."""

    def test_ineligible_returns_ineligible(self):
        rs = RealmSystem()
        session = _make_session(realm="练气", realm_stage=5)  # not final stage
        result = rs.attempt_breakthrough(session)
        assert result["meta"]["breakthrough_result"] == "ineligible"

    def test_success_returns_correct_delta(self):
        rs = RealmSystem()
        session = _make_session(realm="练气", realm_stage=9)
        # Force success
        import agens_novel.game.realm as realm_mod
        original_random = realm_mod.random.random
        realm_mod.random.random = lambda: 0.0  # always succeed
        try:
            result = rs.attempt_breakthrough(session)
        finally:
            realm_mod.random.random = original_random

        assert result["meta"]["breakthrough_result"] == "success"
        assert result["meta"]["new_realm"] == "筑基"
        assert result["character"]["realm"] == "筑基"
        assert result["character"]["realm_stage"] == 1

    def test_failure_returns_correct_delta(self):
        rs = RealmSystem()
        session = _make_session(realm="练气", realm_stage=9)
        # Force failure
        import agens_novel.game.realm as realm_mod
        original_random = realm_mod.random.random
        realm_mod.random.random = lambda: 0.99  # always fail
        try:
            result = rs.attempt_breakthrough(session)
        finally:
            realm_mod.random.random = original_random

        assert result["meta"]["breakthrough_result"] == "failure"
        assert result["meta"]["status_effect_add"] == "走火入魔"
        assert result["character"] == {}


class TestGetSpiritRootModifier:
    """Test spirit root modifier lookup."""

    def test_earth_root_modifier(self):
        rs = RealmSystem()
        mod = rs.get_spirit_root_modifier("金灵根")
        assert mod["cultivation_bonus"] == 1.2
        assert mod["breakthrough_bonus"] == 0.05

    def test_heaven_root_modifier(self):
        rs = RealmSystem()
        mod = rs.get_spirit_root_modifier("冰灵根")
        assert mod["cultivation_bonus"] == 1.5
        assert mod["breakthrough_bonus"] == 0.10

    def test_all_eight_roots_have_modifiers(self):
        rs = RealmSystem()
        for sr in SPIRIT_ROOTS:
            mod = rs.get_spirit_root_modifier(sr["name"])
            assert mod["cultivation_bonus"] == sr["cultivation_bonus"]
            assert mod["breakthrough_bonus"] == sr["breakthrough_bonus"]

    def test_unknown_root_returns_default(self):
        rs = RealmSystem()
        mod = rs.get_spirit_root_modifier("不存在的灵根")
        assert mod["cultivation_bonus"] == 1.0
        assert mod["breakthrough_bonus"] == 0.0
