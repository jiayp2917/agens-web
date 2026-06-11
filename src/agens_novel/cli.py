"""Typer CLI: agens_novel entry point.

Subcommands:
  init    — create runtime/ skeleton, verify env (no key printed).
  run     — execute the Writer Agent on a user input.
  status  — show the most recent run summary.
  repl    — launch the interactive multi-agent REPL.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from . import __version__
from . import paths
from .logging_setup import setup_logging
from .settings import Settings
from .utils.secrets import mask

app = typer.Typer(
    name="agens-novel",
    help="LangGraph-based novel production system (single-Agent learning scaffold).",
    no_args_is_help=True,
    add_completion=False,
)
# Force UTF-8 safe rendering on Windows consoles (avoid GBK codec errors).
console = Console(legacy_windows=False, force_terminal=False, soft_wrap=True)
log = logging.getLogger("agens_novel.cli")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"agens-novel {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", callback=_version_callback, is_eager=True,
        help="Show version and exit.",
    ),
    log_level: str = typer.Option("INFO", "--log-level", help="DEBUG/INFO/WARNING/ERROR"),
) -> None:
    setup_logging(level=getattr(logging, log_level.upper(), logging.INFO))


# ─────────────────────────────────────────────────────────────────────────────
# init
# ─────────────────────────────────────────────────────────────────────────────
@app.command()
def init() -> None:
    """Create the runtime/ skeleton and verify the env (never prints the key)."""
    created = paths.ensure_runtime_dirs()
    console.print(Panel(
        "[green]✔ runtime/ directories ready[/green]\n"
        + "\n".join(f"  {name}: {p}" for name, p in created.items()),
        title="agens-novel init",
    ))

    settings = Settings()
    summary = settings.public_summary()
    console.print(Panel(
        "\n".join(f"  {k}: {v}" for k, v in summary.items()),
        title="Settings (api_key masked)",
    ))

    if not settings.has_api_key():
        console.print(
            "\n[yellow]⚠ AGNES_API_KEY is not set.[/yellow]\n"
            "  Set it in your shell before running:\n"
            "    $env:AGNES_API_KEY = \"sk-...\"\n"
            "  Or use scripts/run_with_key.ps1 to inject + auto-clean."
        )
        raise typer.Exit(code=2)

    console.print("[green]✔ AGNES_API_KEY is set[/green]")


# ─────────────────────────────────────────────────────────────────────────────
# run
# ─────────────────────────────────────────────────────────────────────────────
@app.command()
def run(
    input: str = typer.Option(..., "--input", "-i", help="The writing request."),
    style_hint: str = typer.Option("", "--style", "-s", help="Optional style override."),
) -> None:
    """Run the Writer Agent on a user input."""
    settings = Settings()
    if not settings.has_api_key():
        console.print("[red]✘ AGNES_API_KEY is not set. Run 'init' first.[/red]")
        raise typer.Exit(code=2)

    from .agents.writer.nodes import run_writer_agent

    with console.status("[bold green]Running Writer Agent..."):
        result = run_writer_agent(user_input=input, style_hint=style_hint)

    if result.get("llm_error"):
        console.print(
            Panel(
                f"[red]LLM call failed:[/red]\n{result['llm_error']}\n\n"
                f"audit: {result.get('audit_path', '<not written>')}",
                title="Writer Agent — error",
            )
        )
        raise typer.Exit(code=1)

    output = result.get("output_text", "").strip()
    console.print(Panel(
        output or "(empty output)",
        title=f"output.md (run {result.get('run_id', '?')})",
        border_style="green",
    ))
    console.print(
        f"\n[dim]path:[/dim] {result.get('output_path')}\n"
        f"[dim]audit:[/dim] {result.get('audit_path')}\n"
        f"[dim]tokens:[/dim] {result.get('usage')} | [dim]elapsed:[/dim] {result.get('elapsed_ms')}ms"
    )


# ─────────────────────────────────────────────────────────────────────────────
# status
# ─────────────────────────────────────────────────────────────────────────────
@app.command()
def status() -> None:
    """Show the most recent run summary."""
    artifacts_root = paths.ARTIFACT_ROOT / "writer"
    if not artifacts_root.exists():
        console.print("[yellow]No runs yet. Use `run` to start.[/yellow]")
        return

    runs = [p for p in artifacts_root.iterdir() if p.is_dir()]
    if not runs:
        console.print("[yellow]No runs yet. Use `run` to start.[/yellow]")
        return
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    latest = runs[0]
    audit_path = latest / "audit.json"
    output_path = latest / "output.md"

    audit: dict[str, Any] = {}
    if audit_path.exists():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))

    console.print(Panel(
        f"  run_id:    {latest.name}\n"
        f"  model:     {audit.get('model', '?')}\n"
        f"  started:   {audit.get('started_at', '?')}\n"
        f"  finished:  {audit.get('finished_at', '?')}\n"
        f"  tokens:    {audit.get('usage', {})}\n"
        f"  elapsed:   {audit.get('elapsed_ms', '?')}ms\n"
        f"  output:    {output_path}\n"
        f"  ok:        {not audit.get('llm_error')}",
        title=f"latest run ({len(runs)} total)",
    ))


# ─────────────────────────────────────────────────────────────────────────────
# repl — interactive multi-agent REPL
# ─────────────────────────────────────────────────────────────────────────────
@app.command()
def repl() -> None:
    """Launch the interactive multi-agent REPL."""
    from .repl import Repl, default_runner

    settings = Settings()
    if not settings.has_api_key():
        console.print(
            "[yellow]⚠ AGNES_API_KEY is not set — the REPL will reject writes.[/yellow]\n"
            "  Set it in your shell, or use scripts/run_with_key.ps1."
        )

    session = Repl(runner=default_runner)
    raise typer.Exit(code=session.run())


if __name__ == "__main__":
    app()
