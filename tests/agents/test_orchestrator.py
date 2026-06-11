"""End-to-end multi-agent integration test.

Stubs ``call_llm`` at the import site of every sub-agent and returns
agent-specific canned responses. Verifies:
  - planner produces outline + plan_notes
  - writer produces draft
  - reviewer scores it; on first pass, no loop-back
  - editor produces final_text
  - orchestrator writes audit + output
  - on a failing reviewer, the writer is called twice (loop-back)
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Per-agent canned responses. Use ASCII to avoid Windows-terminal encoding
# roundtrips in the source file. The orchestrator's call order is
#   planner(1) -> writer(1) -> reviewer(1)
#   -> (editor | writer-loop -> reviewer -> editor).
# ─────────────────────────────────────────────────────────────────────────────
PLANNER_TEXT = (
    "plan_notes: fast pacing, 30-50 chars, key motif: spirit qi.\n"
    "outline:\n"
    "- hero puts down the delivery box and looks at the sky.\n"
    "- brow furrows, chest feels warm.\n"
    "- pulls out something like a marble, realizes it is qi.\n"
)

WRITER_TEXT = "Hero puts down the delivery box and looks at the sky. Spirit qi... it's real."

REVIEWER_PASS = '{"score": 8, "passed": true, "feedback": "ok"}'
REVIEWER_FAIL = '{"score": 4, "passed": false, "feedback": "lacks concrete action"}'

EDITOR_TEXT = (
    "Hero sets down the delivery box and looks up, brow furrowed. "
    "His chest warms. He pulls out a marble-like thing and knows spirit qi is real."
)


def _make_canned_llm(*, fail_review: bool) -> AsyncMock:
    """Return an AsyncMock that dispatches by the system prompt's first line.

    The agent system prompts all start with ``# <Name> Agent``, so we can
    sniff the agent type precisely without confusing overlapping keywords
    like "writer" appearing in the reviewer's instructions.
    """
    call_log: list[str] = []

    async def side_effect(messages, **_kwargs):
        sys = (messages[0]["content"] if messages else "").lower()
        # Order matters: the Reviewer prompt references "Writer Agent", so we
        # check most-specific substrings first.
        if "planner agent" in sys:
            call_log.append("planner")
            return _resp(PLANNER_TEXT)
        if "editor agent" in sys:
            call_log.append("editor")
            return _resp(EDITOR_TEXT)
        if "reviewer agent" in sys:
            call_log.append("reviewer")
            n = call_log.count("reviewer")
            if fail_review and n == 1:
                return _resp(REVIEWER_FAIL)
            return _resp(REVIEWER_PASS)
        if "writer agent" in sys:
            call_log.append("writer")
            return _resp(WRITER_TEXT)
        # Fallback
        call_log.append("unknown")
        return _resp("")

    mock = AsyncMock(side_effect=side_effect)
    mock.call_log = call_log  # type: ignore[attr-defined]
    return mock


def _resp(text: str) -> dict[str, Any]:
    return {
        "text": text,
        "model": "agnes-2.0-flash",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "finish_reason": "stop",
        "elapsed_ms": 100,
        "raw": {"stub": True},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def orchestrator_env(
    temp_project_root: Path,
    set_api_key: str,
) -> Iterator[dict[str, Any]]:
    """Temp runtime + injected API key + patched call_llm for all 4 sub-agents."""
    mock = _make_canned_llm(fail_review=False)
    patches = [
        patch("agens_novel.agents.planner.nodes.call_llm", mock),
        patch("agens_novel.agents.writer.nodes.call_llm", mock),
        patch("agens_novel.agents.reviewer.nodes.call_llm", mock),
        patch("agens_novel.agents.editor.nodes.call_llm", mock),
    ]
    for p in patches:
        p.start()
    try:
        yield {"mock": mock, "runtime": temp_project_root}
    finally:
        for p in patches:
            p.stop()


@pytest.fixture
def orchestrator_env_loop(
    temp_project_root: Path,
    set_api_key: str,
) -> Iterator[dict[str, Any]]:
    mock = _make_canned_llm(fail_review=True)
    patches = [
        patch("agens_novel.agents.planner.nodes.call_llm", mock),
        patch("agens_novel.agents.writer.nodes.call_llm", mock),
        patch("agens_novel.agents.reviewer.nodes.call_llm", mock),
        patch("agens_novel.agents.editor.nodes.call_llm", mock),
    ]
    for p in patches:
        p.start()
    try:
        yield {"mock": mock, "runtime": temp_project_root}
    finally:
        for p in patches:
            p.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────
def test_orchestrator_first_pass_end_to_end(orchestrator_env) -> None:
    from agens_novel.orchestrator import build_orchestrator_graph
    import asyncio
    import uuid

    graph = build_orchestrator_graph()
    thread_id = f"orch-{uuid.uuid4().hex[:8]}"
    initial = {
        "user_request": "Write a 50-char urban cultivation opening, hero named Xu Man.",
        "thread_id": thread_id,
    }
    config = {"configurable": {"thread_id": thread_id}}
    result = asyncio.run(graph.ainvoke(initial, config=config))

    # Pipeline outputs
    assert "delivery box" in result.get("outline", "")
    assert "delivery box" in result.get("draft", "")
    assert result.get("final_text") == EDITOR_TEXT
    assert result.get("review_passed") is True
    assert result.get("review_score") == 8
    assert result.get("review_iterations") == 1
    assert not result.get("error")

    # All four agents called exactly once.
    log = orchestrator_env["mock"].call_log
    assert log.count("planner") == 1
    assert log.count("writer") == 1
    assert log.count("reviewer") == 1
    assert log.count("editor") == 1

    # Orchestrator-level audit + output written.
    audit_path = Path(result["audit_path"])
    out_path = Path(result["output_path"])
    assert audit_path.exists()
    assert out_path.exists()
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["agent"] == "orchestrator"
    assert audit["review_passed"] is True
    assert audit["review_iterations"] == 1
    assert out_path.read_text(encoding="utf-8") == EDITOR_TEXT


def test_orchestrator_review_loop_back(orchestrator_env_loop) -> None:
    from agens_novel.orchestrator import build_orchestrator_graph
    import asyncio
    import uuid

    graph = build_orchestrator_graph()
    thread_id = f"orch-loop-{uuid.uuid4().hex[:8]}"
    initial = {
        "user_request": "Write a 50-char urban cultivation opening.",
        "thread_id": thread_id,
    }
    config = {"configurable": {"thread_id": thread_id}}
    result = asyncio.run(graph.ainvoke(initial, config=config))

    log = orchestrator_env_loop["mock"].call_log
    # planner(1) -> writer(1) -> reviewer(fail) -> writer(2) -> reviewer(pass) -> editor(1)
    assert log.count("planner") == 1
    assert log.count("writer") == 2
    assert log.count("reviewer") == 2
    assert log.count("editor") == 1
    assert "unknown" not in log

    assert result.get("review_iterations") == 2
    # On the second pass, the second reviewer's feedback should be "ok".
    assert result.get("review_feedback") == "ok"
    assert result.get("final_text") == EDITOR_TEXT
