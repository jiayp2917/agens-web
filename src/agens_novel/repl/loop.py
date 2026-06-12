"""Interactive REPL loop for agens-novel.

Default mode: free-form text goes to the Chat Agent for conversation.
Writing requests are detected and prompt a confirmation dialog.
Pipeline stages can be run step-by-step via /plan, /write, /review, /edit.
Full automatic pipeline is available via /run.
"""

from __future__ import annotations

import logging
import os
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
    has_write_intent,
    parse_command,
)
from .pipeline_session import PipelineSession
from .stage_runner import run_stage_sync

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
    """Stateful REPL session."""

    def __init__(
        self,
        console: Console | None = None,
        input_fn: Callable[[str], str] | None = None,
        runner: Callable[[str, str], dict] | None = None,
    ) -> None:
        self.console = console or Console(legacy_windows=True, soft_wrap=True)
        self.input_fn = input_fn or (lambda prompt: Prompt.ask(prompt, console=self.console))
        self.runner = runner or self._reject_runner
        self.history: list[str] = []
        self.chat_history: list[dict] = []  # multi-turn chat context
        self.pipeline_session = PipelineSession()

    def _reject_runner(self, user_request: str, style_hint: str) -> dict:
        return {"error": "no runner configured", "final_text": ""}

    # ─────────────────────────────────────────────────────────────────────────
    # Confirmation dialog (numbered choice)
    # ─────────────────────────────────────────────────────────────────────────
    def _confirm(self, prompt: str, options: list[str]) -> int:
        """Show a numbered choice prompt. Returns 0-based index."""
        self.console.print(f"\n  {prompt}")
        for i, opt in enumerate(options, 1):
            marker = " (Recommended)" if i == 1 else ""
            self.console.print(f"    {i}. {opt}{marker}")
        while True:
            choice = self.input_fn("  select> ").strip()
            if not choice:
                return 0  # default to first option
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    return idx
            except ValueError:
                pass
            self.console.print("  [yellow]Invalid choice, try again.[/yellow]")

    # ─────────────────────────────────────────────────────────────────────────
    # Slash-command handlers
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

    def cmd_step(self, _args: str) -> None:
        """Show pipeline session state."""
        s = self.pipeline_session
        if not s.user_request:
            self.console.print("[dim](no active pipeline session. Use /plan <request> to start.)[/dim]")
            return
        lines = [f"  request: {s.user_request}"]
        for stage in ["planner", "writer", "reviewer", "editor"]:
            status = "[green]done[/green]" if stage in s.completed_stages else "[dim]pending[/dim]"
            lines.append(f"  {stage}: {status}")
        next_stage = s.next_stage()
        if next_stage:
            cmd = "plan" if next_stage == "planner" else next_stage
            lines.append(f"  [bold]next: /{cmd}[/bold]")
        else:
            lines.append("  [bold]pipeline complete[/bold]")
        self.console.print(Panel("\n".join(lines), title="pipeline session"))

    def cmd_reset(self, _args: str) -> None:
        self.pipeline_session.reset()
        self.console.print("[dim]pipeline session reset.[/dim]")

    def cmd_plan(self, args: str) -> None:
        """Run Planner stage and store result in session."""
        if not args.strip():
            self.console.print("[yellow]usage: /plan <request>[/yellow]")
            return
        if not _has_api_key():
            self.console.print("[red]AGNES_API_KEY is not set. Run `agens-novel init` first.[/red]")
            return

        # Reset session with new request.
        self.pipeline_session.reset()
        self.pipeline_session.user_request = args.strip()
        self.pipeline_session.api_key_set = True

        with self.console.status("[bold green]planning..."):
            try:
                result = run_stage_sync("planner", self.pipeline_session.as_orchestrator_state())
            except Exception:
                log.exception("planner error")
                self.console.print("[red]planner error[/red] (see logs)")
                return

        if result.get("llm_error"):
            self.console.print(f"[red]planner failed:[/red] {result['llm_error']}")
            return

        self.pipeline_session.update_from_result(result)
        self.pipeline_session.mark_done("planner")

        outline = result.get("outline", "")
        plan_notes = result.get("plan_notes", "")
        if outline:
            self.console.print(Panel(outline, title="outline", border_style="cyan"))
        if plan_notes:
            self.console.print(Panel(plan_notes, title="plan notes", border_style="blue"))

        # Ask what to do next.
        choice = self._confirm(
            "Outline generated. What next?",
            ["Continue to Writer (write draft)", "Cancel pipeline"],
        )
        if choice == 0:
            self._run_stage_interactive("writer")

    def cmd_write(self, _args: str) -> None:
        if not self.pipeline_session.can_run("writer"):
            self.console.print("[yellow]No outline available. Run /plan first.[/yellow]")
            return
        self._run_stage_interactive("writer")

    def cmd_review(self, _args: str) -> None:
        if not self.pipeline_session.can_run("reviewer"):
            self.console.print("[yellow]No draft available. Run /write first.[/yellow]")
            return
        self._run_stage_interactive("reviewer")

    def cmd_edit(self, _args: str) -> None:
        if not self.pipeline_session.can_run("editor"):
            self.console.print("[yellow]No draft available. Run /write first.[/yellow]")
            return
        self._run_stage_interactive("editor")

    def cmd_run(self, args: str) -> None:
        """Full automatic pipeline -- no confirmations."""
        if not args.strip():
            self.console.print("[yellow]usage: /run <request>[/yellow]")
            return
        if not _has_api_key():
            self.console.print("[red]AGNES_API_KEY is not set.[/red]")
            return
        with self.console.status("[bold green]running multi-agent pipeline..."):
            try:
                result = self.runner(args.strip(), "")
            except (SystemExit, KeyboardInterrupt):
                raise
            except Exception:
                log.exception("pipeline error")
                self.console.print("[red]pipeline error[/red] (see logs for details)")
                return
        self._display_pipeline_result(result)

    def cmd_exit(self, _args: str) -> bool:
        self.console.print("[dim]bye.[/dim]")
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Stage execution with confirmation
    # ─────────────────────────────────────────────────────────────────────────
    def _run_stage_interactive(self, stage: str) -> None:
        """Run a single pipeline stage, show the result, and ask what's next."""
        stage_name = stage
        spinner_msg = {
            "writer": "[bold green]writing draft...",
            "reviewer": "[bold green]reviewing...",
            "editor": "[bold green]editing...",
        }.get(stage, "[bold green]running...")

        with self.console.status(spinner_msg):
            try:
                result = run_stage_sync(stage, self.pipeline_session.as_orchestrator_state())
            except Exception:
                log.exception(f"{stage} error")
                self.console.print(f"[red]{stage} error[/red] (see logs)")
                return

        if result.get("llm_error"):
            self.console.print(f"[red]{stage} failed:[/red] {result['llm_error']}")
            return

        self.pipeline_session.update_from_result(result)
        self.pipeline_session.mark_done(stage)

        # Display stage output.
        if stage == "writer":
            draft = result.get("draft") or result.get("output_text", "")
            self.pipeline_session.draft = draft
            chars = len(draft)
            self.console.print(Panel(
                draft or "(empty)", title=f"draft ({chars} chars)", border_style="yellow",
            ))
            choice = self._confirm(
                "Draft generated. What next?",
                ["Send to Reviewer (score + feedback)", "Skip review, go to Editor", "Cancel pipeline"],
            )
            if choice == 0:
                self._run_stage_interactive("reviewer")
            elif choice == 1:
                self._run_stage_interactive("editor")

        elif stage == "reviewer":
            score = self.pipeline_session.review_score
            passed = self.pipeline_session.review_passed
            feedback = self.pipeline_session.review_feedback
            icon = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
            self.console.print(Panel(
                f"  score:    {score}/10\n"
                f"  passed:   {icon}\n"
                f"  feedback: {feedback}",
                title="review", border_style="blue",
            ))
            choice = self._confirm(
                "Review done. What next?",
                ["Edit draft (Editor)", "Re-write draft (back to Writer)", "Cancel pipeline"],
            )
            if choice == 0:
                self._run_stage_interactive("editor")
            elif choice == 1:
                # Reset writer stage so it can re-run.
                if "writer" in self.pipeline_session.completed_stages:
                    self.pipeline_session.completed_stages.remove("writer")
                self._run_stage_interactive("writer")

        elif stage == "editor":
            final = self.pipeline_session.final_text
            self.console.print(Panel(
                Markdown(final) if final else "(empty)",
                title="final text", border_style="green",
            ))
            self.console.print(
                f"  [dim]score:[/dim] {self.pipeline_session.review_score}  "
                f"[dim]output:[/dim] {result.get('output_path', '?')}"
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Chat handler (free-form input)
    # ─────────────────────────────────────────────────────────────────────────
    def _handle_chat(self, text: str) -> None:
        """Send free-form input to the Chat Agent."""
        if not _has_api_key():
            self.console.print("[red]AGNES_API_KEY is not set. Run `agens-novel init` first.[/red]")
            return

        # If the input looks like a writing request, offer to start the pipeline.
        if has_write_intent(text):
            choice = self._confirm(
                "Writing request detected. How would you like to proceed?",
                ["Step-by-step pipeline (with confirmations)",
                 "Run full pipeline automatically",
                 "Cancel, just chat"],
            )
            if choice == 0:
                # Step-by-step: start with planner.
                self.cmd_plan(text)
                return
            elif choice == 1:
                # Full automatic.
                self.cmd_run(text)
                return
            # choice == 2: fall through to chat.

        # Regular chat.
        with self.console.status("[bold green]thinking..."):
            try:
                from ..agents.chat.nodes import run_chat_agent
                result = run_chat_agent(text, chat_history=self.chat_history)
            except (SystemExit, KeyboardInterrupt):
                raise
            except Exception:
                log.exception("chat error")
                self.console.print("[red]chat error[/red] (see logs)")
                return

        if result.get("llm_error"):
            self.console.print(f"[red]chat failed:[/red] {result['llm_error']}")
            return

        response = (result.get("output_text") or "").strip()
        if not response:
            self.console.print("[yellow](empty response)[/yellow]")
            return

        # Update multi-turn history.
        self.chat_history.append({"role": "user", "content": text})
        self.chat_history.append({"role": "assistant", "content": response})
        # Cap history.
        if len(self.chat_history) > 20:
            self.chat_history = self.chat_history[-20:]

        self.console.print(Markdown(response))

    # ─────────────────────────────────────────────────────────────────────────
    # Pipeline result display (for /run)
    # ─────────────────────────────────────────────────────────────────────────
    def _display_pipeline_result(self, result: dict) -> None:
        if not result:
            self.console.print("[red]runner returned no result[/red]")
            return
        if result.get("error"):
            self.console.print("[red]error:[/red] pipeline failed")
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

    # ─────────────────────────────────────────────────────────────────────────
    # Main loop
    # ─────────────────────────────────────────────────────────────────────────
    def run(self) -> int:
        self.console.print(Panel(
            "[bold]agens-novel[/bold] - multi-agent novel REPL\n"
            "Chat freely, or use /plan, /write, /review, /edit for step-by-step pipeline.\n"
            "Type /help for commands.",
            border_style="cyan",
        ))
        while True:
            try:
                raw = self.input_fn(PROMPT)
            except (EOFError, KeyboardInterrupt, StopIteration):
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
                self._handle_chat(cmd.text)
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
            "write": self.cmd_write,
            "review": self.cmd_review,
            "edit": self.cmd_edit,
            "run": self.cmd_run,
            "step": self.cmd_step,
            "reset": self.cmd_reset,
        }.get(name)
        if handler is None:
            self.console.print(f"[red]unknown command:[/red] /{name}  (try /help)")
            return False
        handler(cmd.args)
        return False


def _has_api_key() -> bool:
    return bool(os.environ.get("AGNES_API_KEY", ""))


def default_runner(user_request: str, style_hint: str) -> dict:
    """Run the full orchestrator graph synchronously and return the final state."""
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
