"""Orchestrator -- chains Planner -> Writer -> Reviewer -> Editor.

The Orchestrator is a single ``StateGraph(OrchestratorState)`` that runs each
sub-agent in sequence. After the Reviewer runs, the orchestrator either
forwards to the Editor (review passed) or loops back to the Writer with
feedback appended to the user message (review failed, iterations < 3).

Sub-agents are invoked by calling their node functions directly (not via
compiled sub-graphs) so that all four share the OrchestratorState shape.
The trade-off is that sub-graph checkpointers are not used; see the README
for the rationale.
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
from ..artifacts import store
from ..state.orchestrator_schema import OrchestratorState
from ..utils.timing import utcnow_iso

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Sub-agent wrapper
# ─────────────────────────────────────────────────────────────────────────────
async def _run_sub_agent(state: dict[str, Any], agent_module: Any) -> dict[str, Any]:
    """Drive a sub-agent by calling its four nodes in order and merging output.

    Async so it works correctly inside LangGraph's ``ainvoke``. We skip
    ``load_settings`` when the orchestrator has already bootstrapped run_id /
    model / base_url, to keep a single run_id for cross-agent correlation.
    """
    updates: dict[str, Any] = {}
    if state.get("run_id"):
        # Orchestrator already bootstrapped -- carry forward.
        updates.update({
            "run_id": state["run_id"],
            "model": state.get("model", ""),
            "base_url": state.get("base_url", ""),
            "api_key_set": state.get("api_key_set", False),
            "started_at": state.get("started_at", ""),
        })
    else:
        updates.update(agent_module.load_settings(state))
    updates.update(agent_module.build_prompt({**state, **updates}))
    updates.update(await agent_module.call_agnes_llm({**state, **updates}))
    updates.update(agent_module.save_artifact({**state, **updates}))
    return updates


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator nodes
# ─────────────────────────────────────────────────────────────────────────────
def init_run(state: dict[str, Any]) -> dict[str, Any]:
    """Bootstrap the orchestrator run: generate run_id, read env, validate."""
    user_request = state.get("user_request", "").strip()
    if not user_request:
        raise ValueError("user_request is required (pass a non-empty string).")
    base_url = os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    model = os.environ.get("AGNES_MODEL", "agnes-2.0-flash")
    api_key = os.environ.get("AGNES_API_KEY", "")
    run_id = store.new_run_id()
    log.info("[orchestrator.init] run_id=%s model=%s", run_id, model)
    return {
        "run_id": run_id,
        "model": model,
        "base_url": base_url,
        "api_key_set": bool(api_key),
        "started_at": utcnow_iso(),
    }


async def plan_dispatch(state: dict[str, Any]) -> dict[str, Any]:
    """Run the Planner sub-agent."""
    log.info("[orchestrator] -> planner")
    out = await _run_sub_agent(state, planner_nodes)
    log.info("[orchestrator] planner done: outline=%d chars", len(out.get("outline", "")))
    # Propagate any LLM error to the orchestrator-level error field.
    if out.get("llm_error"):
        out["error"] = out["llm_error"]
    return out


async def write_dispatch(state: dict[str, Any]) -> dict[str, Any]:
    """Run the Writer sub-agent, feeding it the planner's outline as the
    primary user request."""
    log.info("[orchestrator] -> writer (iter=%s)", state.get("review_iterations", 0))
    substate = dict(state)
    substate["user_input"] = _build_writer_user_input(state)
    substate["style_hint"] = state.get("style_hint", "")
    out = await _run_sub_agent(substate, writer_nodes)
    log.info("[orchestrator] writer done: draft=%d chars", len(out.get("draft", out.get("output_text", ""))))
    # Normalize Writer's ``output_text`` into the orchestrator's ``draft``.
    if "draft" not in out and "output_text" in out:
        out["draft"] = out["output_text"]
    if out.get("llm_error"):
        out["error"] = out["llm_error"]
    return out


async def review_dispatch(state: dict[str, Any]) -> dict[str, Any]:
    log.info("[orchestrator] -> reviewer (iter=%s)", state.get("review_iterations", 0))
    out = await _run_sub_agent(state, reviewer_nodes)
    log.info("[orchestrator] reviewer done: score=%s passed=%s", out.get("review_score"), out.get("review_passed"))
    return out


def review_decide(state: dict[str, Any]) -> str:
    """Conditional edge after review: editor if passed or max iterations, else writer.

    Short-circuits to ``finish`` on any agent-level error (LLM failure etc.).
    The iteration cap (>= 3) prevents infinite loops.
    """
    if state.get("error"):
        return "finish"
    passed = bool(state.get("review_passed"))
    iterations = int(state.get("review_iterations", 0))
    if passed or iterations >= 3:
        return "editor"
    log.info("[orchestrator] review failed, looping back to writer (iter=%d)", iterations)
    return "writer"


async def editor_save(state: dict[str, Any]) -> dict[str, Any]:
    log.info("[orchestrator] -> editor")
    out = await _run_sub_agent(state, editor_nodes)
    log.info("[orchestrator] editor done: final=%d chars", len(out.get("final_text", "")))
    if out.get("llm_error"):
        out["error"] = out["llm_error"]
    return out


def orchestrator_finish(state: dict[str, Any]) -> dict[str, Any]:
    """Write the final orchestrator-level audit and log the run."""
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
        parts.append(f"[user request]\n{state['user_request']}")
    if state.get("outline"):
        parts.append(f"[outline]\n{state['outline']}")
    if state.get("plan_notes"):
        parts.append(f"[style plan]\n{state['plan_notes']}")
    if state.get("review_feedback") and not state.get("review_passed"):
        parts.append(f"[review feedback (must address)]\n{state['review_feedback']}")
    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Graph assembly
# ─────────────────────────────────────────────────────────────────────────────
def build_orchestrator_graph() -> Any:
    g = StateGraph(OrchestratorState)
    g.add_node("init_run", init_run)
    g.add_node("planner", plan_dispatch)
    g.add_node("writer", write_dispatch)
    g.add_node("reviewer", review_dispatch)
    g.add_node("editor", editor_save)
    g.add_node("finish", orchestrator_finish)

    g.add_edge(START, "init_run")
    g.add_edge("init_run", "planner")
    g.add_edge("planner", "writer")
    g.add_edge("writer", "reviewer")
    # Conditional: pass -> editor; fail -> writer (loop); error -> finish
    g.add_conditional_edges(
        "reviewer",
        review_decide,
        {"editor": "editor", "writer": "writer", "finish": "finish"},
    )
    g.add_edge("editor", "finish")
    g.add_edge("finish", END)

    return g.compile(checkpointer=MemorySaver())
