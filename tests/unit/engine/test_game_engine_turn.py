"""Tests for GameEngine turn execution and gameplay mechanics — UI-agnostic game logic service."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from agens_novel.engine.game_engine import GameEngine, fallback_choices
from agens_novel.session.game_session import GameSession


# ═══════════════════════════════════════════════════════════════════════════════
# Canned helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _canned_world_builder() -> dict[str, Any]:
    return {
        "generated_data": {
            "character": {
                "name": "许满", "realm": "练气", "realm_stage": 1,
                "hp": 100, "hp_max": 100, "mp": 50, "mp_max": 50,
                "spirit_root": "火木双灵根", "spirit_root_grade": "地",
                "experience": 0, "experience_to_next": 100, "gold": 10,
                "breakthrough_flags": [],
                "techniques": [{"name": "基础吐纳术", "level": 1, "type": "内功"}],
                "inventory": [{"name": "粗布道袍", "quantity": 1, "type": "防具"}],
                "status_effects": [], "lifespan": 100,
            },
            "world": {
                "current_scene": "晨雾中的青云山外门",
                "location": "青云山外门", "region": "东荒",
                "npcs_present": [], "active_quests": [],
                "discovered_locations": ["青云山外门"],
                "lore_facts": [], "day_count": 1,
            },
            "opening_narrative": "天道初开。",
            "choices": ["留在山门吐纳", "询问接引弟子", "观察灵气流向"],
        },
        "world_description": "", "opening_narrative": "",
        "output_path": "", "audit_path": "", "finished_at": "", "llm_error": "",
    }


def _canned_narrator() -> dict[str, Any]:
    return {
        "narrative": "你静坐吐纳，灵气缓缓涌入。",
        "state_delta": {"character": {"mp": "-10", "experience": "+15"}},
        "choices": [],
        "output_path": "", "audit_path": "", "finished_at": "", "llm_error": "",
    }


def _canned_judge() -> dict[str, Any]:
    return {
        "approved": True, "corrected_delta": {},
        "judgment_note": "ok", "review_score": 8,
        "output_path": "", "audit_path": "", "finished_at": "", "llm_error": "",
    }


def _patch_turn_runner(call_log: list | None = None) -> Any:
    if call_log is None:
        call_log = []

    def fake_run_turn_sync(agent_name: str, user_input: str, session: GameSession, **kwargs) -> dict:
        call_log.append(agent_name)
        if agent_name == "narrator":
            return _canned_narrator()
        if agent_name == "judge":
            return _canned_judge()
        if agent_name == "world_builder":
            return _canned_world_builder()
        return {}

    return patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_run_turn_sync)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestGameEngineHandleAction:
    def test_action_runs_narrator_and_judge(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        call_log: list[str] = []
        engine = GameEngine()

        # Set up a started game.
        with _patch_turn_runner():
            engine.new_game("许满")

        with _patch_turn_runner(call_log):
            engine.handle_action("修炼吐纳")

        assert call_log == ["narrator", "judge"]
        assert engine.game_session.turn_count == 1
        assert engine.game_session.mp == 40  # 50 - 10

    def test_choice_letter_routes_to_current_choice(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        seen_inputs: list[str] = []
        engine = GameEngine()
        engine.start_from_profile({
            "char_name": "许满",
            "choices": ["留在山门吐纳", "询问接引弟子", "观察灵气流向"],
        })

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                seen_inputs.append(user_input)
                return {
                    "narrative": "你向接引弟子行礼。",
                    "state_delta": {"character": {"mp": "-5"}},
                    "choices": ["继续询问", "返回山门", "观察弟子神色"],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("B")

        assert seen_inputs == ["询问接引弟子"]
        assert engine.game_session.last_choices == ["继续询问", "返回山门", "观察弟子神色"]

    def test_choice_letter_ignores_missing_slot(self, monkeypatch) -> None:
        engine = GameEngine()

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "world_builder":
                return {"generated_data": {}, "llm_error": "timeout"}
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.start_from_profile({
                "char_name": "许满",
                "opening_narrative": "山门初开。",
                "choices": ["只给一条"],
            })

        assert engine._resolve_choice_input("C") is None

    def test_d_prefix_is_free_typed_action(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        seen_inputs: list[str] = []
        engine = GameEngine()
        engine.start_from_profile({
            "char_name": "许满",
            "choices": ["留在山门吐纳", "询问接引弟子", "观察灵气流向"],
        })

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                seen_inputs.append(user_input)
                return _canned_narrator()
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("D: 沿石阶寻找隐藏碑文")

        assert seen_inputs == ["沿石阶寻找隐藏碑文"]

    def test_action_without_game(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.handle_action("修炼")
        assert "尚未开始" in infos[0]

    def test_action_game_over(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.game_over = True
        engine.game_session.error = "魂飞魄散"
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.handle_action("修炼")
        assert "游戏已结束" in infos[0]

    def test_narrator_exception_restores_turn(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)

        def fake_runner(agent_name, user_input, session, **kw):
            raise RuntimeError("LLM exploded")

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            engine.handle_action("修炼")

        assert engine.game_session.turn_count == 0
        assert len(engine.game_session.last_choices) == 3
        assert any("天道紊乱" in msg for msg in infos)

    def test_narrator_exception_can_end_run_from_ui_choice(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        choices: list[tuple[str, str]] = []
        game_overs: list[str] = []
        engine.on_model_failure_choice = lambda source, reason: choices.append((source, reason)) or "end"
        engine.on_game_over = lambda reason: game_overs.append(reason)

        def fake_runner(agent_name, user_input, session, **kw):
            raise RuntimeError("LLM exploded")

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            engine.handle_action("修炼")

        assert choices and choices[0][0] == "narrator_exception"
        assert engine.game_session.turn_count == 0
        assert engine.game_session.game_over is True
        assert game_overs == ["模型不可用导致本局结束。"]

    def test_empty_model_choices_can_continue_with_local_fallback(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.on_model_failure_choice = lambda source, reason: "fallback"

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {"narrative": "山风拂过。", "state_delta": {}, "choices": [], "llm_error": ""}
            return {"approved": True, "corrected_delta": {}, "llm_error": ""}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("修炼")

        assert engine.game_session.game_over is False
        assert engine.game_session.turn_count == 1
        assert len(engine.game_session.last_choices) == 3

    def test_judge_exception_fallback(self, monkeypatch) -> None:
        """Judge crashes — default to NOT approving (safe default)."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        with _patch_turn_runner():
            engine.new_game("许满")

        call_log: list[str] = []

        def selective_runner(agent_name, user_input, session, **kw):
            call_log.append(agent_name)
            if agent_name == "narrator":
                return _canned_narrator()
            if agent_name == "judge":
                raise ConnectionError("Judge down")
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=selective_runner):
            engine.handle_action("修炼")

        assert engine.game_session.turn_count == 1
        # Judge exception → approved=False by default → delta NOT applied
        assert engine.game_session.mp == 50  # unchanged

    def test_judge_rejects(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        with _patch_turn_runner():
            engine.new_game("许满")

        def selective_runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return _canned_narrator()
            if agent_name == "judge":
                return {
                    "approved": False,
                    "corrected_delta": {"character": {"mp": "-5"}},
                    "judgment_note": "MP消耗过大",
                    "review_score": 3,
                    "output_path": "", "audit_path": "", "finished_at": "", "llm_error": "",
                }
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=selective_runner):
            engine.handle_action("修炼")

        assert engine.game_session.mp == 45  # 50 - 5 (corrected)

    def test_judge_reject_without_correction_suppresses_drift_narrative(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        with _patch_turn_runner():
            engine.new_game("许满")

        narratives: list[tuple[str, int]] = []
        infos: list[str] = []
        engine.on_narrative = lambda text, turn: narratives.append((text, turn))
        engine.on_info = lambda msg: infos.append(msg)

        def selective_runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "虚空之中，混沌未开。",
                    "state_delta": {"world": {"current_scene": "混沌虚空"}},
                    "choices": [],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return {
                    "approved": False,
                    "corrected_delta": {},
                    "judgment_note": "叙事重开局",
                    "review_score": 0,
                    "llm_error": "",
                }
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=selective_runner):
            engine.handle_action("修炼")

        assert narratives == []
        assert any("审判未通过" in msg for msg in infos)
        assert engine.game_session.current_scene == "晨雾中的青云山外门"

    def test_judge_reject_without_correction_keeps_model_choices(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        with _patch_turn_runner():
            engine.new_game("许满")

        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)

        def selective_runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "你试图强闯内门。",
                    "state_delta": {"character": {"mp": "-20"}},
                    "choices": ["向执事解释来意", "退回山门等候", "寻找外门任务"],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return {
                    "approved": False,
                    "corrected_delta": {},
                    "judgment_note": "越权强闯不成立",
                    "review_score": 0,
                    "llm_error": "",
                }
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=selective_runner):
            engine.handle_action("强闯内门")

        assert engine.game_session.last_choices == ["向执事解释来意", "退回山门等候", "寻找外门任务"]
        assert any("审判未通过" in msg for msg in infos)
        assert not any("天道紊乱" in msg for msg in infos)

    def test_action_delta_filters_identity_and_reset_scene(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        with _patch_turn_runner():
            engine.new_game("许满")

        def selective_runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "你仍在山门前吐纳。",
                    "state_delta": {
                        "character": {
                            "realm": "凡人",
                            "realm_stage": 1,
                            "spirit_root": "undetermined",
                            "inventory": [],
                            "techniques": [],
                            "mp": "-5",
                            "experience": "+10",
                        },
                        "world": {"current_scene": "混沌虚空", "day_count": 2},
                    },
                    "choices": [],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=selective_runner):
            engine.handle_action("修炼")

        s = engine.game_session
        assert s.realm == "练气"
        assert s.realm_stage == 1
        assert s.spirit_root == "火木双灵根"
        assert s.inventory == [{"name": "粗布道袍", "quantity": 1, "type": "防具"}]
        assert s.techniques == [{"name": "基础吐纳术", "level": 1, "type": "内功"}]
        assert s.current_scene == "晨雾中的青云山外门"
        assert s.day_count == 2
        assert s.mp == 45
        assert s.experience == 10

    def test_start_from_profile_seeds_opening_chat_history(self, monkeypatch, tmp_path) -> None:
        from agens_novel import paths

        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
        engine = GameEngine()
        engine.start_from_profile({
            "char_name": "许满",
            "talent": "剑心微明",
            "spirit_root": "火灵根",
            "family_background": "寒门",
        })

        assert engine.game_session.chat_history
        assert "当前状态 JSON 为准" in engine.game_session.chat_history[0]["content"]

    def test_typed_combat_action_uses_combat_engine_without_llm(self, monkeypatch, tmp_path) -> None:
        from agens_novel import paths

        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        import agens_novel.game.combat as combat_mod

        monkeypatch.setattr(combat_mod.random, "uniform", lambda _a, _b: 1.0)

        engine = GameEngine()
        engine.start_from_profile({
            "char_name": "许满",
            "techniques": [{"name": "基础吐纳术", "level": 1, "type": "内功", "mp_cost": 10}],
        })
        engine.game_session.combat = engine.combat_engine.start_combat(
            engine.game_session,
            {"name": "妖兽", "hp": 80, "hp_max": 80, "realm": "练气"},
        )

        with patch("agens_novel.engine.game_engine.run_turn_sync") as runner:
            engine.handle_action("施展基础吐纳术攻击妖兽")

        runner.assert_not_called()
        assert engine.game_session.combat is not None
        assert engine.game_session.combat["enemy"]["hp"] < 80
        assert engine.game_session.combat["player"]["mp"] < engine.game_session.mp_max

    def test_narrator_combat_delta_initializes_structured_combat(self, monkeypatch, tmp_path) -> None:
        from agens_novel import paths

        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        engine = GameEngine()
        engine.start_from_profile({"char_name": "许满"})
        combat_updates: list[dict | None] = []
        engine.on_combat_update = lambda state: combat_updates.append(state)

        def selective_runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "山雾里冲出一头妖兽。",
                    "state_delta": {
                        "character": {
                            "combat": {
                                "enemy": {
                                    "name": "山魈",
                                    "hp": 60,
                                    "hp_max": 60,
                                    "realm": "练气",
                                }
                            }
                        }
                    },
                    "choices": [],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=selective_runner):
            engine.handle_action("查看山门外的异响")

        assert engine.game_session.combat is not None
        assert engine.game_session.combat["phase"] == "player_turn"
        assert engine.game_session.combat["enemy"]["name"] == "山魈"
        assert combat_updates and combat_updates[-1]["phase"] == "player_turn"


