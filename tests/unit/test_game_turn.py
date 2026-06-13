"""Game turn journey tests.

Tests the narrator + judge turn cycle by patching ``run_turn_sync``
with canned responses. Also tests save/load round-trip.
"""

from __future__ import annotations

import json
from typing import Any, Callable
from unittest.mock import patch

import pytest

from agens_novel.repl import Repl
from agens_novel.repl.game_session import GameSession


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _canned_narrator_result(
    narrative: str = "你静坐修炼，灵气缓缓汇入丹田。",
    state_delta: dict | None = None,
) -> dict[str, Any]:
    """Return a canned narrator result."""
    return {
        "narrative": narrative,
        "state_delta": state_delta or {"character": {"mp": "-10", "experience": "+15"}},
        "choices": [],
        "output_path": "/tmp/narrator_out.md",
        "audit_path": "/tmp/narrator_audit.json",
        "finished_at": "2026-01-01T00:00:00Z",
        "llm_error": "",
    }


def _canned_judge_result(approved: bool = True) -> dict[str, Any]:
    """Return a canned judge result."""
    return {
        "approved": approved,
        "corrected_delta": {},
        "judgment_note": "ok",
        "review_score": 8,
        "output_path": "/tmp/judge_out.md",
        "audit_path": "/tmp/judge_audit.json",
        "finished_at": "2026-01-01T00:00:00Z",
        "llm_error": "",
    }


def _canned_world_builder_result() -> dict[str, Any]:
    """Return a canned world_builder result for /new."""
    return {
        "generated_data": {
            "character": {
                "name": "许满",
                "realm": "练气",
                "realm_stage": 1,
                "hp": 100, "hp_max": 100,
                "mp": 50, "mp_max": 50,
                "spirit_root": "火木双灵根",
                "spirit_root_grade": "地",
                "experience": 0, "experience_to_next": 100,
                "gold": 10,
                "techniques": [{"name": "基础吐纳术", "level": 1, "type": "内功"}],
                "inventory": [{"name": "粗布道袍", "quantity": 1, "type": "防具"}],
                "status_effects": [],
                "lifespan": 100,
            },
            "world": {
                "current_scene": "晨雾中的青云山外门",
                "location": "青云山外门",
                "region": "东荒",
                "npcs_present": [{"name": "陈师兄", "relation": "同门", "realm": "练气五层"}],
                "active_quests": [{"name": "入门修行", "description": "完成基础修炼", "status": "active"}],
                "discovered_locations": ["青云山外门"],
                "lore_facts": ["青云门是东荒三宗之一"],
                "day_count": 1,
            },
            "opening_narrative": "晨曦微露，青云山外门的大殿前，一个少年盘膝而坐。\n他叫许满，三天前刚被收入外门。\n丹田中一丝灵气若隐若现，修仙之路就此开始。",
        },
        "world_description": "",
        "opening_narrative": "",
        "output_path": "/tmp/wb_out.md",
        "audit_path": "/tmp/wb_audit.json",
        "finished_at": "2026-01-01T00:00:00Z",
        "llm_error": "",
    }


def _make_repl(inputs: list[str]) -> Repl:
    """Build a Repl with a deterministic input stream."""
    it = iter(inputs)
    return Repl(input_fn=lambda _p: next(it))


def _patch_turn_runner(call_log: list | None = None) -> Any:
    """Patch run_turn_sync to return canned results based on agent name."""
    if call_log is None:
        call_log = []

    def fake_run_turn_sync(agent_name: str, user_input: str, session: GameSession, **kwargs) -> dict:
        call_log.append(agent_name)
        if agent_name == "narrator":
            return _canned_narrator_result()
        if agent_name == "judge":
            return _canned_judge_result()
        if agent_name == "world_builder":
            return _canned_world_builder_result()
        return {}

    return patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_run_turn_sync)


