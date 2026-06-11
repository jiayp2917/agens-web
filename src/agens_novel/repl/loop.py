"""Interactive REPL loop for agens-novel.

Mirrors the feel of Codex/Claude Code: a colored prompt, slash commands for
control, and free-form lines dispatched to the multi-agent orchestrator.

Usage:
    python -m agens_novel repl
    # or:
    python -m agens_novel.cli repl
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Callable

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from .. import paths
from ..settings import Settings
from ..utils.secrets import mask
from .commands import (
    EmptyCommand,
    ExitCommand,
    SlashCommand,
    WriteCommand,
    format_help,
    parse_command,
)

log = logging.getLogger(__name__)

PROMPT = "agens> "
HELP_AGENTS = (
    "Pipeline: [bold]Planner -> Writer -> Reviewer -> Editor[/bold]\n"
    "  - Planner   - free-form request -> outline\n"
    "  - Writer    - outline + request -> draft\n"
    "  - Reviewer  - draft -> score + feedback (loops Writer, max 3 iters)\n"
    "  - Editor    - draft + feedback -> final prose"
)


class Repl:
    """Stateful REPL session. Holds a history list and the input callable."""

    def __init__(
        self,
        console: Console | None = None,
        input_fn: Callable[[str], str] | None = None,
        runner: Callable[[str, str], dict] | None = None,
    ) -> None:
        self.console = console or Console(legacy_windows=True, soft_wrap=True)
        self.input_fn = input_fn or (lambda prompt: Prompt.ask(prompt, console=self.console))
        # runner is injected by main(); default rejects writes to keep the
        # REPL usable in environments without a configured API key.
        self.runner = runner or self._reject_runner
        self.history: list[str] = []

    def _reject_runner(self, user_request: str, style_hint: str) -> dict:
        return {"error": "no runner configured", "final_text": ""}

    # ─────────────────────────────────────────────────────────────────────────
    # Slash-command handlers — each returns a string to print (or "" to skip).
    # ─────────────────────────────────────────────────────────────────────────
    def cmd_help(self, _args: str) -> None:
        self.console.print(format_help())

    def cmd_agents(self, _args: str) -> None:
        self.console.print(Panel(HELP_AGENTS, title="multi-agent pipeline"))

    def cmd_config(self, _args: str) -> None:
        s = Settings()
        for k, v in s.public_summary().items():
            self.console.print(f"  {k}: {v}")

    def cmd_status(self, _args: str) -> None:
        from . import status_view
        status_view.show_latest(self.console)

    def cmd_history(self, _args: str) -> None:
        if not self.history:
            self.console.print("[dim](no history yet)[/dim]")
            return
        for i, line in enumerate(self.history, 1):
            shown = line if len(line) <= 80 else line[:77] + "..."
            self.console.print(f"  {i:>3}  {shown}")

    def cmd_clear(self, _args: str) -> None:
        self.console.clear()

    def cmd_plan(self, args: str) -> None:
        if not args.strip():
            self.console.print("[yellow]usage: /plan <request>[/yellow]")
            return
        if not _has_api_key():
            self.console.print(
                "[red]AGNES_API_KEY is not set. "
                "Run `agens-novel init` first.[/red]"
            )
            return
        from . import planner_view
        planner_view.run_plan_only(self.console, args.strip())

    def cmd_exit(self, _args: str) -> bool:
        self.console.print("[dim]bye.[/dim]")
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Main loop
    # ─────────────────────────────────────────────────────────────────────────
    def run(self) -> int:
        self.console.print(Panel(
            "[bold]agens-novel[/bold] - multi-agent novel REPL\n"
            "Type a writing request, or /help for commands.",
            border_style="cyan",
        ))
        while True:
            try:
                raw = self.input_fn(PROMPT)
            except (EOFError, KeyboardInterrupt, StopIteration):
                # EOF on stdin (Ctrl+Z / Ctrl+D), Ctrl+C, or exhausted test input.
                self.console.print()
                return 0

            cmd = parse_command(raw)
            if isinstance(cmd, EmptyCommand):
                continue
            if isinstance(cmd, ExitCommand):
                self.console.print("[dim]bye.[/dim]")
                return 0
            if isinstance(cmd, SlashCommand):
                self.history.append(f"/{cmd.name} {cmd.args}".rstrip())
                if self._dispatch_slash(cmd):
                    return 0
                continue
            if isinstance(cmd, WriteCommand):
                self.history.append(cmd.text)
                self._handle_write(cmd.text)
                continue
        return 0

    def _dispatch_slash(self, cmd: SlashCommand) -> bool:
        """Return True if REPL should exit."""
        name = cmd.name
        if name in {"exit", "quit"}:
            return self.cmd_exit(cmd.args)
        handler = {
            "help": self.cmd_help,
            "agents": self.cmd_agents,
            "config": self.cmd_config,
            "status": self.cmd_status,
            "history": self.cmd_history,
            "clear": self.cmd_clear,
            "plan": self.cmd_plan,
        }.get(name)
        if handler is None:
            self.console.print(f"[red]unknown command:[/red] /{name}  (try /help)")
            return False
        handler(cmd.args)
        return False

    def _handle_write(self, text: str) -> None:
        if not _has_api_key():
            self.console.print("[red]AGNES_API_KEY is not set. Run `agens-novel init` first.[/red]")
            return
        with self.console.status("[bold green]running multi-agent pipeline..."):
            try:
                result = self.runner(text, "")
            except (SystemExit, KeyboardInterrupt):
                raise
            except Exception:  # noqa: BLE001
                log.exception("pipeline error")
                self.console.print("[red]pipeline error[/red] (see logs for details)")
                return
        if not result:
            self.console.print("[red]runner returned no result[/red]")
            return
        if result.get("error"):
            self.console.print(f"[red]error:[/red] pipeline failed")
            return

        final = (result.get("final_text") or result.get("draft") or "").strip()
        if not final:
            self.console.print("[yellow](empty output)[/yellow]")
            return
        self.console.print(Panel(
            Markdown(final), title="final text", border_style="green",
        ))
        self.console.print(
            f"[dim]score:[/dim] {result.get('review_score', '?')}  "
            f"[dim]iterations:[/dim] {result.get('review_iterations', 0)}  "
            f"[dim]output:[/dim] {result.get('output_path', '?')}"
        )


def _has_api_key() -> bool:
    return bool(os.environ.get("AGNES_API_KEY", ""))


# ─────────────────────────────────────────────────────────────────────────────
# Default runner wiring (used when REPL is launched via the CLI).
# ─────────────────────────────────────────────────────────────────────────────
def default_runner(user_request: str, style_hint: str) -> dict:
    """Run the full orchestrator graph synchronously and return the final state.

    Uses ``asyncio.run()`` unconditionally because the REPL is always launched
    from a synchronous CLI entry point -- there is never a pre-existing event
    loop.
    """
    from ..orchestrator import build_orchestrator_graph
    import asyncio
    import uuid

    graph = build_orchestrator_graph()
    thread_id = f"repl-{uuid.uuid4().hex[:8]}"
    initial: dict = {
        "user_request": user_request,
        "style_hint": style_hint,
        "thread_id": thread_id,
    }
    config = {"configurable": {"thread_id": thread_id}}
    return asyncio.run(graph.ainvoke(initial, config=config))
