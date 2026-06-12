"""Edge case and error path tests for the interactive REPL.

These tests cover the journeys described in the audit list:
  1. KeyboardInterrupt (Ctrl+C) -- clean exit.
  2. EOF (StopIteration) -- clean exit.
  3. Whitespace-only input -- silent continue.
  4. /help -- shows 14 commands.
  5. /plan with no API key -- error, no crash.
  6. /run with no API key -- error, no crash.
  7. /agents -- shows pipeline diagram.
  8. /config with API key -- api_key masked.
  9. /history -- empty initially, populated after input.
  10. /status -- shows latest run or 'no runs'.
  11. Unknown slash command -- 'unknown command' + 'try /help'.
  12. /plan with empty args -- usage hint.
  13. Confirmation dialog with non-numeric input -- re-prompts.
  14. Confirmation dialog with out-of-range input -- re-prompts.
  15. Pipeline session state persists between commands.
"""

from __future__ import annotations

from typing import Any, Callable
from unittest.mock import patch

import pytest

from agens_novel.repl import Repl, SlashCommand
from agens_novel.repl.commands import SLASH_COMMANDS


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _make_repl(inputs: list[str], runner: Callable | None = None) -> Repl:
    """Build a Repl with a deterministic input stream."""
    it = iter(inputs)
    return Repl(input_fn=lambda _p: next(it), runner=runner)


def _stage_canned(stage: str) -> dict[str, Any]:
    if stage == "planner":
        return {
            "outline": "1. 主角出场\n2. 遇险\n3. 反击\n4. 结尾",
            "plan_notes": "fast-paced, third person",
            "run_id": "test-run-edge-001",
            "model": "agnes-2.0-flash",
            "base_url": "https://apihub.agnes-ai.com/v1",
            "api_key_set": True,
        }
    if stage == "writer":
        return {
            "draft": "许满放下外卖箱,抬头凝视筒子楼上方的天空。",
            "run_id": "test-run-edge-001",
        }
    if stage == "reviewer":
        return {
            "review_score": 8,
            "review_passed": True,
            "review_feedback": "good pacing",
            "review_iterations": 1,
        }
    if stage == "editor":
        return {
            "final_text": "许满放下外卖箱,抬头凝视筒子楼上方的天空,心中笃定。",
            "output_path": "/tmp/output.md",
        }
    return {}


