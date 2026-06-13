"""Unit tests for the REPL command parser and game commands."""

from __future__ import annotations

from agens_novel.repl import (
    EmptyCommand,
    ExitCommand,
    SlashCommand,
    WriteCommand,
    format_help,
    parse_command,
)


# ─────────────────────────────────────────────────────────────────────────────
# parse_command
# ─────────────────────────────────────────────────────────────────────────────
class TestParseCommand:
    def test_blank_is_empty(self) -> None:
        assert isinstance(parse_command(""), EmptyCommand)
        assert isinstance(parse_command("   "), EmptyCommand)

    def test_slash_help(self) -> None:
        c = parse_command("/help")
        assert isinstance(c, SlashCommand)
        assert c.name == "help"
        assert c.args == ""

    def test_slash_with_args(self) -> None:
        c = parse_command("/new 我叫许满")
        assert isinstance(c, SlashCommand)
        assert c.name == "new"
        assert "许满" in c.args

    def test_slash_is_case_insensitive_on_name(self) -> None:
        c = parse_command("/HELP")
        assert isinstance(c, SlashCommand)
        assert c.name == "help"

    def test_exit_aliases(self) -> None:
        for s in ["/exit", "/quit", ":q", ":quit"]:
            assert isinstance(parse_command(s), ExitCommand), s

    def test_free_form_text_is_write(self) -> None:
        c = parse_command("修炼吐纳")
        assert isinstance(c, WriteCommand)
        assert c.text == "修炼吐纳"

    def test_free_form_text_is_stripped(self) -> None:
        c = parse_command("  修炼吐纳  ")
        assert isinstance(c, WriteCommand)
        assert c.text == "修炼吐纳"

    def test_lone_slash_is_empty(self) -> None:
        assert isinstance(parse_command("/"), EmptyCommand)

    def test_new_game_commands_parse(self) -> None:
        for name in ["new", "save", "load", "status", "inv", "skills", "map", "quest", "log", "expand", "reset"]:
            c = parse_command(f"/{name}")
            assert isinstance(c, SlashCommand), f"/{name}"
            assert c.name == name


# ─────────────────────────────────────────────────────────────────────────────
# format_help
# ─────────────────────────────────────────────────────────────────────────────
class TestFormatHelp:
    def test_lists_all_commands(self) -> None:
        text = format_help()
        for name in ["help", "exit", "quit", "status", "new", "save", "load",
                      "inv", "skills", "map", "quest", "log", "expand", "reset"]:
            assert f"/{name}" in text, f"missing /{name} in help"

    def test_mentions_game(self) -> None:
        text = format_help()
        assert "游戏" in text or "修仙" in text

    def test_returns_string(self) -> None:
        assert isinstance(format_help(), str)
        assert len(format_help()) > 50


# ─────────────────────────────────────────────────────────────────────────────
# Repl dispatcher
# ─────────────────────────────────────────────────────────────────────────────
class TestReplDispatch:
    def test_help_dispatch(self, capsys) -> None:
        from agens_novel.repl import Repl

        repl = Repl()
        repl.cmd_help("")
        captured = capsys.readouterr()
        assert "可用命令" in captured.out

    def test_history_empty(self, capsys) -> None:
        from agens_novel.repl import Repl

        repl = Repl()
        repl.cmd_history("")
        out = capsys.readouterr().out
        assert "暂无历史" in out

    def test_unknown_slash_in_dispatch(self, capsys) -> None:
        from agens_novel.repl import Repl, SlashCommand

        repl = Repl()
        exited = repl._dispatch_slash(SlashCommand(name="foobar", args=""))
        assert exited is False
        out = capsys.readouterr().out
        assert "未知命令" in out

    def test_exit_dispatch_returns_true(self) -> None:
        from agens_novel.repl import Repl, SlashCommand

        repl = Repl()
        assert repl._dispatch_slash(SlashCommand(name="exit", args="")) is True

    def test_status_without_game_shows_hint(self, capsys) -> None:
        from agens_novel.repl import Repl

        repl = Repl()
        repl.cmd_status("")
        out = capsys.readouterr().out
        assert "尚未开始游戏" in out

    def test_reset_clears_session(self, capsys) -> None:
        from agens_novel.repl import Repl

        repl = Repl()
        repl.game_session.char_name = "test"
        repl.cmd_reset("")
        assert repl.game_session.char_name == ""

    def test_action_without_game_shows_hint(self, capsys, monkeypatch) -> None:
        from agens_novel.repl import Repl

        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        repl = Repl()
        repl._handle_action("修炼")
        out = capsys.readouterr().out
        assert "尚未开始游戏" in out


