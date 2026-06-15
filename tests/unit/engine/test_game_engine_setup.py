"""Tests for GameEngine initialization and configuration — UI-agnostic game logic service."""

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

class TestGameEngineNewGame:
    def test_new_game_initializes_session(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        narratives: list[tuple[str, int]] = []
        engine.on_narrative = lambda text, turn: narratives.append((text, turn))

        with _patch_turn_runner():
            engine.new_game("我叫许满")

        assert engine.game_session.game_started is True
        assert engine.game_session.char_name == "许满"
        assert engine.game_session.realm == "练气"
        assert engine.game_session.hp == 100
        assert engine.game_session.last_choices == ["留在山门吐纳", "询问接引弟子", "观察灵气流向"]
        assert len(narratives) == 1

    def test_model_choices_not_padded_when_less_than_three(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "world_builder":
                data = _canned_world_builder()
                data["generated_data"]["choices"] = ["请教陈师兄", "查看山门规矩"]
                return data
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.new_game("许满")

        assert engine.game_session.last_choices == ["请教陈师兄", "查看山门规矩"]

    def test_empty_model_choices_use_visible_fallback_notice(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.start_from_profile({"char_name": "许满", "choices": ["观察山门"]})

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "风声一滞。",
                    "state_delta": {"character": {"experience": "+5"}},
                    "choices": [],
                    "llm_error": "timeout",
                }
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("观察")

        assert len(engine.game_session.last_choices) == 3
        assert any("天道紊乱" in msg for msg in infos)

    def test_empty_successful_choices_still_show_fallback_notice(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.start_from_profile({"char_name": "许满", "opening_narrative": "山门初开。", "choices": ["观察"]})

        def runner(agent_name, user_input, session, **kw):
            if agent_name == "narrator":
                return {
                    "narrative": "你听见钟声。",
                    "state_delta": {"character": {"experience": "+5"}},
                    "choices": [],
                    "llm_error": "",
                }
            if agent_name == "judge":
                return _canned_judge()
            return {}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=runner):
            engine.handle_action("观察")

        assert len(engine.game_session.last_choices) == 3
        assert any("天道紊乱" in msg for msg in infos)

    def test_new_game_without_api_key(self, monkeypatch) -> None:
        """Built-in key is always the fallback, so _has_api_key always True.
        Without AGNES_API_KEY env, the game still tries to run but will fail
        at the turn_runner level because build_graph doesn't exist.
        """
        monkeypatch.delenv("AGNES_API_KEY", raising=False)
        engine = GameEngine()
        errors: list[str] = []
        engine.on_error = lambda msg: errors.append(msg)
        engine.new_game("test")
        # _has_api_key() always returns True (built-in key fallback)
        # So the error comes from the world_builder agent failing, not from API key check
        assert len(errors) == 1
        assert "失败" in errors[0]  # "世界生成失败"

    def test_new_game_empty_concept(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.new_game("")
        assert "取消" in infos[0]

    def test_new_game_llm_error(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        errors: list[str] = []
        engine.on_error = lambda msg: errors.append(msg)

        def fake_runner(agent_name, user_input, session, **kw):
            return {**_canned_world_builder(), "llm_error": "API rate limit"}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            engine.new_game("test")
        assert "API rate limit" in errors[0]

    def test_new_game_empty_data(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)

        def fake_runner(agent_name, user_input, session, **kw):
            return {"generated_data": {}, "llm_error": ""}

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            engine.new_game("test")
        assert "为空" in infos[0]


class TestGameEngineQueries:
    def test_get_status(self) -> None:
        engine = GameEngine()
        engine.game_session.char_name = "许满"
        engine.game_session.realm = "金丹"
        text = engine.get_status()
        assert "许满" in text
        assert "金丹" in text

    def test_get_inventory_empty(self) -> None:
        engine = GameEngine()
        assert "背包为空" in engine.get_inventory()

    def test_get_skills_empty(self) -> None:
        engine = GameEngine()
        assert "尚未习得" in engine.get_skills()

    def test_get_map_empty(self) -> None:
        engine = GameEngine()
        assert "尚未探索" in engine.get_map()

    def test_get_quests_empty(self) -> None:
        engine = GameEngine()
        assert "没有任务" in engine.get_quests()

    def test_get_log_empty(self) -> None:
        engine = GameEngine()
        assert "暂无" in engine.get_log()


class TestGameEngineReset:
    def test_reset(self) -> None:
        engine = GameEngine()
        engine.game_session.char_name = "许满"
        engine.game_session.game_started = True
        engine.game_session.turn_count = 50
        engine.reset()
        assert engine.game_session.char_name == ""
        assert engine.game_session.game_started is False
