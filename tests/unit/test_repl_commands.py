"""Unit tests for the REPL command parser, dispatcher, and chat mode."""

from __future__ import annotations

from agens_novel.repl import (
    EmptyCommand,
    ExitCommand,
    SlashCommand,
    WriteCommand,
    format_help,
    has_write_intent,
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
        c = parse_command("/plan write a story")
        assert isinstance(c, SlashCommand)
        assert c.name == "plan"
        assert "story" in c.args

    def test_slash_is_case_insensitive_on_name(self) -> None:
        c = parse_command("/HELP")
        assert isinstance(c, SlashCommand)
        assert c.name == "help"

    def test_exit_aliases(self) -> None:
        for s in ["/exit", "/quit", ":q", ":quit"]:
            assert isinstance(parse_command(s), ExitCommand), s

    def test_free_form_text_is_write(self) -> None:
        c = parse_command("hello world")
        assert isinstance(c, WriteCommand)
        assert c.text == "hello world"

    def test_free_form_text_is_stripped(self) -> None:
        c = parse_command("  hello world  ")
        assert isinstance(c, WriteCommand)
        assert c.text == "hello world"

    def test_lone_slash_is_empty(self) -> None:
        assert isinstance(parse_command("/"), EmptyCommand)

    def test_new_commands_parse(self) -> None:
        for name in ["write", "review", "edit", "run", "step", "reset"]:
            c = parse_command(f"/{name}")
            assert isinstance(c, SlashCommand), f"/{name}"
            assert c.name == name


# ─────────────────────────────────────────────────────────────────────────────
# has_write_intent
# ─────────────────────────────────────────────────────────────────────────────
class TestWriteIntent:
    def test_detects_chinese_write_intent(self) -> None:
        assert has_write_intent("写一段都市修仙开头")
        assert has_write_intent("帮我写个故事")
        assert has_write_intent("生成一个片段")

    def test_detects_english_write_intent(self) -> None:
        assert has_write_intent("write a story about dragons")
        assert has_write_intent("generate a novel opening")

    def test_no_intent_for_greeting(self) -> None:
        assert not has_write_intent("你好")
        assert not has_write_intent("hello")

    def test_no_intent_for_questions(self) -> None:
        assert not has_write_intent("今天天气怎么样")
        assert not has_write_intent("what is langgraph")


# ─────────────────────────────────────────────────────────────────────────────
# format_help
# ─────────────────────────────────────────────────────────────────────────────
class TestFormatHelp:
    def test_lists_all_commands(self) -> None:
        text = format_help()
        for name in ["help", "exit", "status", "config", "history", "agents",
                      "plan", "write", "review", "edit", "run", "step", "reset"]:
            assert f"/{name}" in text, f"missing /{name} in help"

    def test_mentions_chat_agent(self) -> None:
        text = format_help()
        assert "Chat Agent" in text

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
        assert "Available commands" in captured.out

    def test_agents_dispatch(self, capsys) -> None:
        from agens_novel.repl import Repl

        repl = Repl()
        repl.cmd_agents("")
        out = capsys.readouterr().out
        assert "Planner" in out
        assert "Writer" in out

    def test_history_empty(self, capsys) -> None:
        from agens_novel.repl import Repl

        repl = Repl()
        repl.cmd_history("")
        out = capsys.readouterr().out
        assert "no history" in out.lower()

    def test_unknown_slash_in_dispatch(self, capsys) -> None:
        from agens_novel.repl import Repl, SlashCommand

        repl = Repl()
        exited = repl._dispatch_slash(SlashCommand(name="foobar", args=""))
        assert exited is False
        out = capsys.readouterr().out
        assert "unknown command" in out

    def test_exit_dispatch_returns_true(self) -> None:
        from agens_novel.repl import Repl, SlashCommand

        repl = Repl()
        assert repl._dispatch_slash(SlashCommand(name="exit", args="")) is True

    def test_step_with_no_session(self, capsys) -> None:
        from agens_novel.repl import Repl

        repl = Repl()
        repl.cmd_step("")
        out = capsys.readouterr().out
        assert "no active pipeline" in out.lower()

    def test_reset_clears_session(self, capsys) -> None:
        from agens_novel.repl import Repl

        repl = Repl()
        repl.pipeline_session.user_request = "test"
        repl.cmd_reset("")
        assert repl.pipeline_session.user_request == ""

    def test_write_without_plan_shows_error(self, capsys) -> None:
        from agens_novel.repl import Repl

        repl = Repl()
        repl.cmd_write("")
        out = capsys.readouterr().out
        assert "No outline" in out

    def test_review_without_draft_shows_error(self, capsys) -> None:
        from agens_novel.repl import Repl

        repl = Repl()
        repl.cmd_review("")
        out = capsys.readouterr().out
        assert "No draft" in out

    def test_edit_without_draft_shows_error(self, capsys) -> None:
        from agens_novel.repl import Repl

        repl = Repl()
        repl.cmd_edit("")
        out = capsys.readouterr().out
        assert "No draft" in out


# ─────────────────────────────────────────────────────────────────────────────
# Repl main loop
# ─────────────────────────────────────────────────────────────────────────────
class TestReplLoop:
    def test_run_loop_with_injected_inputs(self, capsys) -> None:
        from agens_novel.repl import Repl

        inputs = iter(["/help", "/agents", "/exit"])
        repl = Repl(input_fn=lambda _p: next(inputs))
        rc = repl.run()
        assert rc == 0
        assert any(line.startswith("/help") for line in repl.history)
        assert any(line.startswith("/agents") for line in repl.history)

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

    def test_help_text_is_ascii(self) -> None:
        from agens_novel.repl import loop as repl_loop

        prompt = repl_loop.PROMPT
        assert all(ord(c) < 128 for c in prompt), f"non-ASCII in PROMPT: {prompt!r}"

    def test_exit_command_prints_bye(self, capsys) -> None:
        from agens_novel.repl import Repl

        inputs = iter(["/exit"])
        repl = Repl(input_fn=lambda _p: next(inputs))
        rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        assert "bye" in out

    def test_slash_run_without_args_shows_usage(self, capsys, monkeypatch) -> None:
        from agens_novel.repl import Repl

        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        inputs = iter(["/run", "/exit"])
        repl = Repl(input_fn=lambda _p: next(inputs))
        repl.run()
        out = capsys.readouterr().out
        assert "usage" in out.lower()

    def test_slash_plan_without_args_shows_usage(self, capsys, monkeypatch) -> None:
        from agens_novel.repl import Repl

        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        inputs = iter(["/plan", "/exit"])
        repl = Repl(input_fn=lambda _p: next(inputs))
        repl.run()
        out = capsys.readouterr().out
        assert "usage" in out.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Chat mode (free-form input goes to Chat Agent)
# ─────────────────────────────────────────────────────────────────────────────
class TestChatMode:
    def test_write_without_api_key_rejected(self, capsys, monkeypatch) -> None:
        from agens_novel.repl import Repl

        monkeypatch.delenv("AGNES_API_KEY", raising=False)

        def fail_runner(*_a, **_k):
            raise AssertionError("runner should not be called")

        inputs = iter(["hello", "/exit"])
        repl = Repl(input_fn=lambda _p: next(inputs), runner=fail_runner)
        rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        assert "AGNES_API_KEY" in out

    def test_write_intent_triggers_confirm(self, monkeypatch) -> None:
        """Free-form text with write intent shows confirmation dialog."""
        from agens_novel.repl import Repl

        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        # Simulate: user types write-intent text, chooses "cancel" (option 2),
        # then /exit.
        inputs = iter(["write a story", "3", "/exit"])
        repl = Repl(input_fn=lambda _p: next(inputs))
        rc = repl.run()
        assert rc == 0

    def test_eof_exits_cleanly(self, monkeypatch) -> None:
        from agens_novel.repl import Repl

        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        def raise_eof(_p):
            raise EOFError

        repl = Repl(input_fn=raise_eof)
        rc = repl.run()
        assert rc == 0


class TestPipelineSession:
    def test_initial_state(self) -> None:
        from agens_novel.repl.pipeline_session import PipelineSession

        s = PipelineSession()
        assert s.user_request == ""
        assert s.completed_stages == []

    def test_next_stage_sequence(self) -> None:
        from agens_novel.repl.pipeline_session import PipelineSession

        s = PipelineSession(user_request="test")
        assert s.next_stage() == "planner"
        s.mark_done("planner")
        assert s.next_stage() == "writer"

    def test_can_run_prerequisites(self) -> None:
        from agens_novel.repl.pipeline_session import PipelineSession

        s = PipelineSession()
        assert not s.can_run("writer")  # needs outline
        s.outline = "test outline"
        assert s.can_run("writer")

    def test_reset_clears_state(self) -> None:
        from agens_novel.repl.pipeline_session import PipelineSession

        s = PipelineSession(user_request="test", outline="x")
        s.mark_done("planner")
        s.reset()
        assert s.user_request == ""
        assert s.outline == ""
        assert s.completed_stages == []

    def test_as_orchestrator_state(self) -> None:
        from agens_novel.repl.pipeline_session import PipelineSession

        s = PipelineSession(user_request="test", draft="hello")
        d = s.as_orchestrator_state()
        assert d["user_request"] == "test"
        assert d["draft"] == "hello"

    def test_update_from_result(self) -> None:
        from agens_novel.repl.pipeline_session import PipelineSession

        s = PipelineSession()
        s.update_from_result({"outline": "bullet1", "plan_notes": "fast"})
        assert s.outline == "bullet1"
        assert s.plan_notes == "fast"
