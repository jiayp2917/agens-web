"""Unit tests for the REPL command parser and dispatcher."""

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
        assert isinstance(parse_command("\t\n"), EmptyCommand)

    def test_slash_help(self) -> None:
        c = parse_command("/help")
        assert isinstance(c, SlashCommand)
        assert c.name == "help"
        assert c.args == ""

    def test_slash_with_args(self) -> None:
        c = parse_command("/plan 用 50 字写许满")
        assert isinstance(c, SlashCommand)
        assert c.name == "plan"
        assert "许满" in c.args

    def test_slash_is_case_insensitive_on_name(self) -> None:
        c = parse_command("/HELP")
        assert isinstance(c, SlashCommand)
        assert c.name == "help"

    def test_exit_aliases(self) -> None:
        for s in ["/exit", "/quit", ":q", ":quit", "exit", "quit"]:
            assert isinstance(parse_command(s), ExitCommand), s

    def test_free_form_text_is_write(self) -> None:
        c = parse_command("写一段都市修仙的开头")
        assert isinstance(c, WriteCommand)
        assert "都市修仙" in c.text

    def test_free_form_text_is_stripped(self) -> None:
        c = parse_command("  hello world  ")
        assert isinstance(c, WriteCommand)
        assert c.text == "hello world"

    def test_lone_slash_is_empty(self) -> None:
        assert isinstance(parse_command("/"), EmptyCommand)


# ─────────────────────────────────────────────────────────────────────────────
# format_help
# ─────────────────────────────────────────────────────────────────────────────
class TestFormatHelp:
    def test_lists_all_commands(self) -> None:
        text = format_help()
        for name in ["help", "exit", "status", "config", "history", "agents", "plan"]:
            assert f"/{name}" in text

    def test_returns_string(self) -> None:
        assert isinstance(format_help(), str)
        assert len(format_help()) > 50


# ─────────────────────────────────────────────────────────────────────────────
# Repl dispatcher (uses an injected input function — no real stdin)
# ─────────────────────────────────────────────────────────────────────────────
class TestReplDispatch:
    def test_help_dispatch(self, capsys) -> None:
        from agens_novel.repl import Repl

        repl = Repl(input_fn=lambda _p: "/help")
        # We don't enter run() because the prompt would block; just verify
        # cmd_help is callable and prints the help text.
        repl.cmd_help("")
        captured = capsys.readouterr()
        assert "Available commands" in captured.out

    def test_agents_dispatch(self, capsys) -> None:
        from agens_novel.repl import Repl

        repl = Repl()
        repl.cmd_agents("")
        out = capsys.readouterr().out
        assert "Planner" in out
        assert "Writer" in out
        assert "Reviewer" in out
        assert "Editor" in out

    def test_history_empty(self, capsys) -> None:
        from agens_novel.repl import Repl

        repl = Repl()
        repl.cmd_history("")
        out = capsys.readouterr().out
        assert "no history" in out.lower()

    def test_unknown_slash_in_dispatch(self, capsys) -> None:
        from agens_novel.repl import Repl

        repl = Repl()
        # _dispatch_slash should print an error and not exit.
        from agens_novel.repl import SlashCommand
        exited = repl._dispatch_slash(SlashCommand(name="foobar", args=""))
        assert exited is False
        out = capsys.readouterr().out
        assert "unknown command" in out

    def test_exit_dispatch_returns_true(self) -> None:
        from agens_novel.repl import Repl, SlashCommand

        repl = Repl()
        assert repl._dispatch_slash(SlashCommand(name="exit", args="")) is True
        assert repl._dispatch_slash(SlashCommand(name="quit", args="")) is True

    def test_run_loop_with_injected_inputs(self, capsys) -> None:
        from agens_novel.repl import Repl

        inputs = iter(["/help", "/agents", "/exit"])
        repl = Repl(input_fn=lambda _p: next(inputs))
        rc = repl.run()
        assert rc == 0
        # History should contain the two non-exit commands.
        assert any(line.startswith("/help") for line in repl.history)
        assert any(line.startswith("/agents") for line in repl.history)

    def test_run_loop_with_write_command_calls_runner(self, capsys, monkeypatch) -> None:
        from agens_novel.repl import Repl

        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        called: list[tuple[str, str]] = []

        def fake_runner(req: str, hint: str) -> dict:
            called.append((req, hint))
            return {"final_text": "**最终的正文**", "draft": "draft", "review_score": 8,
                    "review_iterations": 1, "output_path": "/tmp/x", "audit_path": "/tmp/a",
                    "error": ""}

        inputs = iter(["写一段都市修仙", "/exit"])
        repl = Repl(input_fn=lambda _p: next(inputs), runner=fake_runner)
        rc = repl.run()
        assert rc == 0
        assert called == [("写一段都市修仙", "")]


class TestReplErrorHandling:
    def test_write_without_api_key_rejected(self, capsys, monkeypatch) -> None:
        from agens_novel.repl import Repl

        monkeypatch.delenv("AGNES_API_KEY", raising=False)
        # runner would be called only if api key is set
        def fail_runner(*_a, **_k):  # pragma: no cover
            raise AssertionError("runner should not be called")

        inputs = iter(["写一段", "/exit"])
        repl = Repl(input_fn=lambda _p: next(inputs), runner=fail_runner)
        rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        assert "AGNES_API_KEY" in out

    def test_write_with_runner_error(self, capsys, monkeypatch) -> None:
        from agens_novel.repl import Repl

        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        def error_runner(_req, _hint):
            return {"error": "boom", "final_text": "", "audit_path": "/x"}

        inputs = iter(["x", "/exit"])
        repl = Repl(input_fn=lambda _p: next(inputs), runner=error_runner)
        repl.run()
        out = capsys.readouterr().out
        assert "boom" in out

    def test_eof_exits_cleanly(self, capsys, monkeypatch) -> None:
        from agens_novel.repl import Repl

        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        def raise_eof(_p):
            raise EOFError

        repl = Repl(input_fn=raise_eof)
        rc = repl.run()
        assert rc == 0
