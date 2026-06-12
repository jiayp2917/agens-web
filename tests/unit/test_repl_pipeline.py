"""Step-by-step REPL pipeline journeys.

These tests exercise the interactive REPL pipeline by driving the Repl object
with injected ``input_fn`` (for slash commands and confirm dialogs) and a
patched ``run_stage_sync`` that returns canned data per stage.

Each journey corresponds to a realistic user workflow described in the
project's audit / acceptance list.
"""

from __future__ import annotations

from typing import Any, Callable
from unittest.mock import patch

import pytest

from agens_novel.repl import Repl


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _stage_canned(stage: str) -> dict[str, Any]:
    """Return a deterministic canned result for a given stage name."""
    if stage == "planner":
        return {
            "outline": "1. 主角出场\n2. 遇险\n3. 反击\n4. 结尾",
            "plan_notes": "fast-paced, third person",
            "run_id": "test-run-001",
            "model": "agnes-2.0-flash",
            "base_url": "https://apihub.agnes-ai.com/v1",
            "api_key_set": True,
        }
    if stage == "writer":
        return {
            "draft": "许满放下外卖箱,抬头看了看破旧筒子楼上方的天空。",
            "run_id": "test-run-001",
        }
    if stage == "reviewer":
        return {
            "review_score": 8,
            "review_passed": True,
            "review_feedback": "good pacing, minor wording issues",
            "review_iterations": 1,
        }
    if stage == "editor":
        return {
            "final_text": "许满放下外卖箱,抬头凝视筒子楼上方的天空,心中笃定。",
            "output_path": "/tmp/output.md",
        }
    return {}


def _runner_canned(_user_request: str, _style_hint: str) -> dict[str, Any]:
    """Return canned output for the full-pipeline runner used by /run."""
    return {
        "final_text": "许满放下外卖箱,抬头凝视筒子楼上方的天空,心中笃定。",
        "draft": "draft text",
        "review_score": 8,
        "review_iterations": 1,
        "output_path": "/tmp/output.md",
    }


def _make_repl(inputs: list[str], runner: Callable | None = None) -> Repl:
    """Build a Repl with a deterministic input stream."""
    it = iter(inputs)
    return Repl(input_fn=lambda _p: next(it), runner=runner)