# ─────────────────────────────────────────────────────────────────────────────
# Repl main loop
# ─────────────────────────────────────────────────────────────────────────────
class TestReplLoop:
    def test_run_loop_with_injected_inputs(self, capsys) -> None:
        from agens_novel.repl import Repl

        inputs = iter(["/help", "/status", "/exit"])
        repl = Repl(input_fn=lambda _p: next(inputs))
        rc = repl.run()
        assert rc == 0
        assert any(line.startswith("/help") for line in repl.history)
        assert any(line.startswith("/status") for line in repl.history)

    def test_stop_iteration_exits_cleanly(self, monkeypatch) -> None:
        from agens_novel.repl import Repl

        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        def raise_stop(_p):
            raise StopIteration

        repl = Repl(input_fn=raise_stop)
        rc = repl.run()
        assert rc == 0

    def test_keyboard_interrupt_exits_cleanly(self, monkeypatch) -> None:
        from agens_novel.repl import Repl

        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        def raise_kbi(_p):
            raise KeyboardInterrupt

        repl = Repl(input_fn=raise_kbi)
        rc = repl.run()
        assert rc == 0

    def test_console_uses_legacy_windows(self) -> None:
        from agens_novel.repl import Repl

        repl = Repl()
        assert repl.console.legacy_windows is True

    def test_prompt_is_set(self) -> None:
        from agens_novel.repl import loop as repl_loop

        prompt = repl_loop.PROMPT
        assert prompt.endswith("> ")
        assert len(prompt) > 2

    def test_exit_command_prints_bye(self, capsys) -> None:
        from agens_novel.repl import Repl

        inputs = iter(["/exit"])
        repl = Repl(input_fn=lambda _p: next(inputs))
        rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        assert "再见" in out


# ─────────────────────────────────────────────────────────────────────────────
# GameSession
# ─────────────────────────────────────────────────────────────────────────────
class TestGameSession:
    def test_initial_state(self) -> None:
        from agens_novel.repl.game_session import GameSession

        s = GameSession()
        assert s.char_name == ""
        assert s.realm == "练气"
        assert s.turn_count == 0
        assert s.game_started is False

    def test_as_game_state(self) -> None:
        from agens_novel.repl.game_session import GameSession

        s = GameSession(char_name="许满", realm="练气", realm_stage=3, hp=85)
        d = s.as_game_state()
        assert d["character"]["name"] == "许满"
        assert d["character"]["realm"] == "练气"
        assert d["character"]["hp"] == 85

    def test_apply_delta_increment(self) -> None:
        from agens_novel.repl.game_session import GameSession

        s = GameSession(hp=80, mp=40)
        s.apply_delta({"character": {"hp": "+10", "mp": "-5"}})
        assert s.hp == 90
        assert s.mp == 35

    def test_apply_delta_absolute(self) -> None:
        from agens_novel.repl.game_session import GameSession

        s = GameSession(hp=80)
        s.apply_delta({"character": {"hp": 50}})
        assert s.hp == 50

    def test_apply_delta_realm_change(self) -> None:
        from agens_novel.repl.game_session import GameSession

        s = GameSession(realm="练气")
        s.apply_delta({"character": {"realm": "筑基"}})
        assert s.realm == "筑基"

    def test_apply_delta_world(self) -> None:
        from agens_novel.repl.game_session import GameSession

        s = GameSession()
        s.apply_delta({"world": {"location": "青云山", "region": "东荒"}})
        assert s.location == "青云山"
        assert s.region == "东荒"

    def test_apply_delta_game_over(self) -> None:
        from agens_novel.repl.game_session import GameSession

        s = GameSession()
        s.apply_delta({"meta": {"game_over": True, "game_over_reason": "魂飞魄散"}})
        assert s.game_over is True
        assert s.error == "魂飞魄散"

    def test_round_trip_serialization(self) -> None:
        from agens_novel.repl.game_session import GameSession

        s = GameSession(
            char_name="许满", realm="练气", realm_stage=3,
            hp=85, mp=30, spirit_root="火木双灵根",
            location="青云山外门",
            techniques=[{"name": "基础吐纳术", "level": 1, "type": "内功"}],
        )
        s.game_started = True
        s.turn_count = 7
        data = s.to_save_dict()
        s2 = GameSession.from_save_dict(data)
        assert s2.char_name == "许满"
        assert s2.realm == "练气"
        assert s2.hp == 85
        assert s2.location == "青云山外门"
        assert len(s2.techniques) == 1
        assert s2.game_started is True
        assert s2.turn_count == 7

    def test_reset_clears_state(self) -> None:
        from agens_novel.repl.game_session import GameSession

        s = GameSession(char_name="许满", realm="筑基", game_started=True, turn_count=50)
        s.reset()
        assert s.char_name == ""
        assert s.realm == "练气"
        assert s.game_started is False
        assert s.turn_count == 0
