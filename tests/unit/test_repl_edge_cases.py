"""Edge case and error path tests for the game REPL.

Covers: keyboard interrupt, EOF, whitespace, help, API key checks,
unknown commands, game action without game started, reset, save/load,
confirmation dialogs, and game session persistence.
"""

from __future__ import annotations

import json
from typing import Any, Callable
from unittest.mock import patch

import pytest

from agens_novel.repl import Repl, SlashCommand
from agens_novel.repl.commands import SLASH_COMMANDS


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _make_repl(inputs: list[str]) -> Repl:
    """Build a Repl with a deterministic input stream."""
    it = iter(inputs)
    return Repl(input_fn=lambda _p: next(it))


# ─────────────────────────────────────────────────────────────────────────────
# Clean exits
# ─────────────────────────────────────────────────────────────────────────────
class TestCleanExits:
    def test_kbi_exits_cleanly(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        def raise_kbi(_p):
            raise KeyboardInterrupt

        repl = Repl(input_fn=raise_kbi)
        rc = repl.run()
        assert rc == 0

    def test_stop_iteration_exits_cleanly(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        def raise_stop(_p):
            raise StopIteration

        repl = Repl(input_fn=raise_stop)
        rc = repl.run()
        assert rc == 0

    def test_eof_exits_cleanly(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        def raise_eof(_p):
            raise EOFError

        repl = Repl(input_fn=raise_eof)
        rc = repl.run()
        assert rc == 0


# ─────────────────────────────────────────────────────────────────────────────
# Whitespace continues silently
# ─────────────────────────────────────────────────────────────────────────────
class TestWhitespaceContinues:
    def test_blank_input_continues(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        inputs = iter(["", "   ", "/exit"])
        repl = Repl(input_fn=lambda _p: next(inputs))
        rc = repl.run()
        assert rc == 0
        assert all(h.strip() for h in repl.history)

    def test_lone_slash_continues(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        inputs = iter(["/", "/exit"])
        repl = Repl(input_fn=lambda _p: next(inputs))
        rc = repl.run()
        assert rc == 0
        assert "/" not in repl.history


# ─────────────────────────────────────────────────────────────────────────────
# /help shows all commands
# ─────────────────────────────────────────────────────────────────────────────
class TestHelp:
    def test_help_count(self) -> None:
        """SLASH_COMMANDS contains the expected number of game commands."""
        # 23 commands: original 17 + breakthrough, attack, technique, item, defend, flee
        assert len(SLASH_COMMANDS) == 23

    def test_help_lists_every_command(self, capsys) -> None:
        repl = Repl()
        repl.cmd_help("")
        out = capsys.readouterr().out
        for name in SLASH_COMMANDS:
            assert f"/{name}" in out, f"missing /{name}"

    def test_help_header(self, capsys) -> None:
        repl = Repl()
        repl.cmd_help("")
        out = capsys.readouterr().out
        assert "可用命令" in out

    def test_help_mentions_game(self, capsys) -> None:
        repl = Repl()
        repl.cmd_help("")
        out = capsys.readouterr().out
        assert "游戏" in out or "修仙" in out


# ─────────────────────────────────────────────────────────────────────────────
# API key checks
# ─────────────────────────────────────────────────────────────────────────────
class TestApiKeyChecks:
    def test_action_without_api_key(self, capsys, monkeypatch) -> None:
        """Built-in key is always the fallback, so _has_api_key always True.
        Without AGNES_API_KEY env, the game still tries to run but will fail
        at the turn_runner level because build_graph doesn't exist.
        """
        monkeypatch.delenv("AGNES_API_KEY", raising=False)
        repl = _make_repl(["修炼吐纳", "/exit"])
        repl.game_session.game_started = True
        rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        # Error comes from narrator failing, not from API key check
        assert "失败" in out or "错误" in out

    def test_new_without_api_key(self, capsys, monkeypatch) -> None:
        """Without AGNES_API_KEY env, Repl still checks for key before new game."""
        monkeypatch.delenv("AGNES_API_KEY", raising=False)
        repl = _make_repl(["/new test", "/exit"])
        rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        # Repl's cmd_new checks api_key before calling engine
        assert "AGNES_API_KEY" in out or "未设置" in out or "失败" in out


# ─────────────────────────────────────────────────────────────────────────────
# Config display
# ─────────────────────────────────────────────────────────────────────────────
class TestConfig:
    def test_config_masks_api_key(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        repl = Repl()
        repl.cmd_config("")
        out = capsys.readouterr().out
        assert "sk-test-1234567890" not in out
        assert "***" in out


# ─────────────────────────────────────────────────────────────────────────────
# Unknown command
# ─────────────────────────────────────────────────────────────────────────────
class TestUnknownCommand:
    def test_unknown_command_message(self, capsys) -> None:
        repl = Repl()
        repl._dispatch_slash(SlashCommand(name="foobar", args=""))
        out = capsys.readouterr().out
        assert "未知命令" in out
        assert "/help" in out

    def test_unknown_command_does_not_exit(self) -> None:
        repl = Repl()
        result = repl._dispatch_slash(SlashCommand(name="nope", args=""))
        assert result is False

    def test_unknown_command_in_history(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        inputs = iter(["/foobar", "/exit"])
        repl = _make_repl(inputs)
        rc = repl.run()
        assert rc == 0
        assert any("/foobar" in h for h in repl.history)


# ─────────────────────────────────────────────────────────────────────────────
# Game action without game started
# ─────────────────────────────────────────────────────────────────────────────
class TestActionWithoutGame:
    def test_action_before_new_game(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        inputs = iter(["修炼", "/exit"])
        repl = _make_repl(inputs)
        rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        assert "尚未开始游戏" in out

    def test_status_before_new_game(self, capsys) -> None:
        repl = Repl()
        repl.cmd_status("")
        out = capsys.readouterr().out
        assert "尚未开始游戏" in out

    def test_inv_before_new_game(self, capsys) -> None:
        repl = Repl()
        repl.cmd_inv("")
        out = capsys.readouterr().out
        assert "尚未开始游戏" in out

    def test_skills_before_new_game(self, capsys) -> None:
        repl = Repl()
        repl.cmd_skills("")
        out = capsys.readouterr().out
        assert "尚未开始游戏" in out

    def test_map_before_new_game(self, capsys) -> None:
        repl = Repl()
        repl.cmd_map("")
        out = capsys.readouterr().out
        assert "尚未开始游戏" in out

    def test_quest_before_new_game(self, capsys) -> None:
        repl = Repl()
        repl.cmd_quest("")
        out = capsys.readouterr().out
        assert "尚未开始游戏" in out


# ─────────────────────────────────────────────────────────────────────────────
# Reset
# ─────────────────────────────────────────────────────────────────────────────
class TestReset:
    def test_reset_clears_session(self, capsys) -> None:
        repl = Repl()
        repl.game_session.char_name = "许满"
        repl.game_session.game_started = True
        repl.game_session.turn_count = 42
        repl.cmd_reset("")
        assert repl.game_session.char_name == ""
        assert repl.game_session.game_started is False
        assert repl.game_session.turn_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# Confirmation dialog
# ─────────────────────────────────────────────────────────────────────────────
class TestConfirmDialog:
    def test_invalid_number_reprompts(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        # _confirm is used by cmd_new but we test it directly.
        repl = Repl()
        inputs = iter(["abc", "1"])
        repl.input_fn = lambda _p: next(inputs)
        idx = repl._confirm("选择", ["A", "B"])
        assert idx == 0
        out = capsys.readouterr().out
        assert "无效选择" in out

    def test_empty_defaults_to_first(self) -> None:
        repl = Repl()
        repl.input_fn = lambda _p: ""
        idx = repl._confirm("选择", ["A", "B"])
        assert idx == 0

    def test_out_of_range_reprompts(self, capsys) -> None:
        repl = Repl()
        inputs = iter(["0", "99", "1"])
        repl.input_fn = lambda _p: next(inputs)
        idx = repl._confirm("选择", ["A", "B"])
        assert idx == 0
        out = capsys.readouterr().out
        assert out.count("无效选择") == 2


# ─────────────────────────────────────────────────────────────────────────────
# History
# ─────────────────────────────────────────────────────────────────────────────
class TestHistory:
    def test_history_empty_initially(self, capsys) -> None:
        repl = Repl()
        repl.cmd_history("")
        out = capsys.readouterr().out
        assert "暂无历史" in out
        assert repl.history == []

    def test_history_populated_after_input(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        inputs = iter(["/help", "/status", "/history", "/exit"])
        repl = _make_repl(inputs)
        rc = repl.run()
        assert rc == 0
        assert "/help" in repl.history
        assert "/status" in repl.history


# ─────────────────────────────────────────────────────────────────────────────
# Log (turn history display)
# ─────────────────────────────────────────────────────────────────────────────
class TestLog:
    def test_log_empty_before_game(self, capsys) -> None:
        repl = Repl()
        repl.cmd_log("")
        out = capsys.readouterr().out
        assert "暂无" in out

    def test_log_with_history(self, capsys) -> None:
        repl = Repl()
        repl.game_session.game_started = True
        repl.game_session.turn_history = [
            {"turn": 1, "narrative": "你开始修炼。"},
            {"turn": 2, "narrative": "灵气涌动。"},
        ]
        repl.cmd_log("")
        out = capsys.readouterr().out
        assert "第 1 回合" in out
        assert "第 2 回合" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
