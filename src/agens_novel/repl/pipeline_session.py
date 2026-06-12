"""PipelineSession -- tracks step-by-step pipeline state across REPL commands.

Instead of running Planner -> Writer -> Reviewer -> Editor in one shot,
the user can advance through stages one at a time, inspecting results
between steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_STAGE_ORDER = ["planner", "writer", "reviewer", "editor"]


@dataclass
class PipelineSession:
    """Stateful session for step-by-step pipeline execution."""

    user_request: str = ""
    style_hint: str = ""
    thread_id: str = ""
    run_id: str = ""
    model: str = ""
    base_url: str = ""
    api_key_set: bool = False

    # Stage outputs
    outline: str = ""
    plan_notes: str = ""
    draft: str = ""
    review_score: int = 0
    review_passed: bool = False
    review_feedback: str = ""
    review_iterations: int = 0
    final_text: str = ""
    error: str = ""

    completed_stages: list[str] = field(default_factory=list)

    def next_stage(self) -> str | None:
        """Return the next unfinished stage, or None if complete."""
        for stage in _STAGE_ORDER:
            if stage not in self.completed_stages:
                return stage
        return None

    def can_run(self, stage: str) -> bool:
        """Check whether a stage's prerequisites are met."""
        if stage in self.completed_stages:
            return False
        if stage == "planner":
            return bool(self.user_request)
        if stage == "writer":
            return bool(self.outline) or bool(self.user_request)
        if stage == "reviewer":
            return bool(self.draft)
        if stage == "editor":
            return bool(self.draft)
        return False

    def mark_done(self, stage: str) -> None:
        if stage not in self.completed_stages:
            self.completed_stages.append(stage)

    def reset(self) -> None:
        """Clear all state for a fresh start."""
        self.user_request = ""
        self.style_hint = ""
        self.thread_id = ""
        self.run_id = ""
        self.model = ""
        self.base_url = ""
        self.api_key_set = False
        self.outline = ""
        self.plan_notes = ""
        self.draft = ""
        self.review_score = 0
        self.review_passed = False
        self.review_feedback = ""
        self.review_iterations = 0
        self.final_text = ""
        self.error = ""
        self.completed_stages.clear()

    def as_orchestrator_state(self) -> dict[str, Any]:
        """Convert to a dict compatible with OrchestratorState for sub-agent invocation."""
        return {
            "user_request": self.user_request,
            "style_hint": self.style_hint,
            "thread_id": self.thread_id,
            "run_id": self.run_id,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_set": self.api_key_set,
            "outline": self.outline,
            "plan_notes": self.plan_notes,
            "draft": self.draft,
            "review_score": self.review_score,
            "review_passed": self.review_passed,
            "review_feedback": self.review_feedback,
            "review_iterations": self.review_iterations,
            "final_text": self.final_text,
            "error": self.error,
        }

    def update_from_result(self, result: dict[str, Any]) -> None:
        """Merge a sub-agent result dict into the session state."""
        for key in (
            "outline", "plan_notes", "draft", "final_text",
            "review_score", "review_passed", "review_feedback",
            "review_iterations", "error", "run_id", "model",
            "base_url", "api_key_set",
        ):
            if key in result and result[key]:
                setattr(self, key, result[key])
