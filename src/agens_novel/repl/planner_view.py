"""``/plan <request>`` — run the Planner sub-agent standalone."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import patch

from rich.console import Console
from rich.panel import Panel

from ..agents.planner.nodes import call_agnes_llm, build_prompt, load_settings, save_artifact


def run_plan_only(console: Console, user_request: str) -> None:
    """Run the Planner sub-agent synchronously and display the parsed outline."""
    state: dict = {"user_request": user_request, "style_hint": "", "thread_id": f"plan-{uuid.uuid4().hex[:8]}"}
    state.update(load_settings(state))
    state.update(build_prompt(state))

    with console.status("[bold green]planning..."):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                state.update(loop.run_until_complete(call_agnes_llm(state)))
            else:
                state.update(asyncio.run(call_agnes_llm(state)))
        except RuntimeError:
            state.update(asyncio.run(call_agnes_llm(state)))
    state.update(save_artifact(state))

    if state.get("llm_error"):
        console.print(f"[red]✘ planner failed:[/red] {state['llm_error']}")
        return
    console.print(Panel(
        state.get("outline") or "(no outline parsed)",
        title="outline",
        border_style="cyan",
    ))
    if state.get("plan_notes"):
        console.print(Panel(state["plan_notes"], title="plan notes", border_style="blue"))
