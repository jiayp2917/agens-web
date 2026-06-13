"""Tests for the Realm system — breakthrough logic and spirit root modifiers."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from agens_novel.game.realm import RealmSystem, RealmConfig
from agens_novel.game.constants import REALM_ORDER, REALM_CONFIGS, SPIRIT_ROOTS


class TestRealmConfig:
    """Test RealmConfig dataclass."""

    def test_from_dict(self):
        data = REALM_CONFIGS["练气"]
        cfg = RealmConfig.from_dict(data)
        assert cfg.name == "练气"
        assert cfg.stages == 9
        assert cfg.experience_required == 100
        assert cfg.breakthrough_base_rate == 0.80
        assert cfg.hp_base == 100
        assert cfg.mp_base == 50

    def test_from_dict_defaults(self):
        cfg = RealmConfig.from_dict({})
        assert cfg.name == ""
        assert cfg.stages == 1
        assert cfg.experience_required == 100
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
        "experience": 300,
        "experience_to_next": 100,
        "game_over": False,
        "hp": 100,
        "hp_max": 100,
        "mp": 50,
        "mp_max": 50,
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
        session = _make_session(realm="练气", realm_stage=9, experience=300, experience_to_next=100)
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

    def test_not_eligible_insufficient_experience(self):
        rs = RealmSystem()
        session = _make_session(realm="练气", realm_stage=9, experience=50, experience_to_next=100)
        can, reason = rs.can_attempt_breakthrough(session)
        assert can is False
        assert "经验不足" in reason

    def test_not_eligible_max_realm(self):
        rs = RealmSystem()
        session = _make_session(realm="飞升", realm_stage=1, experience=999999)
        can, reason = rs.can_attempt_breakthrough(session)
        assert can is False
        assert "最高" in reason

    def test_eligible_reserved_realm_huati(self):
        """v0.4: 合体 (and all 9 realms) are now eligible for breakthrough."""
        rs = RealmSystem()
        session = _make_session(realm="合体", realm_stage=4, experience=10000, experience_to_next=5000)
        can, reason = rs.can_attempt_breakthrough(session)
        assert can is True

    def test_eligible_zhuji_to_jindan(self):
        rs = RealmSystem()
        session = _make_session(realm="筑基", realm_stage=4, experience=600, experience_to_next=300)
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


class TestAttemptBreakthrough:
    """Test breakthrough execution."""

    def test_ineligible_returns_ineligible(self):
        rs = RealmSystem()
        session = _make_session(realm="练气", realm_stage=5)  # not final stage
        result = rs.attempt_breakthrough(session)
        assert result["meta"]["breakthrough_result"] == "ineligible"

    def test_success_returns_correct_delta(self):
        rs = RealmSystem()
        session = _make_session(realm="练气", realm_stage=9, experience=300, experience_to_next=100)
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
        assert result["character"]["hp_max"] == 200
        assert result["character"]["mp_max"] == 100

    def test_failure_returns_correct_delta(self):
        rs = RealmSystem()
        session = _make_session(realm="练气", realm_stage=9, hp=100, experience=300, experience_to_next=100)
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
        # HP loss should be ~15% of current
        hp_loss_str = result["character"]["hp"]
        assert hp_loss_str.startswith("-")
        assert result["character"]["experience"] == "-20"


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
