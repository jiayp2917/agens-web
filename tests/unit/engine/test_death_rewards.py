"""Tests for P4 death rewards evaluation (UI-agnostic engine logic)."""

from __future__ import annotations

from typing import Any

from agens_novel.engine.death_rewards import (
    DEATH_BY_EVENT,
    DEATH_BY_FINALE,
    DEATH_BY_KARMA,
    DEATH_BY_LIFESPAN,
    DEATH_BY_PLAYER,
    apply_legacy_bonuses,
    bonuses_to_legacy,
    build_run_summary,
    categorize_death,
    compute_rewards,
    evaluate_achievements,
)
from agens_novel.session.game_session import GameSession


def _make_session(**overrides: Any) -> GameSession:
    session = GameSession()
    for key, value in overrides.items():
        setattr(session, key, value)
    return session


class TestCategorizeDeath:
    def test_finale_takes_precedence(self) -> None:
        session = _make_session(game_over=True, finale=True)
        assert categorize_death(session) == DEATH_BY_FINALE

    def test_event_death_from_trial(self) -> None:
        session = _make_session(game_over=True, lifespan=100, error="斗法失败，道消身殒。")
        assert categorize_death(session) == DEATH_BY_EVENT

    def test_karma_death_from_luck(self) -> None:
        session = _make_session(game_over=True, lifespan=100, error="气运反噬，因果缠身。")
        assert categorize_death(session) == DEATH_BY_KARMA

    def test_lifespan_death(self) -> None:
        session = _make_session(game_over=True, lifespan=0)
        assert categorize_death(session) == DEATH_BY_LIFESPAN

    def test_player_quit(self) -> None:
        session = _make_session(game_over=True, lifespan=100, error="玩家结束本局。")
        assert categorize_death(session) == DEATH_BY_PLAYER

    def test_not_game_over_returns_empty(self) -> None:
        session = _make_session(game_over=False)
        assert categorize_death(session) == ""


class TestEvaluateAchievements:
    def test_foundation_milestone(self) -> None:
        session = _make_session(realm="筑基", realm_stage=1, turn_count=10)
        achievements = evaluate_achievements(session)
        keys = [a["key"] for a in achievements]
        assert "foundation_established" in keys

    def test_golden_core_milestone(self) -> None:
        session = _make_session(realm="金丹", realm_stage=1, turn_count=10)
        achievements = evaluate_achievements(session)
        keys = [a["key"] for a in achievements]
        assert "golden_core_forged" in keys
        assert "foundation_established" in keys  # realm-order cumulative

    def test_qi_persistence(self) -> None:
        session = _make_session(realm="练气", realm_stage=7, turn_count=10)
        keys = [a["key"] for a in evaluate_achievements(session)]
        assert "qi_refinement_persistent" in keys

    def test_long_lived_mortal(self) -> None:
        session = _make_session(realm="练气", realm_stage=3, age=80, lifespan=100, turn_count=10)
        keys = [a["key"] for a in evaluate_achievements(session)]
        assert "long_lived_mortal" in keys

    def test_long_lived_mortal_uses_age_not_lifespan_cap(self) -> None:
        session = _make_session(realm="练气", realm_stage=3, age=16, lifespan=100, turn_count=2)
        keys = [a["key"] for a in evaluate_achievements(session)]
        assert "long_lived_mortal" not in keys

    def test_veteran_wanderer(self) -> None:
        session = _make_session(realm="练气", realm_stage=3, turn_count=30, lifespan=100)
        keys = [a["key"] for a in evaluate_achievements(session)]
        assert "veteran_wanderer" in keys

    def test_well_stocked(self) -> None:
        items = [{"name": f"item{i}"} for i in range(5)]
        session = _make_session(realm="练气", realm_stage=1, inventory=items)
        keys = [a["key"] for a in evaluate_achievements(session)]
        assert "well_stocked" in keys

    def test_polymath_cultivator(self) -> None:
        techs = [{"name": f"t{i}"} for i in range(3)]
        session = _make_session(realm="练气", realm_stage=1, techniques=techs)
        keys = [a["key"] for a in evaluate_achievements(session)]
        assert "polymath_cultivator" in keys

    def test_explorer(self) -> None:
        places = [f"loc{i}" for i in range(5)]
        session = _make_session(realm="练气", realm_stage=1, discovered_locations=places)
        keys = [a["key"] for a in evaluate_achievements(session)]
        assert "explorer" in keys

    def test_ascension(self) -> None:
        session = _make_session(realm="飞升", realm_stage=1, finale=True)
        keys = [a["key"] for a in evaluate_achievements(session)]
        assert "ascended" in keys

    def test_no_achievements_for_quick_death(self) -> None:
        session = _make_session(realm="练气", realm_stage=1, turn_count=1, lifespan=10)
        keys = [a["key"] for a in evaluate_achievements(session)]
        assert keys == []


