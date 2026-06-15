"""Tests for GameEngine state management, persistence, and game lifecycle — UI-agnostic game logic service."""

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
        if agent_name == "judge":
            return _canned_judge()
        if agent_name == "world_builder":
            return _canned_world_builder()
        return {}

    return patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_run_turn_sync)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════

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


class TestFinaleCallback:
    """Tests for ascension finale handling."""

    def test_finale_callback_on_ascension(self, monkeypatch) -> None:
        """Breaking through to 飞升 fires on_finale."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        finales: list[str] = []
        game_overs: list[str] = []
        engine.on_finale = lambda reason: finales.append(reason)
        engine.on_game_over = lambda reason: game_overs.append(reason)

        with _patch_turn_runner():
            engine.new_game("许满")

        # Set to max stage of 渡劫 with enough XP and 感悟 (insight) to pass the gate.
        engine.game_session.realm = "渡劫"
        engine.game_session.realm_stage = 4
        engine.game_session.experience = 20001
        engine.game_session.experience_to_next = 20000
        engine.game_session.insight = 999  # 渡劫 requires 400 感悟 to break through
        engine.game_session.breakthrough_flags = ["tribulation_elixir", "ascension_protection"]

        # Mock random and LLM to guarantee deterministic unit behavior.
        with _patch_turn_runner():
            with patch("agens_novel.game.realm.random.random", return_value=0.001):
                engine.attempt_breakthrough()

        assert len(finales) == 1
        assert game_overs == []
        assert "飞升" in finales[0]
        assert engine.game_session.finale is True
        assert engine.game_session.game_over is True
        assert engine.game_session.realm == "飞升"

    def test_death_screen_no_finale_for_normal_death(self, monkeypatch) -> None:
        """Regular death (HP=0) does not set finale flag."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        game_overs: list[str] = []
        engine.on_game_over = lambda reason: game_overs.append(reason)

        engine.game_session.game_started = True
        engine.game_session.hp = 0
        engine.game_session.char_name = "许满"
        engine._check_game_over()

        assert engine.game_session.finale is False
        assert engine.game_session.game_over is True
        assert len(game_overs) == 1
        assert engine.game_session.turn_count == 0
