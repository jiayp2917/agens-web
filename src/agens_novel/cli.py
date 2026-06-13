"""Typer CLI: agens_novel entry point.

Subcommands:
  init    — create runtime/ skeleton, verify env (no key printed).
  status  — show the most recent run summary.
  repl    — launch the interactive xianxia cultivation simulator.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from . import __version__
from . import paths
from .logging_setup import setup_logging
from .settings import Settings

app = typer.Typer(
    name="agens-novel",
    help="文字修仙 - AI 驱动的修仙世界模拟器",
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
        "[green]✔ runtime/ 目录已就绪[/green]\n"
        + "\n".join(f"  {name}: {p}" for name, p in created.items()),
        title="agens-novel init",
    ))

    settings = Settings()
    summary = settings.public_summary()
    console.print(Panel(
        "\n".join(f"  {k}: {v}" for k, v in summary.items()),
        title="配置（api_key 已脱敏）",
    ))

    if not settings.has_api_key():
        console.print(
            "\n[yellow]⚠ AGNES_API_KEY 未设置。[/yellow]\n"
            "  请先在终端中设置环境变量：\n"
            "    $env:AGNES_API_KEY = \"sk-...\"\n"
            "  或使用 scripts/run_with_key.ps1 自动注入。"
        )
        raise typer.Exit(code=2)

    console.print("[green]✔ AGNES_API_KEY 已设置[/green]")


# ─────────────────────────────────────────────────────────────────────────────
# status
# ─────────────────────────────────────────────────────────────────────────────
@app.command()
def status() -> None:
    """Show the most recent run summary."""
    artifacts_root = paths.ARTIFACT_ROOT / "narrator"
    if not artifacts_root.exists():
        console.print("[yellow]尚无运行记录。输入 agens-novel repl 开始游戏。[/yellow]")
        return

    runs = [p for p in artifacts_root.iterdir() if p.is_dir()]
    if not runs:
        console.print("[yellow]尚无运行记录。[/yellow]")
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
        title=f"最近一次运行（共 {len(runs)} 次）",
    ))


# ─────────────────────────────────────────────────────────────────────────────
# repl — interactive game
# ─────────────────────────────────────────────────────────────────────────────
@app.command()
def repl() -> None:
    """Launch the interactive xianxia cultivation simulator."""
    from .repl import Repl

    settings = Settings()
    if not settings.has_api_key():
        console.print(
            "[yellow]⚠ AGNES_API_KEY 未设置 — 游戏将无法运行。[/yellow]\n"
            "  请先设置环境变量，或使用 scripts/run_with_key.ps1。"
        )

    session = Repl()
    raise typer.Exit(code=session.run())


if __name__ == "__main__":
    app()
