"""Tests for rule-driven GameEngine stage advancement."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.engine.game_engine import GameEngine
from tests.unit.engine.fixtures import canned_judge as _canned_judge
from tests.unit.engine.fixtures import canned_world_builder as _canned_world_builder
from tests.unit.engine.turn_test_support import FixedRuleRng as _FixedRuleRng
from tests.unit.engine.turn_test_support import patch_turn_runner_for_tests as _patch_turn_runner


class TestStageAdvancement:
    """Tests for auto-advancing small layers within a realm."""

    def test_advance_stage_on_rule_chance(self, monkeypatch) -> None:
        """Stage advancement is event-like and probability-driven, not XP-driven."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        with _patch_turn_runner():
            engine.new_game("许满")

        delta = engine.realm_system.try_advance_stage(
            engine.game_session,
            rule_rng=_FixedRuleRng(0.0),
        )
        assert delta is not None
        assert delta["character"]["realm_stage"] == 2
        engine.game_session.apply_delta(delta)
        assert engine.game_session.realm_stage == 2
        assert not hasattr(engine.game_session, "experience")

    def test_no_advance_at_max_stage(self, monkeypatch) -> None:
        """At max stage, try_advance_stage returns None (needs breakthrough)."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        with _patch_turn_runner():
            engine.new_game("许满")

        engine.game_session.realm_stage = 9
        delta = engine.realm_system.try_advance_stage(engine.game_session)
        assert delta is None

    def test_chain_multiple_stages_in_action(self, monkeypatch) -> None:
        """One action can emit at most one small-stage advancement."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "修炼大进！",
                    "state_delta": {"character": {"attributes": {"willpower": 1}}},
                    "choices": ["继续吐纳", "检查瓶颈", "出门历练"],
                    "output_path": "",
                    "audit_path": "",
                    "finished_at": "",
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            if agent_name == "world_builder":
                return _canned_world_builder()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.new_game("许满")
            with patch(
                "agens_novel.game.realm.rule_rng_for_session",
                return_value=_FixedRuleRng(0.0),
            ):
                engine.handle_action("闭关修炼")

        assert engine.game_session.realm_stage == 2
        stage_msgs = [m for m in infos if "修为精进" in m]
        assert len(stage_msgs) == 1

    def test_stage_advance_is_recorded_in_turn_delta(self, monkeypatch) -> None:
        """Automatic small-stage advancement must be auditable in turn_history."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        with _patch_turn_runner():
            engine.new_game("许满")
        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 3
        engine.game_session.age = 29
        engine.game_session.turn_count = 9
        engine.game_session.attributes = {"comprehension": 5, "root_bone": 5}

        with _patch_turn_runner():
            engine.handle_action("闭关修炼")

        last_delta = engine.game_session.turn_history[-1]["delta"]
        assert last_delta["character"]["realm_stage"] == engine.game_session.realm_stage
        assert last_delta["meta"]["stage_advanced"] is True
        assert last_delta["meta"]["stage_advance_reason"] == "chronicle_pace"

    def test_stage_advance_info_uses_public_realm_label_only(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda message: infos.append(message)
        engine.game_session.game_started = True
        engine.game_session.realm = "筑基"
        engine.game_session.realm_stage = 1
        stage_delta = {
            "character": {"realm_stage": 2},
            "meta": {
                "stage_advanced": True,
                "stage_advance_reason": "chronicle_pace",
                "new_stage": 2,
                "max_stage": 4,
            },
        }

        with patch.object(engine.realm_system, "try_advance_stage", return_value=stage_delta):
            with _patch_turn_runner():
                engine.handle_action("闭关温养")

        stage_messages = [message for message in infos if "修为精进" in message]
        assert stage_messages
        assert "境界:" not in stage_messages[-1]
        assert "破境准备" not in stage_messages[-1]
        assert "/" not in stage_messages[-1]
