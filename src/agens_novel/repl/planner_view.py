"""``/plan <request>`` -- run the Planner sub-agent standalone.

Returns the state dict so callers (like the REPL session) can extract
the outline and plan_notes.
"""

from __future__ import annotations

import asyncio
import uuid

from rich.console import Console
from rich.panel import Panel

from ..agents.planner.nodes import build_prompt, call_agnes_llm, load_settings, save_artifact


def run_plan_only(console: Console, user_request: str) -> dict:
    """Run the Planner sub-agent synchronously and return the full state dict.

    Also prints the outline and plan_notes to the console.
    """
    state: dict = {
        "user_request": user_request,
        "style_hint": "",
        "thread_id": f"plan-{uuid.uuid4().hex[:8]}",
    }
    state.update(load_settings(state))
    state.update(build_prompt(state))

    with console.status("[bold green]planning..."):
        state.update(asyncio.run(call_agnes_llm(state)))
    state.update(save_artifact(state))

    if state.get("llm_error"):
        console.print(f"[red]planner failed:[/red] {state['llm_error']}")
        return state

    outline = state.get("outline", "")
    plan_notes = state.get("plan_notes", "")
    if outline:
        console.print(Panel(outline, title="outline", border_style="cyan"))
    if plan_notes:
        console.print(Panel(plan_notes, title="plan notes", border_style="blue"))
    return state
