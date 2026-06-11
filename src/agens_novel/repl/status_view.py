"""REPL helper views — split out so they can be unit-tested without driving the loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

from .. import paths


def show_latest(console: Console, agent: str = "orchestrator") -> None:
    root = paths.ARTIFACT_ROOT / agent
    if not root.exists():
        console.print(f"[yellow]No {agent} runs yet.[/yellow]")
        return
    runs = [p for p in root.iterdir() if p.is_dir()]
    if not runs:
        console.print(f"[yellow]No {agent} runs yet.[/yellow]")
        return
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    latest = runs[0]
    audit_path = latest / "audit.json"
    audit: dict[str, Any] = {}
    if audit_path.exists():
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            audit = {}
    console.print(Panel(
        f"  run_id:    {latest.name}\n"
        f"  started:   {audit.get('started_at', '?')}\n"
        f"  finished:  {audit.get('finished_at', '?')}\n"
        f"  score:     {audit.get('review_score', '?')}\n"
        f"  iterations:{audit.get('review_iterations', '?')}\n"
        f"  output:    {latest / 'output.md'}\n"
        f"  audit:     {audit_path}",
        title=f"latest {agent} run ({len(runs)} total)",
    ))