# ─────────────────────────────────────────────────────────────────────────────
# Journey 1: /new creates a character and starts the game
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney1NewGame:
    def test_new_game_initializes_session(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        call_log: list[str] = []

        inputs = ["/new 我叫许满", "/exit"]
        repl = _make_repl(inputs)

        with _patch_turn_runner(call_log):
            rc = repl.run()

        assert rc == 0
        assert "world_builder" in call_log
        assert repl.game_session.game_started is True
        assert repl.game_session.char_name == "许满"
        assert repl.game_session.realm == "练气"
        assert repl.game_session.hp == 100
        assert repl.game_session.location == "青云山外门"

    def test_new_game_shows_opening_narrative(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        inputs = ["/new 许满", "/exit"]
        repl = _make_repl(inputs)

        with _patch_turn_runner():
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        assert "天道初开" in out


# ─────────────────────────────────────────────────────────────────────────────
# Journey 2: Player action triggers narrator + judge
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney2PlayerAction:
    def test_action_runs_narrator_and_judge(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        call_log: list[str] = []

        inputs = ["/new 许满", "修炼吐纳", "/exit"]
        repl = _make_repl(inputs)

        with _patch_turn_runner(call_log):
            rc = repl.run()

        assert rc == 0
        # world_builder for /new, then narrator + judge for the action.
        assert call_log == ["world_builder", "narrator", "judge"]
        assert repl.game_session.turn_count == 1
        assert repl.game_session.mp == 40  # 50 - 10 from delta

    def test_action_displays_narrative(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        inputs = ["/new 许满", "修炼", "/exit"]
        repl = _make_repl(inputs)

        with _patch_turn_runner():
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        assert "第 1 回合" in out


# ─────────────────────────────────────────────────────────────────────────────
# Journey 3: Save and load
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney3SaveLoad:
    def test_save_and_load_round_trip(self, capsys, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        from agens_novel import paths
        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path / "saves")

        inputs = ["/new 许满", "/save test", "/exit"]
        repl = _make_repl(inputs)

        with _patch_turn_runner():
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        assert "已保存" in out

        # Load into a new repl.
        inputs2 = ["/load test", "/status", "/exit"]
        repl2 = _make_repl(inputs2)

        with _patch_turn_runner():
            rc2 = repl2.run()

        assert rc2 == 0
        assert repl2.game_session.char_name == "许满"
        assert repl2.game_session.game_started is True


# ─────────────────────────────────────────────────────────────────────────────
# Journey 4: Reset clears the game
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney4Reset:
    def test_reset_clears_game_session(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        inputs = ["/new 许满", "/reset", "/status", "/exit"]
        repl = _make_repl(inputs)

        with _patch_turn_runner():
            rc = repl.run()

        assert rc == 0
        assert repl.game_session.game_started is False
        assert repl.game_session.char_name == ""
        out = capsys.readouterr().out
        # /status after reset should show "尚未开始游戏"
        assert "尚未开始游戏" in out


# ─────────────────────────────────────────────────────────────────────────────
# Journey 5: Action without game started
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney5NoGame:
    def test_action_before_game_shows_hint(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        call_log: list[str] = []

        inputs = ["修炼", "/exit"]
        repl = _make_repl(inputs)

        with _patch_turn_runner(call_log):
            rc = repl.run()

        assert rc == 0
        # No agents should have been called.
        assert call_log == []
        out = capsys.readouterr().out
        assert "尚未开始游戏" in out


# ─────────────────────────────────────────────────────────────────────────────
# Journey 6: Game over
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney6GameOver:
    def test_game_over_blocks_actions(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        repl = _make_repl(["修炼", "/exit"])
        repl.game_session.game_started = True
        repl.game_session.game_over = True
        repl.game_session.error = "魂飞魄散"

        call_log: list[str] = []
        with _patch_turn_runner(call_log):
            rc = repl.run()

        assert rc == 0
        assert call_log == []
        out = capsys.readouterr().out
        assert "游戏已结束" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
