"""Tests for GameEngine — UI-agnostic game logic service."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from agens_novel.engine.game_engine import GameEngine
from agens_novel.repl.game_session import GameSession


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
        assert len(narratives) == 1

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

        def fake_runner(agent_name, user_input, session, **kw):
            raise RuntimeError("LLM exploded")

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            engine.handle_action("修炼")

        assert engine.game_session.turn_count == 0

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


class TestGameEngineSaveLoad:
    def test_save_and_load(self, monkeypatch, tmp_path) -> None:
        from agens_novel import paths
        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path / "saves")
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        engine = GameEngine()
        with _patch_turn_runner():
            engine.new_game("许满")

        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)

        engine.save("test")
        assert "已保存" in infos[-1]

        # Load into new engine.
        engine2 = GameEngine()
        engine2.on_info = lambda msg: infos.append(msg)
        engine2.load("test")
        assert engine2.game_session.char_name == "许满"
        assert "已加载" in infos[-1]

    def test_save_without_game(self, monkeypatch) -> None:
        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.save("test")
        assert "没有进行中" in infos[0]

    def test_load_nonexistent(self, monkeypatch, tmp_path) -> None:
        from agens_novel import paths
        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path / "saves")

        engine = GameEngine()
        infos: list[str] = []
        engine.on_info = lambda msg: infos.append(msg)
        engine.load("nonexistent")
        assert "不存在" in infos[0] or "找不到" in infos[0]


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
        assert engine.game_session.turn_count == 0