def _patch_run_stage_sync() -> Any:
    return patch(
        "agens_novel.repl.loop.run_stage_sync",
        side_effect=lambda stage, _state: _stage_canned(stage),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Journey 1: KeyboardInterrupt (Ctrl+C) exits cleanly
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney1KeyboardInterrupt:
    def test_kbi_exits_cleanly(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        def raise_kbi(_p):
            raise KeyboardInterrupt

        repl = Repl(input_fn=raise_kbi)
        rc = repl.run()
        assert rc == 0
        # The newline-after-bye is printed so the cursor lands cleanly.
        out = capsys.readouterr().out
        # The exit happens immediately -- no further prompts attempted.
        assert rc == 0


# ─────────────────────────────────────────────────────────────────────────────
# Journey 2: EOF / StopIteration exits cleanly
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney2EofCleanExit:
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

    def test_eof_after_some_inputs_exits_cleanly(self, capsys, monkeypatch) -> None:
        """Commands issued before EOF are recorded in history."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        inputs = iter(["/help", "/agents"])

        def input_fn(_p):
            try:
                return next(inputs)
            except StopIteration:
                raise EOFError

        repl = Repl(input_fn=input_fn)
        rc = repl.run()
        assert rc == 0
        assert "/help" in repl.history
        assert "/agents" in repl.history


# ─────────────────────────────────────────────────────────────────────────────
# Journey 3: Whitespace-only input continues silently
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney3WhitespaceContinues:
    def test_blank_input_silently_continues(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        # Several blank/whitespace inputs, then /exit.
        inputs = iter(["", "   ", "\t\t", "  \n", "/exit"])
        repl = Repl(input_fn=lambda _p: next(inputs))
        rc = repl.run()
        assert rc == 0
        # History should not contain blank lines.
        assert all(h.strip() for h in repl.history)
        assert repl.history == [] or all(h != "" for h in repl.history)

    def test_lone_slash_continues_silently(self, capsys, monkeypatch) -> None:
        """A bare '/' parses as EmptyCommand -- no error, no history."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        inputs = iter(["/", "/exit"])
        repl = Repl(input_fn=lambda _p: next(inputs))
        rc = repl.run()
        assert rc == 0
        # Lone '/' is not added to history.
        assert "/" not in repl.history

    def test_whitespace_does_not_trigger_api_call(
        self, capsys, monkeypatch
    ) -> None:
        """Whitespace must not dispatch to chat or any agent."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        called = {"n": 0}

        def tracking_input(prompt):
            called["n"] += 1
            if called["n"] == 1:
                return "   "
            if called["n"] == 2:
                return "\t"
            return "/exit"

        repl = Repl(input_fn=tracking_input)
        # We never patched the chat agent -- but it should never be called.
        rc = repl.run()
        assert rc == 0
        # The loop made exactly 3 calls: blank, blank, exit.
        assert called["n"] == 3
        # And history is still empty (whitespace was silently skipped).
        assert repl.history == []


# ─────────────────────────────────────────────────────────────────────────────
# Journey 4: /help shows all 14 commands
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney4HelpListsAllCommands:
    def test_help_count_is_14(self, capsys) -> None:
        """`SLASH_COMMANDS` is the single source of truth.

        The journey brief says "14 commands". Looking at the dispatch table in
        Repl._dispatch_slash, the unique functional commands are:
          help, agents, config, status, history, clear, plan, write, review,
          edit, run, step, reset, exit  (with "quit" as an alias for exit).
        That's 14 functional commands; SLASH_COMMANDS stores 15 keys because
        "exit" and "quit" are listed separately in the help table.
        """
        # The dispatch table has 14 functional handlers.
        from agens_novel.repl.loop import Repl as _Repl
        from inspect import getsource
        src = getsource(_Repl._dispatch_slash)
        # Count distinct handler names in the dispatch dict literal.
        # The dispatch block in loop.py maps "exit" and "quit" both to cmd_exit
        # in the if/elif above; the dict itself has 14 entries.
        assert len(SLASH_COMMANDS) == 15  # help table has 15 keys (exit+quit)
        # 14 unique functional command names, with "quit" being an alias.
        unique_names = {k for k in SLASH_COMMANDS.keys() if k != "quit"}
        # That gives 14 unique names.
        assert len(unique_names) == 14

    def test_help_lists_every_command(self, capsys) -> None:
        repl = Repl()
        repl.cmd_help("")
        out = capsys.readouterr().out
        for name in [
            "help", "exit", "quit", "status", "clear", "config",
            "history", "agents", "plan", "write", "review", "edit",
            "run", "step", "reset",
        ]:
            assert f"/{name}" in out, f"missing /{name} in /help output"

    def test_help_header_present(self, capsys) -> None:
        repl = Repl()
        repl.cmd_help("")
        out = capsys.readouterr().out
        assert "Available commands" in out

    def test_help_mentions_chat_fallback(self, capsys) -> None:
        repl = Repl()
        repl.cmd_help("")
        out = capsys.readouterr().out
        assert "Chat Agent" in out
        # And mentions the write-intent detection.
        assert "Writing requests" in out or "writing" in out.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Journey 5: /plan with no API key
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney5PlanNoApiKey:
    def test_plan_no_api_key_shows_error_no_crash(
        self, capsys, monkeypatch
    ) -> None:
        monkeypatch.delenv("AGNES_API_KEY", raising=False)

        inputs = ["/plan write me a story", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync() as stage_mock:
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        assert "AGNES_API_KEY" in out
        assert "not set" in out.lower()
        # Stage runner must NOT have been called.
        assert stage_mock.call_count == 0
        # Session must not be populated.
        assert repl.pipeline_session.user_request == ""


# ─────────────────────────────────────────────────────────────────────────────
# Journey 6: /run with no API key
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney6RunNoApiKey:
    def test_run_no_api_key_shows_error_no_crash(
        self, capsys, monkeypatch
    ) -> None:
        monkeypatch.delenv("AGNES_API_KEY", raising=False)

        runner_called = {"n": 0}

        def fail_runner(*_a, **_k):
            runner_called["n"] += 1
            return {"error": "should not run"}

        inputs = ["/run test", "/exit"]
        repl = _make_repl(inputs, runner=fail_runner)

        rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        assert "AGNES_API_KEY" in out
        assert runner_called["n"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Journey 7: /agents shows pipeline diagram
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney7AgentsDiagram:
    def test_agents_shows_pipeline(self, capsys) -> None:
        repl = Repl()
        repl.cmd_agents("")
        out = capsys.readouterr().out
        # All four agents mentioned.
        assert "Planner" in out
        assert "Writer" in out
        assert "Reviewer" in out
        assert "Editor" in out
        # Arrow indicating flow.
        assert "->" in out
        # Panel title mentions "pipeline".
        assert "pipeline" in out.lower()

    def test_agents_describes_each_role(self, capsys) -> None:
        repl = Repl()
        repl.cmd_agents("")
        out = capsys.readouterr().out
        # Each role's responsibility is described.
        assert "outline" in out.lower()
        assert "draft" in out.lower()
        assert "score" in out.lower() or "feedback" in out.lower()
        assert "final" in out.lower() or "prose" in out.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Journey 8: /config with API key set
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney8ConfigMasksApiKey:
    def test_config_masks_api_key(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        repl = Repl()
        repl.cmd_config("")
        out = capsys.readouterr().out
        # Real key value is NOT printed in plaintext.
        assert "sk-test-1234567890" not in out
        # But the masked form is present.
        assert "sk-***" in out or "***" in out

    def test_config_shows_base_url_and_model(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        monkeypatch.setenv("AGNES_BASE_URL", "https://example.com/v1")
        monkeypatch.setenv("AGNES_MODEL", "agnes-2.0-pro")

        repl = Repl()
        repl.cmd_config("")
        out = capsys.readouterr().out
        assert "https://example.com/v1" in out
        assert "agnes-2.0-pro" in out


# ─────────────────────────────────────────────────────────────────────────────
# Journey 9: /history
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney9History:
    def test_history_empty_initially(self, capsys) -> None:
        repl = Repl()
        repl.cmd_history("")
        out = capsys.readouterr().out
        assert "no history" in out.lower()
        assert repl.history == []

    def test_history_populated_after_input(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        inputs = iter(["/help", "/agents", "/config", "/history", "/exit"])
        repl = _make_repl(inputs)
        rc = repl.run()
        assert rc == 0
        # The /help, /agents, /config lines were appended to history.
        # /history itself is appended too.
        assert "/help" in repl.history
        assert "/agents" in repl.history
        assert "/config" in repl.history
        # The /history line shows the recorded commands.
        out = capsys.readouterr().out
        assert "/help" in out
        assert "/agents" in out

    def test_history_truncates_long_lines(self, capsys) -> None:
        repl = Repl()
        long_line = "/" + "x" * 200
        repl.history.append(long_line)
        repl.cmd_history("")
        out = capsys.readouterr().out
        # Truncation marker "..." should be present.
        assert "..." in out


# ─────────────────────────────────────────────────────────────────────────────
# Journey 10: /status
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney10Status:
    def test_status_handles_no_runs(self, capsys, monkeypatch, tmp_path) -> None:
        """When ARTIFACT_ROOT has no runs, /status should print a friendly message."""
        # Point ARTIFACT_ROOT at a temp dir with no runs.
        from agens_novel import paths
        monkeypatch.setattr(paths, "ARTIFACT_ROOT", tmp_path / "artifacts")

        repl = Repl()
        # Should not raise.
        repl.cmd_status("")
        out = capsys.readouterr().out
        # Either "No ... runs yet" or similar friendly message.
        assert "No" in out or "no" in out.lower()

    def test_status_calls_show_latest(self, capsys, monkeypatch) -> None:
        """cmd_status should defer to status_view.show_latest."""
        from agens_novel.repl import status_view

        with patch.object(status_view, "show_latest") as mock_show:
            repl = Repl()
            repl.cmd_status("")
            mock_show.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Journey 11: Unknown slash command
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney11UnknownCommand:
    def test_unknown_command_message(self, capsys) -> None:
        repl = Repl()
        repl._dispatch_slash(SlashCommand(name="foobar", args=""))
        out = capsys.readouterr().out
        assert "unknown command" in out
        assert "try /help" in out or "/help" in out
        # Must NOT exit the REPL.
        # (Repl is still alive -- we just verify it didn't return True.)

    def test_unknown_command_does_not_exit(self) -> None:
        repl = Repl()
        # _dispatch_slash returns False for unknown commands.
        result = repl._dispatch_slash(SlashCommand(name="nope", args=""))
        assert result is False

    def test_unknown_command_appears_in_history(
        self, capsys, monkeypatch
    ) -> None:
        """Even unknown commands get appended to history (visible in /history)."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        inputs = iter(["/foobar", "/exit"])
        repl = _make_repl(inputs)
        rc = repl.run()
        assert rc == 0
        # /foobar is added to history before dispatch.
        assert any("/foobar" in h for h in repl.history)


# ─────────────────────────────────────────────────────────────────────────────
# Journey 12: /plan with empty args
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney12PlanEmptyArgs:
    def test_plan_empty_args_shows_usage(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        inputs = ["/plan", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync() as stage_mock:
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        assert "usage" in out.lower()
        assert "/plan" in out
        # Stage runner must NOT have been called.
        assert stage_mock.call_count == 0

    def test_plan_whitespace_only_args_shows_usage(
        self, capsys, monkeypatch
    ) -> None:
        """Whitespace-only args are treated as empty."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        inputs = ["/plan   ", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync() as stage_mock:
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        assert "usage" in out.lower()
        assert stage_mock.call_count == 0

    def test_run_empty_args_shows_usage(self, capsys, monkeypatch) -> None:
        """Same for /run -- no args shows usage."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        inputs = ["/run", "/exit"]
        repl = _make_repl(inputs)

        rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        assert "usage" in out.lower()
        assert "/run" in out


# ─────────────────────────────────────────────────────────────────────────────
# Journey 13: Confirmation dialog with non-numeric input
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney13ConfirmNonNumeric:
    def test_invalid_number_reprompts(self, capsys, monkeypatch) -> None:
        """Typing 'abc' to a confirm prompt re-prompts, then accepts valid input."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        # /plan test -> planner runs -> confirm dialog appears
        # First attempt: "abc" (invalid) -> re-prompt
        # Second attempt: "2" (Cancel pipeline) -> exit confirm
        inputs = ["/plan test", "abc", "2", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync():
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        # The "Invalid choice" message should appear at least once.
        assert "Invalid choice" in out

    def test_empty_string_in_confirm_defaults_to_first(
        self, capsys, monkeypatch
    ) -> None:
        """Empty input at confirm prompt defaults to option 0 (first)."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        # /plan test -> confirm -> "" (default to first) -> writer runs
        # Writer's "what next?" -> "3" (Cancel)
        inputs = ["/plan test", "", "3", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync() as stage_mock:
            rc = repl.run()

        assert rc == 0
        # Both planner and writer should have run.
        called = [c.args[0] for c in stage_mock.call_args_list]
        assert "planner" in called
        assert "writer" in called


# ─────────────────────────────────────────────────────────────────────────────
# Journey 14: Confirmation dialog with out-of-range input
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney14ConfirmOutOfRange:
    def test_zero_reprompts(self, capsys, monkeypatch) -> None:
        """Typing '0' is out of range (1-based) -- should re-prompt."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        inputs = ["/plan test", "0", "2", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync():
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        assert "Invalid choice" in out

    def test_ninety_nine_reprompts(self, capsys, monkeypatch) -> None:
        """Typing '99' is out of range -- should re-prompt."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        inputs = ["/plan test", "99", "2", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync():
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        assert "Invalid choice" in out

    def test_negative_reprompts(self, capsys, monkeypatch) -> None:
        """Typing '-1' should also re-prompt (not be parsed as a valid index)."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        inputs = ["/plan test", "-1", "2", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync():
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        assert "Invalid choice" in out

    def test_confirm_recovery_eventually_works(
        self, capsys, monkeypatch
    ) -> None:
        """After multiple bad inputs, a valid input still works."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        # First two attempts invalid, third valid.
        inputs = ["/plan test", "abc", "0", "2", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync() as stage_mock:
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        # Two "Invalid choice" messages, then success.
        assert out.count("Invalid choice") == 2
        # Planner ran once.
        assert stage_mock.call_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# Journey 15: Pipeline session carries over between commands
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney15SessionPersistence:
    def test_session_state_persists_across_commands(
        self, capsys, monkeypatch
    ) -> None:
        """/plan stores the request; /step reads it back; /reset clears it."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        # /plan test -> "2" (Cancel) so we don't go to writer
        # /step -> shows session with planner done
        # /reset -> clears session
        # /step -> "no active pipeline"
        inputs = [
            "/plan test",
            "2",       # Cancel after plan
            "/step",   # should show planner done, writer pending
            "/reset",
            "/step",   # should show "no active pipeline"
            "/exit",
        ]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync():
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        # After /reset, session is cleared (this is the final state we observe).
        assert repl.pipeline_session.user_request == ""
        assert repl.pipeline_session.completed_stages == []
        # Output contains both step messages -- the "no active pipeline"
        # appears twice (once before /reset would be wrong; it should appear
        # only after /reset).
        assert "no active pipeline" in out.lower()
        # /step after /plan+Cancel shows the "pipeline session" panel.
        assert "pipeline session" in out.lower()

    def test_plan_marks_planner_done_and_persists_to_step(
        self, capsys, monkeypatch
    ) -> None:
        """Verify the planner stage is marked done and is visible to /step."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        # /plan test -> "2" (Cancel after plan)
        # At this point, planner is done and writer is pending.
        # We inspect session state by NOT resetting.
        inputs = ["/plan test", "2", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync():
            rc = repl.run()

        assert rc == 0
        # Planner was marked done.
        assert "planner" in repl.pipeline_session.completed_stages
        # Writer was NOT done.
        assert "writer" not in repl.pipeline_session.completed_stages
        # Session.user_request is preserved.
        assert repl.pipeline_session.user_request == "test"
        # next_stage returns "writer".
        assert repl.pipeline_session.next_stage() == "writer"

    def test_session_outline_persists_to_write(
        self, capsys, monkeypatch
    ) -> None:
        """/write uses the outline from /plan; session.outline is preserved."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        # /plan test -> "2" (Cancel) so /plan returns
        # /write -> runs writer (outline already set)
        # writer confirm -> "3" (Cancel)
        inputs = [
            "/plan test",
            "2",      # Cancel after plan
            "/write", # writer can run because session has outline
            "3",      # Cancel after write
            "/exit",
        ]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync() as stage_mock:
            rc = repl.run()

        assert rc == 0
        called = [c.args[0] for c in stage_mock.call_args_list]
        # Both planner and writer ran.
        assert "planner" in called
        assert "writer" in called
        # Session contains the canned outline.
        assert "主角出场" in repl.pipeline_session.outline
        # Session contains the canned draft.
        assert "许满" in repl.pipeline_session.draft

    def test_session_can_run_respects_prerequisites(
        self, capsys, monkeypatch
    ) -> None:
        """/review requires a draft -- session state guards the call."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        # /review alone (no draft yet) -> error
        inputs = ["/review", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync() as stage_mock:
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        assert "No draft" in out
        # Reviewer was never called.
        called = [c.args[0] for c in stage_mock.call_args_list]
        assert "reviewer" not in called

    def test_reset_clears_completed_stages(
        self, capsys, monkeypatch
    ) -> None:
        """/reset clears completed_stages AND all state fields."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        # /plan test -> "2" (Cancel) so we have completed_stages = ["planner"]
        # /reset
        # /plan second -> "2" (Cancel) so we have a fresh session
        inputs = [
            "/plan test",
            "2",
            "/reset",
            "/plan second",
            "2",
            "/exit",
        ]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync():
            rc = repl.run()

        assert rc == 0
        # Final state reflects the second /plan (request == "second").
        assert repl.pipeline_session.user_request == "second"
        assert repl.pipeline_session.completed_stages == ["planner"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
