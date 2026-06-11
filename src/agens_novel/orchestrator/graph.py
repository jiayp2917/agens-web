"""Orchestrator — chains Planner → Writer → Reviewer → Editor.

The Orchestrator is a single ``StateGraph(OrchestratorState)`` that runs each
sub-agent in sequence. After the Reviewer runs, the orchestrator either
forwards to the Editor (review passed) or loops back to the Writer with
feedback appended to the user message (review failed, iterations < 3).

Note: the four sub-agents are themselves state graphs. To keep the
orchestrator's state shape stable, we invoke each sub-agent by calling
its nodes directly here, passing the orchestrator's state into them. This
sidesteps LangGraph's "state must match the sub-graph's TypedDict" friction
because all four sub-agents share ``OrchestratorState`` already.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from ..agents.editor import nodes as editor_nodes
from ..agents.planner import nodes as planner_nodes
from ..agents.reviewer import nodes as reviewer_nodes
from ..agents.writer import nodes as writer_nodes
from ..state.orchestrator_schema import OrchestratorState
from ..utils.timing import utcnow_iso

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Sub-agent wrappers: run a sub-graph and merge its output back into the
# orchestrator's running state. Each wrapper handles the full
# load → build → call → save cycle for its agent.
# ─────────────────────────────────────────────────────────────────────────────
def _run_sub_agent(state: dict[str, Any], agent_module: Any) -> dict[str, Any]:
    """Drive a sub-agent by calling its four nodes in order and merging output."""
    updates: dict[str, Any] = {}
    updates.update(agent_module.load_settings(state))
    updates.update(agent_module.build_prompt({**state, **updates}))
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            llm_updates = loop.run_until_complete(_async_call(agent_module, {**state, **updates}))
        else:
            llm_updates = asyncio.run(_async_call(agent_module, {**state, **updates}))
    except RuntimeError:
        llm_updates = asyncio.run(_async_call(agent_module, {**state, **updates}))
    updates.update(llm_updates)
    updates.update(agent_module.save_artifact({**state, **updates}))
    return updates


async def _async_call(agent_module: Any, state: dict[str, Any]) -> dict[str, Any]:
    return await agent_module.call_agnes_llm(state)


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator nodes
# ─────────────────────────────────────────────────────────────────────────────
def plan_dispatch(state: dict[str, Any]) -> dict[str, Any]:
    """Run the Planner sub-agent."""
    log.info("[orchestrator] -> planner")
    out = _run_sub_agent(state, planner_nodes)
    log.info("[orchestrator] planner done: outline=%d chars", len(out.get("outline", "")))
    return out


def write_dispatch(state: dict[str, Any]) -> dict[str, Any]:
    """Run the Writer sub-agent, feeding it the planner's outline as the
    primary user request. The original user request and review feedback (if
    any, on retry) are also attached to the Writer's prompt via a state-level
    override on ``user_input`` and ``style_hint``."""
    log.info("[orchestrator] -> writer (iter=%s)", state.get("review_iterations", 0))
    # The Writer expects ``user_input``/``style_hint`` fields, not the
    # orchestrator's ``user_request``/``outline``. Build a Writer-shaped
    # substate on the fly.
    substate = dict(state)
    substate["user_input"] = _build_writer_user_input(state)
    substate["style_hint"] = state.get("style_hint", "")
    out = _run_sub_agent(substate, writer_nodes)
    log.info("[orchestrator] writer done: draft=%d chars", len(out.get("draft", out.get("output_text", ""))))
    # Normalize Writer's ``output_text`` into the orchestrator's ``draft``.
    if "draft" not in out and "output_text" in out:
        out["draft"] = out["output_text"]
    return out


def review_dispatch(state: dict[str, Any]) -> dict[str, Any]:
    log.info("[orchestrator] -> reviewer (iter=%s)", state.get("review_iterations", 0))
    out = _run_sub_agent(state, reviewer_nodes)
    log.info("[orchestrator] reviewer done: score=%s passed=%s", out.get("review_score"), out.get("review_passed"))
    return out


def review_decide(state: dict[str, Any]) -> str:
    """Conditional edge after review: editor if passed or max iterations, else writer."""
    if state.get("error"):
        return "finish"
    passed = bool(state.get("review_passed"))
    iterations = int(state.get("review_iterations", 0))
    if passed or iterations >= 3:
        return "editor"
    log.info("[orchestrator] review failed, looping back to writer (iter=%d)", iterations)
    return "writer"


def editor_save(state: dict[str, Any]) -> dict[str, Any]:
    log.info("[orchestrator] -> editor")
    out = _run_sub_agent(state, editor_nodes)
    log.info("[orchestrator] editor done: final=%d chars", len(out.get("final_text", "")))
    return out


def orchestrator_finish(state: dict[str, Any]) -> dict[str, Any]:
    """Write the final orchestrator-level audit and log the run."""
    from ..artifacts import store

    run_id = state.get("run_id") or store.new_run_id()
    final_text = state.get("final_text") or state.get("draft") or ""
    audit = {
        "run_id": run_id,
        "agent": "orchestrator",
        "started_at": state.get("started_at"),
        "finished_at": utcnow_iso(),
        "user_request": state.get("user_request"),
        "outline_chars": len(state.get("outline", "")),
        "plan_notes_chars": len(state.get("plan_notes", "")),
        "draft_chars": len(state.get("draft", "")),
        "final_chars": len(final_text),
        "review_score": state.get("review_score", 0),
        "review_passed": bool(state.get("review_passed")),
        "review_iterations": int(state.get("review_iterations", 0)),
        "review_feedback": state.get("review_feedback", ""),
        "error": state.get("error", ""),
        "model": state.get("model"),
    }
    audit_path = store.write_audit("orchestrator", run_id, audit)
    out_path = store.write_output("orchestrator", run_id, final_text)
    store.append_global_log({
        "event": "orchestrator_run_finished", "run_id": run_id,
        "review_score": state.get("review_score", 0),
        "iterations": int(state.get("review_iterations", 0)),
    })
    return {
        "output_path": str(out_path),
        "audit_path": str(audit_path),
        "finished_at": audit["finished_at"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _build_writer_user_input(state: dict[str, Any]) -> str:
    """Compose the user_input fed to the Writer from the planner's outline,
    the original request, and (if present) the reviewer's feedback."""
    parts: list[str] = []
    if state.get("user_request"):
        parts.append(f"[用户原始请求]\n{state['user_request']}")
    if state.get("outline"):
        parts.append(f"[大纲]\n{state['outline']}")
    if state.get("plan_notes"):
        parts.append(f"[风格计划]\n{state['plan_notes']}")
    if state.get("review_feedback") and not state.get("review_passed"):
        parts.append(f"[审稿修改意见(必须落实)]\n{state['review_feedback']}")
    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Graph assembly
# ─────────────────────────────────────────────────────────────────────────────
def build_orchestrator_graph() -> Any:
    g = StateGraph(OrchestratorState)
    g.add_node("planner", plan_dispatch)
    g.add_node("writer", write_dispatch)
    g.add_node("reviewer", review_dispatch)
    g.add_node("editor", editor_save)
    g.add_node("finish", orchestrator_finish)

    g.add_edge(START, "planner")
    g.add_edge("planner", "writer")
    g.add_edge("writer", "reviewer")
    # Conditional: pass -> editor; fail -> writer (loop)
    g.add_conditional_edges(
        "reviewer",
        review_decide,
        {"editor": "editor", "writer": "writer", "finish": "finish"},
    )
    g.add_edge("editor", "finish")
    g.add_edge("finish", END)

    return g.compile(checkpointer=MemorySaver())