def _patch_run_stage_sync() -> Any:
    """Patch the run_stage_sync symbol that loop.py imported.

    The REPL imports ``run_stage_sync`` into ``agens_novel.repl.loop`` at
    module load time, so we must patch it there (not at its origin module).
    """
    return patch(
        "agens_novel.repl.loop.run_stage_sync",
        side_effect=lambda stage, _state: _stage_canned(stage),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Journey 1: /plan "test" -> outline -> confirm continue -> writer stage
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney1PlanContinueToWriter:
    def test_plan_then_continue_runs_writer_stage(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-fixture-1234567890")

        # /plan "test"  -> planner runs
        # prompt for "what next?" -> enter "1" (Continue to Writer)
        # writer runs -> prompt for "what next?" -> enter "3" (Cancel pipeline)
        # /exit
        inputs = ["/plan test", "1", "3", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync() as stage_mock:
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        # The outline panel is printed.
        assert "outline" in out.lower()
        # The draft panel is printed.
        assert "draft" in out.lower()
        # Both planner and writer stages were called via stage_runner.
        called_stages = [c.args[0] for c in stage_mock.call_args_list]
        assert "planner" in called_stages
        assert "writer" in called_stages


# ─────────────────────────────────────────────────────────────────────────────
# Journey 2: /write without prior /plan -> "no outline" error
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney2WriteWithoutPlan:
    def test_write_without_outline_shows_error(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-fixture-1234567890")

        inputs = ["/write", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync() as stage_mock:
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        assert "No outline" in out
        # The writer stage must not have been called.
        assert stage_mock.call_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# Journey 3: /review without prior /write -> "no draft" error
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney3ReviewWithoutWrite:
    def test_review_without_draft_shows_error(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-fixture-1234567890")

        inputs = ["/review", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync() as stage_mock:
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        assert "No draft" in out
        assert stage_mock.call_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# Journey 4: /edit without prior /write -> "no draft" error
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney4EditWithoutWrite:
    def test_edit_without_draft_shows_error(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-fixture-1234567890")

        inputs = ["/edit", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync() as stage_mock:
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        assert "No draft" in out
        assert stage_mock.call_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# Journey 5: /step with no active session
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney5StepWithNoSession:
    def test_step_with_no_session_shows_inactive_message(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-fixture-1234567890")

        inputs = ["/step", "/exit"]
        repl = _make_repl(inputs)

        rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        assert "no active pipeline" in out.lower()
        # Session was never started.
        assert repl.pipeline_session.user_request == ""


# ─────────────────────────────────────────────────────────────────────────────
# Journey 6: /step after /plan -> planner done, writer pending
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney6StepAfterPlan:
    def test_step_after_plan_shows_planner_done_writer_pending(
        self, capsys, monkeypatch
    ) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-fixture-1234567890")

        # /plan test -> confirm dialog -> "2" (Cancel pipeline) so writer is not run
        # /step
        # /exit
        inputs = ["/plan test", "2", "/step", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync():
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        # The step panel prints stage statuses.
        assert "planner" in out
        assert "writer" in out
        # Session state shows planner is done and writer is pending.
        assert "planner" in repl.pipeline_session.completed_stages
        assert "writer" not in repl.pipeline_session.completed_stages
        assert repl.pipeline_session.next_stage() == "writer"


# ─────────────────────────────────────────────────────────────────────────────
# Journey 7: /step after /plan + /write -> planner + writer done, reviewer pending
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney7StepAfterPlanAndWrite:
    def test_step_after_plan_and_write_shows_reviewer_pending(
        self, capsys, monkeypatch
    ) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-fixture-1234567890")

        # /plan test -> "1" (Continue to Writer)
        # writer's "what next?" -> "3" (Cancel pipeline)
        # /step
        # /exit
        inputs = ["/plan test", "1", "3", "/step", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync():
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        # Both stages completed.
        assert "planner" in repl.pipeline_session.completed_stages
        assert "writer" in repl.pipeline_session.completed_stages
        assert "reviewer" not in repl.pipeline_session.completed_stages
        # Next stage is reviewer.
        assert repl.pipeline_session.next_stage() == "reviewer"
        # The step output mentions the remaining stages.
        assert "reviewer" in out


# ─────────────────────────────────────────────────────────────────────────────
# Journey 8: /reset clears session
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney8ResetClearsSession:
    def test_reset_clears_session_state(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-fixture-1234567890")

        # /plan test -> "2" (Cancel) so we don't go further
        # /reset
        # /step -> should now show "no active pipeline"
        # /exit
        inputs = ["/plan test", "2", "/reset", "/step", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync():
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        # After reset, the session is empty.
        assert repl.pipeline_session.user_request == ""
        assert repl.pipeline_session.outline == ""
        assert repl.pipeline_session.completed_stages == []
        # The /step after reset should report "no active pipeline".
        assert "no active pipeline" in out.lower()
        # The reset confirmation message is printed.
        assert "reset" in out.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Journey 9: /run "test" -> full pipeline via runner (NOT stage_runner)
# ─────────────────────────────────────────────────────────────────────────────
class TestJourney9RunFullPipeline:
    def test_run_uses_runner_not_stage_runner(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-fixture-1234567890")

        inputs = ["/run test", "/exit"]
        repl = _make_repl(inputs, runner=_runner_canned)

        with _patch_run_stage_sync() as stage_mock:
            rc = repl.run()

        assert rc == 0
        out = capsys.readouterr().out
        # The runner was called for the full pipeline (not stage_runner).
        assert stage_mock.call_count == 0
        # The final text from the canned runner is rendered.
        assert "许满" in out
        # The "final text" panel is printed.
        assert "final" in out.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Bonus: stage_runner call sequence verification
# ─────────────────────────────────────────────────────────────────────────────
class TestStageCallSequence:
    def test_planner_writer_call_order(self, capsys, monkeypatch) -> None:
        """The stage runner is called for planner first, then writer."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-fixture-1234567890")

        inputs = ["/plan test", "1", "3", "/exit"]
        repl = _make_repl(inputs)

        with _patch_run_stage_sync() as stage_mock:
            rc = repl.run()

        assert rc == 0
        called_stages = [c.args[0] for c in stage_mock.call_args_list]
        assert called_stages[0] == "planner"
        assert "writer" in called_stages
        # Planner strictly before writer.
        assert called_stages.index("planner") < called_stages.index("writer")

    def test_runner_receives_user_request_and_empty_style(
        self, capsys, monkeypatch
    ) -> None:
        """The /run command must pass user request as the first arg."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-fixture-1234567890")

        captured: dict[str, Any] = {}

        def capturing_runner(req: str, style: str) -> dict[str, Any]:
            captured["user_request"] = req
            captured["style_hint"] = style
            return _runner_canned(req, style)

        inputs = ["/run hello world", "/exit"]
        repl = _make_repl(inputs, runner=capturing_runner)

        with _patch_run_stage_sync():
            rc = repl.run()

        assert rc == 0
        assert captured["user_request"] == "hello world"
        assert captured["style_hint"] == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