class TestStageAdvancement:
    """Tests for auto-advancing small layers within a realm."""

    def test_advance_stage_on_xp_threshold(self, monkeypatch) -> None:
        """When XP reaches experience_to_next, stage auto-advances."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        with _patch_turn_runner():
            engine.new_game("许满")

        # Give just enough XP to advance from stage 1 to stage 2.
        engine.game_session.experience = 100
        engine.game_session.experience_to_next = 100
        delta = engine.realm_system.try_advance_stage(engine.game_session)
        assert delta is not None
        assert delta["character"]["realm_stage"] == 2
        engine.game_session.apply_delta(delta)
        assert engine.game_session.realm_stage == 2
        assert engine.game_session.experience == 0  # XP consumed

    def test_no_advance_at_max_stage(self, monkeypatch) -> None:
        """At max stage, try_advance_stage returns None (needs breakthrough)."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        with _patch_turn_runner():
            engine.new_game("许满")

        # Set to max stage of 练气 (9) with enough XP.
        engine.game_session.realm_stage = 9
        engine.game_session.experience = 200
        engine.game_session.experience_to_next = 100
        delta = engine.realm_system.try_advance_stage(engine.game_session)
        assert delta is None

    def test_chain_multiple_stages_in_action(self, monkeypatch) -> None:
        """Pure cultivation caps large XP so one action does not skip the journey."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)

        # Create a narrator that grants huge XP.
        def huge_xp_narrator(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "修炼大进！",
                    "state_delta": {
                        "character": {"mp": "-5", "experience": "+500"},
                    },
                    "choices": [],
                    "output_path": "", "audit_path": "", "finished_at": "", "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            if agent_name == "world_builder":
                return _canned_world_builder()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=huge_xp_narrator):
            engine.new_game("许满")
            engine.handle_action("闭关修炼")

        assert engine.game_session.realm_stage == 2
        stage_msgs = [m for m in infos if "修为精进" in m]
        assert len(stage_msgs) == 1


class TestBreakthroughRouting:
    """Tests for natural-language breakthrough detection and routing."""

    def test_parse_breakthrough_action(self) -> None:
        """_parse_breakthrough_action detects breakthrough keywords."""
        engine = GameEngine()
        engine.game_session.game_started = True

        assert engine._parse_breakthrough_action("突破") is True
        assert engine._parse_breakthrough_action("尝试突破") is True
        assert engine._parse_breakthrough_action("冲击筑基") is True
        assert engine._parse_breakthrough_action("准备渡劫飞升") is True
        assert engine._parse_breakthrough_action("闭关修炼") is False
        assert engine._parse_breakthrough_action("探索秘境") is False

    def test_breakthrough_not_during_combat(self) -> None:
        """Breakthrough keyword during combat should not route to breakthrough."""
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.combat = {"phase": "player_turn", "enemy": {"name": "山魈"}}
        assert engine._parse_breakthrough_action("突破") is False

    def test_handle_action_routes_breakthrough(self, monkeypatch) -> None:
        """Typing "尝试突破" routes to attempt_breakthrough, not narrator."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)

        with _patch_turn_runner():
            engine.new_game("许满")

        # Character is at stage 1, not max — breakthrough should be ineligible.
        engine.handle_action("尝试突破")
        assert any("需达到" in m for m in infos) or any("未满" in m for m in infos)


