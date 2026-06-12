"""StageRunner -- run individual pipeline stages standalone.

Reuses the same sub-agent node functions that the orchestrator uses,
but runs them one at a time so the user can inspect/confirm between steps.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from ..agents.editor import nodes as editor_nodes
from ..agents.planner import nodes as planner_nodes
from ..agents.reviewer import nodes as reviewer_nodes
from ..agents.writer import nodes as writer_nodes
from ..artifacts import store
from ..utils.timing import utcnow_iso

_MODULES = {
    "planner": planner_nodes,
    "writer": writer_nodes,
    "reviewer": reviewer_nodes,
    "editor": editor_nodes,
}


def _bootstrap_env(state: dict[str, Any]) -> dict[str, Any]:
    """Ensure env-level fields exist in state."""
    env = {}
    if not state.get("run_id"):
        env["run_id"] = store.new_run_id()
    if not state.get("model"):
        env["model"] = os.environ.get("AGNES_MODEL", "agnes-2.0-flash")
    if not state.get("base_url"):
        env["base_url"] = os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    if not state.get("api_key_set"):
        env["api_key_set"] = bool(os.environ.get("AGNES_API_KEY", ""))
    if not state.get("started_at"):
        env["started_at"] = utcnow_iso()
    return env


async def run_stage_async(stage: str, state: dict[str, Any]) -> dict[str, Any]:
    """Run a single pipeline stage and return the updates dict."""
    mod = _MODULES.get(stage)
    if mod is None:
        raise ValueError(f"Unknown stage: {stage}")

    # Ensure env bootstrap.
    updates = _bootstrap_env(state)

    # For writer: compose user_input from orchestrator-style state.
    if stage == "writer":
        substate = dict(state)
        substate.update(updates)
        substate["user_input"] = _build_writer_input(substate)
        substate["style_hint"] = substate.get("style_hint", "")
        state = substate
    else:
        state = {**state, **updates}

    # Run the four node functions in sequence.
    result: dict[str, Any] = {}
    result.update(mod.load_settings(state))
    result.update(mod.build_prompt({**state, **result}))
    result.update(await mod.call_agnes_llm({**state, **result}))
    result.update(mod.save_artifact({**state, **result}))
    return result


def run_stage_sync(stage: str, state: dict[str, Any]) -> dict[str, Any]:
    """Synchronous wrapper for REPL use."""
    return asyncio.run(run_stage_async(stage, state))


def _build_writer_input(state: dict[str, Any]) -> str:
    """Compose the user_input for the Writer from session state."""
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