class TestComputeRewards:
    def test_base_attribute_points_always_granted(self) -> None:
        session = _make_session(realm="练气", realm_stage=1)
        rewards = compute_rewards([], session)
        types = [r["type"] for r in rewards]
        assert "attribute_points" in types

    def test_finale_grants_title_and_lifespan(self) -> None:
        session = _make_session(realm="飞升", realm_stage=1, finale=True)
        rewards = compute_rewards(
            [{"key": "ascended", "name": "飞升证道", "description": ""}],
            session,
        )
        types = {r["type"] for r in rewards}
        assert "opening_title" in types
        assert "extra_lifespan" in types

    def test_golden_core_grants_extra_lifespan(self) -> None:
        session = _make_session(realm="金丹", realm_stage=1)
        rewards = compute_rewards(
            [{"key": "golden_core_forged", "name": "金丹凝成", "description": ""}],
            session,
        )
        types = {r["type"] for r in rewards}
        assert "extra_lifespan" in types

    def test_explorer_unlocks_legacy_talent(self) -> None:
        session = _make_session(realm="练气", realm_stage=1)
        rewards = compute_rewards(
            [{"key": "explorer", "name": "足迹遍布", "description": ""}],
            session,
        )
        types = {r["type"] for r in rewards}
        assert "legacy_talent" in types


class TestLegacyBonusApplication:
    def test_attribute_points_distributed_to_lowest(self) -> None:
        profile = {"attributes": {"root_bone": 5, "luck": 3, "willpower": 7}}
        bonuses = [{"bonus_type": "attribute_points", "bonus_value": 3, "label": "+3"}]
        updated = apply_legacy_bonuses(profile, bonuses)
        assert updated["attributes"] == {"root_bone": 6, "luck": 5, "willpower": 7}

    def test_extra_lifespan_added(self) -> None:
        profile = {"attributes": {}}
        bonuses = [{"bonus_type": "extra_lifespan", "bonus_value": 15, "label": "+15"}]
        updated = apply_legacy_bonuses(profile, bonuses)
        assert updated["extra_lifespan"] == 15

    def test_extra_lifespan_accumulates(self) -> None:
        profile = {"attributes": {}, "extra_lifespan": 10}
        bonuses = [{"bonus_type": "extra_lifespan", "bonus_value": 5, "label": "+5"}]
        updated = apply_legacy_bonuses(profile, bonuses)
        assert updated["extra_lifespan"] == 15

    def test_legacy_talent_appended(self) -> None:
        profile = {"attributes": {}}
        bonuses = [{"bonus_type": "legacy_talent", "bonus_value": "游历之眼", "label": "legacy"}]
        updated = apply_legacy_bonuses(profile, bonuses)
        assert "游历之眼" in updated["legacy_talents"]

    def test_opening_title_appended(self) -> None:
        profile = {"attributes": {}}
        bonuses = [{"bonus_type": "opening_title", "bonus_value": "飞升者", "label": "title"}]
        updated = apply_legacy_bonuses(profile, bonuses)
        assert "飞升者" in updated["opening_titles"]

    def test_empty_bonuses_returns_copy(self) -> None:
        profile = {"attributes": {"root_bone": 5}}
        updated = apply_legacy_bonuses(profile, [])
        assert updated == profile
        assert updated is not profile

    def test_attribute_points_cap_at_10(self) -> None:
        profile = {"attributes": {"root_bone": 10, "luck": 9}}
        bonuses = [{"bonus_type": "attribute_points", "bonus_value": 50, "label": "+50"}]
        updated = apply_legacy_bonuses(profile, bonuses)
        # Only 1 point fits (9 -> 10), rest is silently dropped.
        assert updated["attributes"]["luck"] == 10
        assert updated["attributes"]["root_bone"] == 10

    def test_legacy_percent_profile_attributes_are_migrated_before_bonus(self) -> None:
        profile = {"attributes": {"root_bone": 50, "luck": 30, "willpower": 70}}
        bonuses = [{"bonus_type": "attribute_points", "bonus_value": 2, "label": "+2"}]
        updated = apply_legacy_bonuses(profile, bonuses)
        assert updated["attributes"] == {"root_bone": 5, "luck": 5, "willpower": 7}


class TestBonusesToLegacy:
    def test_runs_remaining_defaults_to_one(self) -> None:
        rows = bonuses_to_legacy([
            {"type": "attribute_points", "value": 3, "label": "+3"},
            {"type": "extra_lifespan", "value": 10, "label": "+10"},
        ])
        assert len(rows) == 2
        assert all(row["runs_remaining"] == 1 for row in rows)


class TestBuildRunSummary:
    def test_summary_includes_headline_and_lists(self) -> None:
        session = _make_session(
            realm="练气",
            realm_stage=3,
            turn_count=15,
            age=18,
            inventory=[{"name": "粗布道袍"}],
            techniques=[{"name": "基础吐纳术"}],
            discovered_locations=["loc1", "loc2"],
        )
        achievements = [{"key": "veteran_wanderer", "name": "历练已久", "description": "x"}]
        rewards = [{"type": "attribute_points", "value": 2, "label": "+2"}]
        summary = build_run_summary(session, achievements, rewards, DEATH_BY_PLAYER)
        assert summary["death_cause"] == DEATH_BY_PLAYER
        assert summary["final_realm"] == "练气"
        assert summary["final_stage"] == 3
        assert summary["turn_count"] == 15
        assert summary["achievements"] == achievements
        assert summary["rewards"] == rewards
        assert "主动退场" in summary["headline"]
        assert summary["inventory_count"] == 1
        assert summary["technique_count"] == 1
        assert summary["discovered_count"] == 2

    def test_finale_headline(self) -> None:
        session = _make_session(realm="飞升", realm_stage=1, finale=True, char_name="许满")
        summary = build_run_summary(session, [], [], DEATH_BY_FINALE)
        assert "飞升" in summary["headline"]