class TestInsightGate:
    """Tests for the 感悟 breakthrough gate and cultivation classification."""

    def test_is_pure_cultivation_detection(self) -> None:
        """Meditation phrases are pure cultivation; other deeds are not."""
        engine = GameEngine()
        assert engine._is_pure_cultivation("闭关修炼") is True
        assert engine._is_pure_cultivation("打坐修行") is True
        assert engine._is_pure_cultivation("静坐吐纳") is True
        assert engine._is_pure_cultivation("盘膝运功") is True
        assert engine._is_pure_cultivation("吸纳天地灵气") is True
        # Practising a martial art / exploring / contemplating are NOT pure.
        assert engine._is_pure_cultivation("修炼剑法") is False
        assert engine._is_pure_cultivation("外出历练") is False
        assert engine._is_pure_cultivation("参悟功法") is False
        assert engine._is_pure_cultivation("打坐参悟") is False
        assert engine._is_pure_cultivation("") is False

    def test_pure_cultivation_grants_no_insight(self, monkeypatch) -> None:
        """闭关修炼 drops even LLM-granted insight — meditation yields no 感悟."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        def narrator_with_insight(agent_name, user_input, session, **kwargs):
            if agent_name == "world_builder":
                return _canned_world_builder()
            if agent_name == "narrator":
                return {
                    "narrative": "你闭关吐纳。",
                    "state_delta": {"character": {"experience": "+20", "insight": "+50"}},
                    "choices": [],
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=narrator_with_insight):
            engine.new_game("许满")
            engine.handle_action("闭关修炼")

        assert engine.game_session.insight == 0, \
            "Pure cultivation must grant no insight even if the LLM offered some"

    def test_non_cultivation_grants_insight(self, monkeypatch) -> None:
        """A non-cultivation deed grants baseline 感悟 on top of any LLM amount."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        engine.game_session.game_started = True
        engine.game_session.char_name = "许满"
        engine.game_session.realm = "练气"
        engine.game_session.experience_to_next = 999999  # avoid stage auto-advance noise

        def narrator_plain(agent_name, user_input, session, **kwargs):
            if agent_name == "narrator":
                return _canned_narrator()  # no insight in delta
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=narrator_plain):
            engine.handle_action("外出历练")

        from agens_novel.engine.game_engine import INSIGHT_BASE_GAIN
        assert engine.game_session.insight == INSIGHT_BASE_GAIN, \
            "Non-cultivation action must grant the baseline insight"

    def test_breakthrough_blocked_without_insight(self, monkeypatch) -> None:
        """Max layer + full XP but zero 感悟 → breakthrough blocked with a 感悟 hint."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)

        engine.game_session.game_started = True
        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 9  # max layer
        engine.game_session.experience = 500
        engine.game_session.experience_to_next = 100
        engine.game_session.insight = 0  # 练气 requires 30

        engine.attempt_breakthrough()

        assert engine.game_session.realm == "练气", "Breakthrough must be blocked"
        assert any("感悟" in m for m in infos), \
            f"Blocked message must mention 感悟, got: {infos}"

    def test_breakthrough_allowed_with_insight(self, monkeypatch) -> None:
        """Max layer + full XP + sufficient 感悟 → breakthrough succeeds."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        with _patch_turn_runner():
            engine.new_game("许满")

        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 9
        engine.game_session.experience = 500
        engine.game_session.experience_to_next = 100
        engine.game_session.insight = 999  # well past the 30 gate
        engine.game_session.breakthrough_flags = ["foundation_aid"]

        with _patch_turn_runner():
            with patch("agens_novel.game.realm.random.random", return_value=0.001):
                engine.attempt_breakthrough()

        assert engine.game_session.realm == "筑基", \
            f"Breakthrough should reach 筑基, got {engine.game_session.realm}"
        assert engine.game_session.last_choices == fallback_choices(engine.game_session)

    def test_breakthrough_updates_model_choices(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        with _patch_turn_runner():
            engine.new_game("许满")

        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 9
        engine.game_session.experience = 500
        engine.game_session.experience_to_next = 100
        engine.game_session.insight = 999
        engine.game_session.breakthrough_flags = ["foundation_aid"]

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "你破开瓶颈。",
                    "state_delta": {},
                    "choices": ["稳固筑基道台", "拜谢护法长老", "查看新功法"],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            with patch("agens_novel.game.realm.random.random", return_value=0.001):
                engine.attempt_breakthrough()

        assert engine.game_session.realm == "筑基"
        assert engine.game_session.last_choices == ["稳固筑基道台", "拜谢护法长老", "查看新功法"]

    def test_breakthrough_narrator_error_uses_fallback_choices(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)

        with _patch_turn_runner():
            engine.new_game("许满")

        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 9
        engine.game_session.experience = 500
        engine.game_session.experience_to_next = 100
        engine.game_session.insight = 999
        engine.game_session.breakthrough_flags = ["foundation_aid"]

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {"narrative": "", "state_delta": {}, "choices": [], "llm_error": "timeout"}
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.attempt_breakthrough()

        assert engine.game_session.realm == "练气"
        assert len(engine.game_session.last_choices) == 3
        assert any("天道紊乱" in msg for msg in infos)

    def test_insight_resets_on_breakthrough(self, monkeypatch) -> None:
        """A successful breakthrough zeroes 感悟 (new realm, new bottleneck)."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        with _patch_turn_runner():
            engine.new_game("许满")

        engine.game_session.realm = "练气"
        engine.game_session.realm_stage = 9
        engine.game_session.experience = 500
        engine.game_session.experience_to_next = 100
        engine.game_session.insight = 999
        engine.game_session.breakthrough_flags = ["foundation_aid"]

        with _patch_turn_runner():
            with patch("agens_novel.game.realm.random.random", return_value=0.001):
                engine.attempt_breakthrough()

        assert engine.game_session.realm == "筑基"
        assert engine.game_session.insight == 0, \
            "Insight must reset to 0 after a successful breakthrough"

    def test_insight_serialization_roundtrip(self) -> None:
        """save/load preserves the 感悟 value."""
        session = GameSession()
        session.insight = 137
        data = session.to_save_dict()
        assert data["character"]["insight"] == 137

        restored = GameSession.from_save_dict(data)
        assert restored.insight == 137

    def test_insight_floor_guard(self) -> None:
        """Insight is floored at 0 — cannot go negative."""
        session = GameSession()
        session.insight = 5
        session.apply_delta({"character": {"insight": "-50"}})
        assert session.insight == 0
